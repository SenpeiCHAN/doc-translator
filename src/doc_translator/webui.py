"""Web 前端 — Gradio 界面（模型选择 + 翻译预览 + 进度预估）。"""

from __future__ import annotations

import os
import time
import threading
from pathlib import Path
from datetime import timedelta

import gradio as gr

from doc_translator.config import Config
from doc_translator.reader.docx_reader import DocxReader
from doc_translator.reader.pdf_reader import PdfReader
from doc_translator.translator import Translator
from doc_translator.vocabulary import extract_vocabulary
from doc_translator.writer.docx_writer import DocxWriter
from doc_translator.writer.markdown_writer import MarkdownWriter

MODEL_OPTIONS = ["deepseek-chat", "deepseek-v4-flash"]

# 全局状态用于线程间通信
_state_lock = threading.Lock()
_current_progress = {"done": 0, "total": 0, "start_time": 0}
_live_preview = ""


def _translate_in_thread(
    input_path: str,
    config: Config,
    ext: str,
    no_vocabulary: bool,
    result_holder: dict,
):
    """在后台线程中执行翻译，实时更新进度。"""
    global _current_progress, _live_preview

    try:
        if ext == "docx":
            reader = DocxReader(chars_per_page=config.chars_per_page)
        else:
            reader = PdfReader(
                ocr_engine=config.ocr_engine,
                ocr_force=config.ocr_force,
            )
        document = reader.read(input_path)

        total_pages = len(document.pages)
        with _state_lock:
            _current_progress = {
                "done": 0,
                "total": total_pages,
                "start_time": time.time(),
            }

        # 创建一个回调钩子，在每页翻译完成后更新预览
        original_translate = Translator(config)

        # Patch the translate_document method to update progress
        orig_translate_doc = original_translate.translate_document

        def patched_translate(doc):
            from concurrent.futures import ThreadPoolExecutor, as_completed

            total = len(doc.pages)
            original_translate.checkpoint_dir = (
                Path(config.output_dir)
                / ".progress"
                / Path(doc.source_path).stem
            )
            original_translate.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            completed = original_translate._load_checkpoint()

            # Restore completed pages
            for p in doc.pages:
                if p.page_number in completed:
                    cached = completed[p.page_number]
                    p.translated_text = cached["translated_text"]
                    for j, t in enumerate(cached.get("translated_elements", [])):
                        if j < len(p.elements):
                            p.elements[j].translated_text = t

            pending = [p for p in doc.pages if p.page_number not in completed]

            if not pending:
                return doc

            with ThreadPoolExecutor(max_workers=config.workers) as pool:
                futures = {}
                for p in pending:
                    futures[
                        pool.submit(original_translate._translate_page, p, p.page_number)
                    ] = p

                for future in as_completed(futures):
                    page = futures[future]
                    try:
                        future.result()
                        original_translate._save_checkpoint(page)
                        with _state_lock:
                            _current_progress["done"] += 1
                            # 实时更新预览
                            text_parts = []
                            for p in doc.pages:
                                if p.translated_text:
                                    text_parts.append(f"### 第 {p.page_number} 页\n\n{p.translated_text}")
                            _live_preview = "\n\n---\n\n".join(text_parts)
                    except Exception:
                        with _state_lock:
                            _current_progress["done"] += 1

            return doc

        document = patched_translate(document)

        # 生成输出
        out_dir = Path(config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        src_name = input_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        out_ext = "docx" if config.output_format == "docx" else "md"
        out_path = out_dir / f"{src_name}_{ext}_zh.{out_ext}"

        if config.output_format == "docx":
            DocxWriter().write(document, str(out_path))
        else:
            MarkdownWriter().write(document, str(out_path))

        vocab_text = ""
        if not no_vocabulary:
            try:
                extract_vocabulary(document, config, original_translate.client)
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

        result_holder["status"] = "done"
        result_holder["out_path"] = str(out_path)
        result_holder["out_path_rel"] = out_path.name
        result_holder["vocab"] = vocab_text
        result_holder["preview"] = _live_preview

    except Exception as exc:
        import traceback
        result_holder["status"] = "error"
        result_holder["error"] = f"{exc}\n\n```\n{traceback.format_exc()}\n```"


def translate_file_async(
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
):
    """启动后台翻译线程，然后通过 yield 轮询进度。"""
    global _current_progress, _live_preview

    if not file_obj:
        yield "请先上传文件", "", None, "<span style='color:gray'>等待中...</span>"
        return

    if not api_key.strip():
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key.strip():
        yield "错误：请设置 API Key", "", None, "<span style='color:red'>缺少 API Key</span>"
        return

    input_path = file_obj.name
    ext = input_path.rsplit(".", 1)[-1].lower()
    if ext not in ("docx", "pdf"):
        yield (
            f"不支持的文件格式: .{ext}（仅支持 .docx / .pdf）",
            "", None, "<span style='color:red'>格式不支持</span>",
        )
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

    # 先解析文档
    yield "正在解析文档...", "", None, "<span style='color:gray'>解析中...</span>"

    try:
        if ext == "docx":
            reader = DocxReader(chars_per_page=config.chars_per_page)
        else:
            reader = PdfReader(
                ocr_engine=config.ocr_engine,
                ocr_force=config.ocr_force,
            )
        document = reader.read(input_path)
    except Exception as exc:
        yield (
            f"❌ 解析失败: {exc}",
            "", None, "<span style='color:red'>解析失败</span>",
        )
        return

    total_pages = len(document.pages)
    _live_preview = ""
    _current_progress = {"done": 0, "total": total_pages, "start_time": time.time()}

    result_holder = {}
    thread = threading.Thread(
        target=_translate_in_thread,
        args=(input_path, config, ext, no_vocabulary, result_holder),
        daemon=True,
    )
    thread.start()

    # 轮询进度
    last_done = -1
    while thread.is_alive():
        with _state_lock:
            done = _current_progress["done"]
            total = _current_progress["total"]
            elapsed = time.time() - _current_progress["start_time"]

        if done > last_done and done > 0:
            last_done = done
            elapsed_str = str(timedelta(seconds=int(elapsed)))
            if done > 1:
                eta_seconds = int(elapsed / done * (total - done))
                eta_str = str(timedelta(seconds=eta_seconds))
                progress_line = (
                    f"⏳ 翻译中... {done}/{total} 页 "
                    f"（已用时 {elapsed_str}，预计剩余 {eta_str}）"
                )
            else:
                progress_line = f"⏳ 翻译中... {done}/{total} 页（已用时 {elapsed_str}，正在估算...）"

            with _state_lock:
                preview = _live_preview

            preview_md = preview if preview else "*翻译内容将在此处实时展示...*"

            yield progress_line, preview_md, None, _build_progress_bar(done, total)

        time.sleep(1.5)

    thread.join()

    if result_holder.get("status") == "error":
        yield (
            f"❌ 出错: {result_holder.get('error', '')}",
            "", None, "<span style='color:red'>翻译失败</span>",
        )
        return

    out_path = result_holder.get("out_path", "")
    out_name = result_holder.get("out_path_rel", "")
    vocab = result_holder.get("vocab", "")
    preview = result_holder.get("preview", "")

    done_str = f"✅ 翻译完成！共 {total_pages} 页"
    elapsed = str(timedelta(seconds=int(time.time() - _current_progress["start_time"])))

    yield (
        f"{done_str}\n输出文件: {out_name}\n总用时: {elapsed}",
        preview if preview else "*无翻译内容*",
        out_path if os.path.exists(out_path) else None,
        _build_progress_bar(total_pages, total_pages, True),
    )


def _build_progress_bar(done: int, total: int, complete: bool = False) -> str:
    pct = int(done / total * 100) if total > 0 else 0
    bar_len = 20
    filled = int(bar_len * pct / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    color = "#22c55e" if complete else "#3b82f6"
    return (
        f"<div style='font-family:monospace;background:#1e1e2e;padding:8px 12px;"
        f"border-radius:6px;color:#e0e0e0'>"
        f"<span style='color:{color}'>{bar}</span>"
        f"<span style='margin-left:8px;font-weight:bold;color:#f0f0f0'>{pct}%</span>"
        f"<span style='color:#888'>（{done}/{total} 页）</span>"
        f"</div>"
    )


def build_ui():
    css = """
    .progress-wrap { margin: 8px 0; }
    .preview-box { max-height: 600px; overflow-y: auto; }
    """
    with gr.Blocks(title="Mac 文档翻译器", css=css) as app:
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

                api_key = gr.Textbox(
                    label="DeepSeek API Key",
                    type="password",
                    placeholder="sk-... 或设置环境变量 DEEPSEEK_API_KEY",
                    value=os.getenv("DEEPSEEK_API_KEY", ""),
                )

                with gr.Row():
                    model = gr.Dropdown(
                        label="模型选择",
                        choices=MODEL_OPTIONS,
                        value="deepseek-chat",
                        interactive=True,
                    )
                    api_base_url = gr.Textbox(
                        label="API Base URL",
                        value="https://api.deepseek.com",
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
                gr.Markdown("**📊 翻译进度**")
                progress_bar = gr.HTML(
                    "<span style='color:gray'>等待上传文件...</span>"
                )
                status = gr.Markdown("")

                with gr.Accordion("📖 翻译预览（实时更新）", open=True):
                    preview_md = gr.Markdown(
                        "*上传文件并开始翻译后，翻译内容将在此处逐页显示...*",
                        elem_classes=["preview-box"],
                    )

                download = gr.File(label="📥 下载翻译结果", visible=True)
                vocab_display = gr.Markdown("")

        btn.click(
            fn=translate_file_async,
            inputs=[
                file_input, api_key, output_format, model, api_base_url,
                chars_per_page, temperature, workers,
                ocr_force, no_vocabulary,
            ],
            outputs=[status, preview_md, download, progress_bar],
        )

        gr.Markdown("""
        ---
        ### 使用说明

        1. 上传 `.docx` 或 `.pdf` 文件
        2. 填写 DeepSeek API Key（或设置环境变量 `DEEPSEEK_API_KEY`）
        3. 选择模型（`deepseek-chat` = V4 Pro，`deepseek-v4-flash` = 快速版）
        4. 选择输出格式（Word 或 Markdown）
        5. 点击「开始翻译」，实时预览翻译进度
        6. 下载翻译结果

        ### 前置依赖（仅扫描件 PDF OCR 需要）

        ```bash
        brew install tesseract tesseract-lang poppler
        ```

        ### 命令行用法

        ```bash
        doc-translator -i document.docx --model deepseek-v4-flash --format docx
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
