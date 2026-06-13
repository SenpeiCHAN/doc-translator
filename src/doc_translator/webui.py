"""Web 前端 — Gradio 界面。"""

from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path

import gradio as gr

from doc_translator.config import Config
from doc_translator.reader.docx_reader import DocxReader
from doc_translator.reader.pdf_reader import PdfReader
from doc_translator.translator import Translator
from doc_translator.vocabulary import extract_vocabulary
from doc_translator.writer.docx_writer import DocxWriter
from doc_translator.writer.markdown_writer import MarkdownWriter


def translate_file(
    file_obj,
    api_key: str,
    output_format: str,
    model: str,
    api_base_url: str,
    chars_per_page: int,
    temperature: float,
    workers: int,
    ocr_force: bool,
    no_vocabulary: bool,
    progress=gr.Progress(),
):
    if not file_obj:
        return "请先上传文件", None

    if not api_key.strip():
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key.strip():
        yield "错误：请设置 API Key", None, None
        return

    input_path = file_obj.name
    ext = input_path.rsplit(".", 1)[-1].lower()
    if ext not in ("docx", "pdf"):
        yield f"不支持的文件格式: .{ext}（仅支持 .docx / .pdf）", None, None
        return

    config = Config(
        api_key=api_key.strip(),
        api_base_url=api_base_url.strip() or "https://api.deepseek.com",
        model=model.strip() or "deepseek-chat",
        output_dir="./translated",
        output_format=output_format,
        chars_per_page=chars_per_page,
        temperature=temperature,
        workers=workers,
        ocr_force=ocr_force,
        no_vocabulary=no_vocabulary,
        verbose=False,
        quiet=True,
    )

    yield "正在解析文档...", None, None

    try:
        if ext == "docx":
            reader = DocxReader(chars_per_page=config.chars_per_page)
        else:
            reader = PdfReader(
                ocr_engine=config.ocr_engine, ocr_force=config.ocr_force,
            )
        document = reader.read(input_path)

        pages = len(document.pages)
        elements = sum(len(p.elements) for p in document.pages)
        yield f"解析完成：{pages} 页, {elements} 个元素。开始翻译...", None, None

        translator = Translator(config)
        document = translator.translate_document(document)

        yield "翻译完成，正在生成输出...", None, None

        out_dir = Path(config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        src_name = input_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        out_ext = "docx" if output_format == "docx" else "md"
        out_path = out_dir / f"{src_name}_{ext}_zh.{out_ext}"

        if output_format == "docx":
            DocxWriter().write(document, str(out_path))
        else:
            MarkdownWriter().write(document, str(out_path))

        vocab_text = ""
        if not no_vocabulary:
            try:
                extract_vocabulary(document, config, translator.client)
                vocab = document.metadata.get("vocabulary", [])
                if vocab:
                    vocab_lines = ["## 术语表 / Vocabulary\n"]
                    for entry in vocab:
                        en = entry.get("en", "")
                        zh = entry.get("zh", "")
                        notes = entry.get("notes", "")
                        line = f"- **{en}** → {zh}"
                        if notes:
                            line += f" _(备注: {notes})_"
                        vocab_lines.append(line)
                    vocab_text = "\n".join(vocab_lines)
            except Exception:
                pass

        yield f"✅ 翻译完成！输出: {out_path.name}", str(out_path), vocab_text

    except Exception as exc:
        tb = traceback.format_exc()
        yield f"❌ 出错: {exc}\n\n```\n{tb}\n```", None, None


def build_ui():
    with gr.Blocks(title="Mac 文档翻译器", theme=gr.themes.Soft()) as app:
        gr.Markdown("""
        # 📄 Mac 文档翻译器

        将 Word (.docx) 和 PDF 文件逐页翻译为简体中文，调用 **DeepSeek API**。
        保留原文格式、图片、表格，翻译后自动生成术语表。
        """)

        with gr.Row():
            with gr.Column(scale=2):
                file_input = gr.File(
                    label="上传文档",
                    file_types=[".docx", ".pdf"],
                )

                with gr.Row():
                    api_key = gr.Textbox(
                        label="DeepSeek API Key",
                        type="password",
                        placeholder="sk-... 或设置环境变量 DEEPSEEK_API_KEY",
                        value=os.getenv("DEEPSEEK_API_KEY", ""),
                    )

                with gr.Row():
                    api_base_url = gr.Textbox(
                        label="API Base URL",
                        value="https://api.deepseek.com",
                    )
                    model = gr.Textbox(
                        label="模型名称",
                        value="deepseek-chat",
                    )

                with gr.Row():
                    output_format = gr.Radio(
                        label="输出格式",
                        choices=["docx", "md"],
                        value="docx",
                    )

                with gr.Accordion("高级选项", open=False):
                    chars_per_page = gr.Slider(
                        label="每页近似字符数",
                        minimum=500, maximum=10000, value=3000, step=500,
                    )
                    temperature = gr.Slider(
                        label="翻译温度",
                        minimum=0.0, maximum=1.0, value=0.1, step=0.05,
                    )
                    workers = gr.Slider(
                        label="并发 Worker 数",
                        minimum=1, maximum=10, value=3, step=1,
                    )
                    ocr_force = gr.Checkbox(
                        label="强制 OCR（扫描件 PDF）", value=False,
                    )
                    no_vocabulary = gr.Checkbox(
                        label="跳过术语表", value=False,
                    )

                btn = gr.Button("开始翻译", variant="primary", size="lg")

            with gr.Column(scale=3):
                status = gr.Markdown("等待上传文件...")
                download = gr.File(label="下载翻译结果", visible=True)
                vocab_display = gr.Markdown("")

        btn.click(
            fn=translate_file,
            inputs=[
                file_input, api_key, output_format, model, api_base_url,
                chars_per_page, temperature, workers,
                ocr_force, no_vocabulary,
            ],
            outputs=[status, download, vocab_display],
        )

        gr.Markdown("""
        ---
        ### 使用说明

        1. 上传 `.docx` 或 `.pdf` 文件
        2. 填写 DeepSeek API Key（或设置环境变量 `DEEPSEEK_API_KEY`）
        3. 选择输出格式（Word 或 Markdown）
        4. 点击「开始翻译」
        5. 下载翻译结果

        ### 前置依赖（仅扫描件 PDF OCR 需要）

        ```bash
        brew install tesseract tesseract-lang poppler
        ```

        ### 命令行用法

        ```bash
        doc-translator -i document.docx --format docx --dry-run
        ```
        """)

    return app


def main():
    app = build_ui()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=True,
    )


if __name__ == "__main__":
    main()
