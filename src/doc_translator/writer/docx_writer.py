"""DOCX 输出写入器：保留格式、图片、表格。"""

from __future__ import annotations

from io import BytesIO

from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from doc_translator.document import Document
from doc_translator.writer.base import BaseWriter

# 支持中文的系统字体列表
CN_FONTS = {
    "pingfang sc", "microsoft yahei", "simsun",
    "noto sans cjk", "source han sans", "heiti sc",
}

ALIGN_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "both": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


class DocxWriter(BaseWriter):

    def write(self, document: Document, output_path: str) -> None:
        out = DocxDocument()

        for page in document.pages:
            self._write_page(out, page)

        self._write_vocabulary(out, document)

        out.save(output_path)

    def _write_page(self, out: DocxDocument, page) -> None:
        for elem in page.elements:
            if elem.type == "paragraph":
                self._write_paragraph(out, elem)
            elif elem.type == "table":
                self._write_table(out, elem)
            elif elem.type == "image" and elem.image_data:
                try:
                    stream = BytesIO(elem.image_data)
                    out.add_picture(stream)
                except Exception:
                    pass

    def _write_paragraph(self, out: DocxDocument, elem) -> None:
        para = out.add_paragraph()
        meta = elem.meta or {}

        # 对齐方式
        align_str = meta.get("alignment")
        if align_str and align_str in ALIGN_MAP:
            para.alignment = ALIGN_MAP[align_str]

        text = elem.translated_text or elem.text
        runs_meta = meta.get("runs", [])

        if runs_meta:
            # 逐 run 重建
            for i, run_meta in enumerate(runs_meta):
                if run_meta.get("is_image"):
                    continue
                run = para.add_run(run_meta.get("text", ""))
                if i == 0 and elem.translated_text:
                    run.text = elem.translated_text
                self._apply_font(run, run_meta.get("font", {}))
        else:
            run = para.add_run(text)
            self._apply_font(run, {})

    def _apply_font(self, run, font_meta: dict) -> None:
        name = font_meta.get("name")
        if name:
            run.font.name = name
        else:
            run.font.name = "PingFang SC"

        size = font_meta.get("size")
        if size:
            run.font.size = Pt(int(size) / 2)

        bold = font_meta.get("bold")
        if bold is not None:
            run.font.bold = bold

        italic = font_meta.get("italic")
        if italic is not None:
            run.font.italic = italic

        color = font_meta.get("color")
        if color:
            from docx.shared import RGBColor
            try:
                run.font.color.rgb = RGBColor.from_string(color)
            except Exception:
                pass

    def _write_table(self, out: DocxDocument, elem) -> None:
        rows = elem.table_rows
        if not rows:
            return

        num_cols = max(len(r) for r in rows) if rows else 1
        table = out.add_table(rows=len(rows), cols=num_cols)
        table.style = "Table Grid"

        for i, row_data in enumerate(rows):
            for j, cell_text in enumerate(row_data):
                if j < num_cols:
                    table.cell(i, j).text = cell_text

    def _write_vocabulary(self, out: DocxDocument, document) -> None:
        vocab = document.metadata.get("vocabulary")
        if not vocab:
            return

        out.add_page_break()
        heading = out.add_heading("术语表 / Vocabulary", level=1)

        table = out.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text = "English Term"
        hdr[1].text = "中文翻译"
        hdr[2].text = "备注"

        for entry in vocab:
            row = table.add_row().cells
            row[0].text = entry.get("en", "")
            row[1].text = entry.get("zh", "")
            row[2].text = entry.get("notes", "")
