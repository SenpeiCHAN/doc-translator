"""DOCX 阅读器：有序提取段落/表格/图片，保留格式元数据，按字符数分页桶。"""

from __future__ import annotations

import logging

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from lxml import etree

from doc_translator.document import ContentElement, Document, Page
from doc_translator.reader.base import BaseReader

logger = logging.getLogger(__name__)

NSMAP = {
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}

IMAGE_PLACEHOLDER = "[图片]"


class DocxReader(BaseReader):

    def __init__(self, chars_per_page: int = 3000):
        self.chars_per_page = chars_per_page
        self._doc: DocxDocument | None = None

    def read(self, path: str) -> Document:
        self._doc = DocxDocument(path)
        all_elements: list[ContentElement] = []

        for item in self._doc.element.body:
            tag = etree.QName(item).localname if isinstance(item.tag, str) else None
            if tag == "p":
                self._handle_paragraph(item, all_elements)
            elif tag == "tbl":
                elem = self._parse_table(item)
                if elem is not None:
                    all_elements.append(elem)
            elif tag == "sdt":
                self._handle_sdt(item, all_elements)

        pages = self._bucket_into_pages(all_elements)
        return Document(source_path=path, source_type="docx", pages=pages)

    def _handle_paragraph(self, para_elem, all_elements: list[ContentElement]) -> None:
        text_parts: list[str] = []
        meta: dict = {"alignment": None, "runs": []}
        standalone_images: list[ContentElement] = []

        pPr = para_elem.find(qn("w:pPr"))
        if pPr is not None:
            jc = pPr.find(qn("w:jc"))
            if jc is not None:
                meta["alignment"] = jc.get(qn("w:val"))

        for child in para_elem:
            child_tag = etree.QName(child).localname if isinstance(child.tag, str) else None
            if child_tag == "r":
                self._process_run(child, text_parts, meta["runs"], standalone_images)
            elif child_tag in ("hyperlink",):
                for sub in child:
                    if isinstance(sub.tag, str) and etree.QName(sub).localname == "r":
                        self._process_run(sub, text_parts, meta["runs"], standalone_images)

        text = "".join(text_parts).strip()

        if standalone_images:
            all_elements.extend(standalone_images)

        if not text and not meta["runs"] and not standalone_images:
            return

        if text or meta["runs"]:
            all_elements.append(ContentElement(
                type="paragraph", text=text, meta=meta,
            ))

    def _process_run(
        self, run_elem, text_parts: list[str],
        runs: list[dict], images: list[ContentElement],
    ) -> None:
        has_text = False
        for t in run_elem.findall(qn("w:t")):
            if t.text:
                text_parts.append(t.text)
                has_text = True

        # 图片检测
        drawings = run_elem.findall(qn("w:drawing"))
        for drawing in drawings:
            blips = drawing.findall(".//a:blip", NSMAP)
            for blip in blips:
                rId = blip.get(qn("r:embed"))
                if rId:
                    blob, ext = self._extract_image(rId)
                    if blob:
                        images.append(ContentElement(
                            type="image", image_data=blob, image_ext=ext,
                        ))
                        text_parts.append(IMAGE_PLACEHOLDER)
                        runs.append({
                            "text": IMAGE_PLACEHOLDER,
                            "is_image": True,
                            "font": {},
                        })

        if not has_text:
            if text_parts:
                runs.append({"text": text_parts[-1] if text_parts else "", "font": {}})
            return

        font_info = self._parse_font(run_elem)
        runs.append({"text": "".join(
            t.text for t in run_elem.findall(qn("w:t")) if t.text
        ), "font": font_info})

    def _parse_font(self, run_elem) -> dict:
        rPr = run_elem.find(qn("w:rPr"))
        font = {}
        if rPr is not None:
            rFonts = rPr.find(qn("w:rFonts"))
            if rFonts is not None:
                font["name"] = (
                    rFonts.get(qn("w:ascii"))
                    or rFonts.get(qn("w:eastAsia"))
                    or rFonts.get(qn("w:hAnsi"))
                )
            sz = rPr.find(qn("w:sz"))
            if sz is not None:
                font["size"] = sz.get(qn("w:val"))
            font["bold"] = rPr.find(qn("w:b")) is not None
            font["italic"] = rPr.find(qn("w:i")) is not None
            color = rPr.find(qn("w:color"))
            if color is not None:
                font["color"] = color.get(qn("w:val"))
        return font

    def _extract_image(self, rId: str) -> tuple[bytes | None, str]:
        try:
            part = self._doc.part.related_parts[rId]
            ext = part.partname.rsplit(".", 1)[-1] if "." in part.partname else "png"
            return part.blob, ext
        except Exception:
            return None, "png"

    def _handle_sdt(self, sdt_elem, all_elements: list[ContentElement]) -> None:
        for child in sdt_elem:
            tag = etree.QName(child).localname if isinstance(child.tag, str) else None
            if tag == "p":
                self._handle_paragraph(child, all_elements)
            elif tag == "tbl":
                elem = self._parse_table(child)
                if elem is not None:
                    all_elements.append(elem)

    def _parse_table(self, tbl_elem) -> ContentElement | None:
        rows: list[list[str]] = []
        for row_elem in tbl_elem.findall(qn("w:tr")):
            row: list[str] = []
            for cell_elem in row_elem.findall(qn("w:tc")):
                cell_texts: list[str] = []
                for p in cell_elem.findall(qn("w:p")):
                    for r in p.findall(qn("w:r")):
                        for t in r.findall(qn("w:t")):
                            if t.text:
                                cell_texts.append(t.text)
                row.append("".join(cell_texts))
            if row:
                rows.append(row)
        if not rows:
            return None
        return ContentElement(
            type="table",
            text="\n".join(" | ".join(r) for r in rows),
            table_rows=rows,
        )

    def _bucket_into_pages(self, elements: list[ContentElement]) -> list[Page]:
        pages: list[Page] = []
        bucket: list[ContentElement] = []
        char_count = 0
        page_num = 1

        for elem in elements:
            if elem.type == "image":
                bucket.append(elem)
                continue

            elem_chars = len(elem.text)
            if bucket and char_count + elem_chars > self.chars_per_page:
                pages.append(self._make_page(page_num, bucket))
                page_num += 1
                bucket = []
                char_count = 0

            bucket.append(elem)
            char_count += elem_chars

        if bucket:
            pages.append(self._make_page(page_num, bucket))
        return pages

    def _make_page(self, num: int, elements: list[ContentElement]) -> Page:
        text = "\n".join(
            e.text for e in elements
            if e.type in ("paragraph", "table") and e.text
        )
        return Page(page_number=num, elements=elements, native_text=text)
