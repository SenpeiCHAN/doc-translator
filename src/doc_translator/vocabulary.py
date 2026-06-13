"""词汇表：翻译后通过 DeepSeek API 提取专有名词和领域术语。"""

from __future__ import annotations

import json
import logging
import re

from doc_translator.config import Config
from doc_translator.document import Document

logger = logging.getLogger(__name__)

VOCAB_SYSTEM = """You are a terminologist specializing in Chinese-English technical translation.

Given the English source text and its Chinese translation, extract all domain-specific terms,
technical jargon, proper nouns, and abbreviations that are important for understanding the document.

For each term, provide:
1. "en": The English term
2. "zh": The Chinese translation used in the document
3. "notes": Any notes on the translation choice (if no special notes, use "").

Rules:
- Include only terms that are domain-specific, technical, or proper nouns.
- Do NOT include common everyday words.
- Do NOT include duplicate terms.
- Terms should appear in alphabetical order by English.

Respond as a JSON array only, no other text:
[{"en": "...", "zh": "...", "notes": "..."}, ...]"""


def extract_vocabulary(
    document: Document, config: Config, client: object = None
) -> list[dict]:
    source_parts: list[str] = []
    translated_parts: list[str] = []

    for page in document.pages:
        for elem in page.elements:
            if elem.type in ("paragraph", "table") and elem.text:
                source_parts.append(elem.text)
                translated_parts.append(
                    elem.translated_text or elem.text
                )

    if not source_parts:
        logger.warning("无可提取术语的文本")
        document.metadata["vocabulary"] = []
        return []

    source_text = "\n\n".join(source_parts[:50])
    translated_text = "\n\n".join(translated_parts[:50])

    user_message = (
        "SOURCE TEXT:\n"
        f"{source_text[:12000]}\n\n"
        "TRANSLATED TEXT:\n"
        f"{translated_text[:12000]}"
    )

    if client is None:
        from openai import OpenAI
        client = OpenAI(
            api_key=config.api_key,
            base_url=config.api_base_url,
        )

    logger.info("正在提取术语表...")
    try:
        response = client.chat.completions.create(
            model=config.model,
            temperature=0.3,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": VOCAB_SYSTEM},
                {"role": "user", "content": user_message},
            ],
        )
        raw = response.choices[0].message.content or "[]"
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        terms = json.loads(raw)
        logger.info("术语表提取完成，共 %d 个术语", len(terms))
    except Exception as exc:
        logger.warning("术语提取失败: %s", exc)
        terms = []

    document.metadata["vocabulary"] = terms
    return terms
