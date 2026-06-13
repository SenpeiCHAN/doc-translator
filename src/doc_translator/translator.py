"""翻译引擎：DeepSeek API 客户端 + 分段翻译提示词 + 重试 + 并发。"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import (
    APIError,
    APIConnectionError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from doc_translator.config import Config
from doc_translator.document import Document, Page
from doc_translator.token_counter import count_tokens

logger = logging.getLogger(__name__)

SEGMENT_DELIMITER = "---SEGMENT---"
MAX_SEGMENT_MISMATCH_RETRIES = 2

SYSTEM_PROMPT = """You are a professional English-Chinese document translator.
Translate the provided page text from English to Simplified Chinese.

RULES:
1. Translate ALL text content faithfully and naturally into Simplified Chinese.
2. Preserve the exact meaning, tone, and register of the original.
3. For proper nouns, company names, product names, and technical terms:
   - If a widely accepted Chinese translation exists, use it.
   - Otherwise, keep the original English term in parentheses after the first occurrence.
4. Do NOT add explanations, commentary, or editorial notes.
5. Do NOT translate code snippets, URLs, or file paths.
6. Preserve the formatting of numbers, dates, and measurements.
7. Maintain the exact segment boundaries — respond with EXACTLY the same number of
   segments as the input, separated by the delimiter "---SEGMENT---".
8. If the input contains mixed languages, translate only the non-Chinese portions.
9. For markdown formatting markers (**, *, #, etc.), keep them intact.

FORMAT:
Input: [Segment 1] ---SEGMENT--- [Segment 2] ---SEGMENT--- ...
Output: [Translation 1] ---SEGMENT--- [Translation 2] ---SEGMENT--- ..."""


class Translator:

    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.api_base_url,
        )
        self.checkpoint_dir: Path | None = None

    def translate_document(self, document: Document) -> Document:
        total = len(document.pages)
        logger.info("共 %d 页待翻译", total)

        self.checkpoint_dir = (
            Path(self.config.output_dir)
            / ".progress"
            / Path(document.source_path).stem
        )
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # 加载断点
        completed = self._load_checkpoint()

        with ThreadPoolExecutor(max_workers=self.config.workers) as pool:
            futures = {}
            for i, page in enumerate(document.pages):
                if page.page_number in completed:
                    # 恢复已翻译页
                    cached = completed[page.page_number]
                    page.translated_text = cached["translated_text"]
                    for j, t in enumerate(cached.get("translated_elements", [])):
                        if j < len(page.elements):
                            page.elements[j].translated_text = t
                    continue
                futures[
                    pool.submit(self._translate_page, page, i + 1)
                ] = page

            for future in as_completed(futures):
                page = futures[future]
                try:
                    future.result()
                    self._save_checkpoint(page)
                except Exception as exc:
                    logger.error(
                        "第 %d 页翻译失败（跳过）: %s",
                        page.page_number, exc,
                    )

        return document

    def _translate_page(self, page: Page, index: int) -> None:
        text_elements = [
            e for e in page.elements if e.type in ("paragraph", "table")
        ]
        if not text_elements:
            logger.info("第 %d 页无翻译内容，跳过", page.page_number)
            return

        segments = [e.text for e in text_elements]
        user_message = (
            "Translate the following document content to Simplified Chinese.\n"
            "Maintain the exact segment boundaries marked by "
            f'"{SEGMENT_DELIMITER}".\n\n'
            + f"\n{SEGMENT_DELIMITER}\n".join(segments)
        )

        # Token 检查
        total_tokens = (
            count_tokens(SYSTEM_PROMPT)
            + count_tokens(user_message)
            + 8192
        )
        if total_tokens > 120_000:
            logger.warning(
                "第 %d 页 token 数量过大 (%d)，可能超出上下文",
                page.page_number, total_tokens,
            )

        logger.info("翻译第 %d/%d 页...", index, page.page_number)

        raw = self._call_with_retry(user_message)
        translated_segments = self._parse_segments(raw, len(segments))

        # 如果段数不匹配，重试
        retries = 0
        while (
            len(translated_segments) != len(segments)
            and retries < MAX_SEGMENT_MISMATCH_RETRIES
        ):
            logger.warning(
                "段数不匹配：期望 %d，实际 %d，正在重试...",
                len(segments), len(translated_segments),
            )
            raw = self._call_with_retry(
                user_message
                + f"\n\n（注意：请确保输出恰好 {len(segments)} 个段，"
                f"用 {SEGMENT_DELIMITER} 分隔）"
            )
            translated_segments = self._parse_segments(raw, len(segments))
            retries += 1

        if len(translated_segments) != len(segments):
            logger.warning(
                "第 %d 页段数仍然不匹配，使用 heuristic 对齐",
                page.page_number,
            )
            translated_segments = self._heuristic_align(
                segments, translated_segments
            )

        for elem, translation in zip(text_elements, translated_segments):
            elem.translated_text = translation

        page.translated_text = "\n".join(
            e.translated_text
            for e in text_elements
            if e.translated_text
        )

    @retry(
        retry=retry_if_exception_type((
            RateLimitError, APIConnectionError, APITimeoutError, APIError,
        )),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _call_with_retry(self, user_message: str) -> str:
        response = self.client.chat.completions.create(
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content or ""

    def _parse_segments(
        self, raw: str, expected: int
    ) -> list[str]:
        parts = raw.split(SEGMENT_DELIMITER)
        if len(parts) == expected:
            return [p.strip() for p in parts]
        return [p.strip() for p in parts]

    def _heuristic_align(
        self, source: list[str], translated: list[str]
    ) -> list[str]:
        if len(translated) >= len(source):
            return translated[:len(source)]
        result = list(translated)
        while len(result) < len(source):
            result.append(source[len(result)])
        return result

    # ---- 断点续传 ----

    def _checkpoint_path(self) -> Path:
        return self.checkpoint_dir / "progress.json"

    def _load_checkpoint(self) -> dict[int, dict]:
        path = self._checkpoint_path()
        if path.exists():
            try:
                raw = json.loads(path.read_text())
                return {int(k): v for k, v in raw.items()}
            except Exception:
                pass
        return {}

    def _save_checkpoint(self, page: Page) -> None:
        current = self._load_checkpoint()
        current[page.page_number] = {
            "translated_text": page.translated_text,
            "translated_elements": [
                e.translated_text for e in page.elements
            ],
        }
        self._checkpoint_path().write_text(
            json.dumps(current, ensure_ascii=False, indent=2)
        )
