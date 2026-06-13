"""PDF 阅读器：PyMuPDF 文本提取 + OCR 回退。"""

from __future__ import annotations

import logging

import fitz  # PyMuPDF
from PIL import Image

from doc_translator.document import ContentElement, Document, Page
from doc_translator.ocr import (
    ocr_image_tesseract,
    ocr_image_paddle,
    tesseract_available,
)
from doc_translator.reader.base import BaseReader

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 10


class PdfReader(BaseReader):

    def __init__(self, ocr_engine: str = "tesseract", ocr_force: bool = False):
        self.ocr_engine = ocr_engine
        self.ocr_force = ocr_force

    def read(self, path: str) -> Document:
        doc = fitz.open(path)
        pages: list[Page] = []

        for i in range(len(doc)):
            page = doc[i]
            native_text = page.get_text().strip()
            is_scanned = False
            elements: list[ContentElement] = []

            if self.ocr_force or len(native_text) < MIN_TEXT_LENGTH:
                is_scanned = True
                native_text = self._ocr_page(page)
                if native_text:
                    elements.append(ContentElement(
                        type="paragraph", text=native_text
                    ))
            else:
                elements = self._extract_elements(page)

            # 仅在非扫描模式且文本提取成功时提取图片
            if not is_scanned:
                elements = self._attach_images(page, elements)

            text_only = "\n".join(
                e.text for e in elements
                if e.type in ("paragraph", "table") and e.text
            )

            pages.append(Page(
                page_number=i + 1,
                elements=elements,
                native_text=text_only,
                is_scanned=is_scanned,
            ))

        doc.close()
        return Document(source_path=path, source_type="pdf", pages=pages)

    def _extract_elements(self, page: fitz.Page) -> list[ContentElement]:
        elements: list[ContentElement] = []
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block["type"] == 0:  # text block
                paragraphs: dict[int, list[str]] = {}
                for line in block.get("lines", []):
                    y = round(line["bbox"][1])
                    text = "".join(s["text"] for s in line.get("spans", []))
                    paragraphs.setdefault(y, []).append(text)
                for y in sorted(paragraphs):
                    full_text = " ".join(paragraphs[y]).strip()
                    if full_text:
                        elements.append(ContentElement(
                            type="paragraph",
                            text=full_text,
                            meta={"bbox": list(block["bbox"])},
                        ))

        return elements

    def _attach_images(
        self, page: fitz.Page, elements: list[ContentElement]
    ) -> list[ContentElement]:
        image_infos = page.get_images(full=True)
        for img_info in image_infos:
            try:
                xref = img_info[0]
                base_image = page.parent.extract_image(xref)
                elements.append(ContentElement(
                    type="image",
                    image_data=base_image["image"],
                    image_ext=base_image["ext"],
                ))
            except Exception as exc:
                logger.warning("PDF 图片提取失败: %s", exc)
        return elements

    def _ocr_page(self, page: fitz.Page) -> str:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        if self.ocr_engine == "paddle":
            return ocr_image_paddle(img)
        else:
            if not tesseract_available():
                logger.warning(
                    "Tesseract 未安装或缺少 chi_sim 语言包，"
                    "请执行: brew install tesseract tesseract-lang"
                )
                # 回退到 PyMuPDF 简单提取，避免崩溃
                text = page.get_text()
                return text.strip() if text else ""
            return ocr_image_tesseract(img)
