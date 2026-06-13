"""CLI 入口。"""

from __future__ import annotations

import argparse
import logging
import sys

from doc_translator.config import Config
from doc_translator.document import Document
from doc_translator.reader.docx_reader import DocxReader
from doc_translator.reader.pdf_reader import PdfReader
from doc_translator.translator import Translator
from doc_translator.vocabulary import extract_vocabulary
from doc_translator.writer.docx_writer import DocxWriter
from doc_translator.writer.markdown_writer import MarkdownWriter

logger = logging.getLogger("doc_translator")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="doc-translator",
        description="Mac 文档翻译器：将 Word/PDF 逐页翻译为中文，调用 DeepSeek API",
    )

    p.add_argument(
        "--input", "-i",
        required=True, nargs="+",
        help="输入 .docx / .pdf 文件路径",
    )

    p.add_argument(
        "--output-dir", "-o",
        default=None,
        help="输出目录（默认 ./translated/）",
    )
    p.add_argument(
        "--format", "-f",
        choices=["docx", "md"], default=None,
        help="输出格式（默认 docx）",
    )

    p.add_argument(
        "--model",
        default=None,
        help="DeepSeek 模型名（默认 deepseek-chat）",
    )
    p.add_argument(
        "--api-base-url",
        default=None,
        help="API base URL（默认 https://api.deepseek.com）",
    )
    p.add_argument(
        "--api-key",
        default=None,
        help="DeepSeek API key（默认 $DEEPSEEK_API_KEY）",
    )

    p.add_argument(
        "--chars-per-page",
        type=int, default=None,
        help="DOCX 每页近似字符数（默认 3000）",
    )
    p.add_argument(
        "--workers", "-w",
        type=int, default=None,
        help="并发翻译 worker 数（默认 3）",
    )
    p.add_argument(
        "--temperature",
        type=float, default=None,
        help="翻译温度 0.0-1.0（默认 0.1）",
    )

    p.add_argument(
        "--ocr-force",
        action="store_true", default=None,
        help="强制对 PDF 使用 OCR",
    )
    p.add_argument(
        "--ocr-engine",
        choices=["tesseract", "paddle"], default=None,
        help="OCR 引擎（默认 tesseract）",
    )

    p.add_argument(
        "--no-vocabulary",
        action="store_true", default=None,
        help="跳过术语表生成",
    )

    p.add_argument(
        "--dry-run",
        action="store_true", default=None,
        help="仅解析文档并计算页数，不调用 API",
    )

    p.add_argument(
        "--verbose", "-v",
        action="store_true", default=None,
        help="详细日志",
    )
    p.add_argument(
        "--quiet", "-q",
        action="store_true", default=None,
        help="静默输出",
    )

    return p


def setup_logging(config: Config) -> None:
    level = logging.DEBUG if config.verbose else (
        logging.WARNING if config.quiet else logging.INFO
    )
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def resolve_reader(file_path: str, config: Config):
    ext = file_path.rsplit(".", 1)[-1].lower()
    if ext == "docx":
        return DocxReader(chars_per_page=config.chars_per_page)
    elif ext == "pdf":
        return PdfReader(
            ocr_engine=config.ocr_engine,
            ocr_force=config.ocr_force,
        )
    raise ValueError(f"不支持的文件格式: .{ext}（仅支持 .docx / .pdf）")


def resolve_writer(config: Config):
    fmt = config.output_format
    if fmt == "docx":
        return DocxWriter()
    elif fmt == "md":
        return MarkdownWriter()
    raise ValueError(f"不支持的输出格式: {fmt}")


def translate_one(
    file_path: str,
    config: Config,
    translator: Translator | None,
) -> Document:
    logger.info("解析文档: %s", file_path)
    reader = resolve_reader(file_path, config)
    document = reader.read(file_path)

    logger.info(
        "解析完成: %d 页, %d 元素",
        len(document.pages),
        sum(len(p.elements) for p in document.pages),
    )

    if config.dry_run:
        logger.info("（dry-run 模式，跳过翻译）")
        return document

    if translator is None:
        translator = Translator(config)

    document = translator.translate_document(document)

    if not config.no_vocabulary:
        extract_vocabulary(document, config, translator.client)

    return document


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config = Config.from_env_and_args(
        api_key=args.api_key,
        api_base_url=args.api_base_url,
        model=args.model,
        output_dir=args.output_dir,
        output_format=args.format,
        chars_per_page=args.chars_per_page,
        workers=args.workers,
        temperature=args.temperature,
        ocr_engine=args.ocr_engine,
        ocr_force=args.ocr_force,
        no_vocabulary=args.no_vocabulary,
        dry_run=args.dry_run,
        verbose=args.verbose,
        quiet=args.quiet,
        input_files=args.input,
    )

    setup_logging(config)

    if not config.api_key and not config.dry_run:
        print(
            "错误：未设置 DeepSeek API key。\n"
            "请设置环境变量 DEEPSEEK_API_KEY 或使用 --api-key 参数。\n"
            "（可使用 --dry-run 仅解析文档，无需 API key）",
            file=sys.stderr,
        )
        sys.exit(1)

    out_dir = config.resolve_output_dir()

    translator = None
    if not config.dry_run:
        translator = Translator(config)

    for file_path in config.input_files:
        try:
            document = translate_one(file_path, config, translator)

            src_name = file_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            src_ext = file_path.rsplit("/", 1)[-1].rsplit(".", 1)[-1]
            ext = "docx" if config.output_format == "docx" else "md"
            out_path = out_dir / f"{src_name}_{src_ext}_zh.{ext}"
            writer = resolve_writer(config)
            writer.write(document, str(out_path))

            logger.info("输出已保存: %s", out_path)
            print(f"✅ 翻译完成: {out_path}")

            vocab = document.metadata.get("vocabulary", [])
            if vocab:
                print(f"📝 术语表: {len(vocab)} 个术语")

        except Exception as exc:
            logger.error("处理 %s 时出错: %s", file_path, exc)
            if config.verbose:
                import traceback
                traceback.print_exc()
            print(f"❌ 翻译失败: {file_path} — {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
