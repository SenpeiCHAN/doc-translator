"""Markdown 输出写入器。"""

from __future__ import annotations

from pathlib import Path

from doc_translator.document import ContentElement, Document
from doc_translator.writer.base import BaseWriter


class MarkdownWriter(BaseWriter):

    def write(self, document: Document, output_path: str) -> None:
        out_path = Path(output_path)
        out_dir = out_path.parent
        img_dir = out_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        img_counter = 0

        for page in document.pages:
            for elem in page.elements:
                if elem.type == "paragraph":
                    text = elem.translated_text or elem.text
                    if text:
                        lines.append(text)
                        lines.append("")

                elif elem.type == "table":
                    self._write_md_table(lines, elem)

                elif elem.type == "image" and elem.image_data:
                    img_counter += 1
                    img_path = self._save_image(elem, img_dir, img_counter)
                    if img_path:
                        lines.append(f"![图片](images/{img_path.name})")
                        lines.append("")

        vocab = document.metadata.get("vocabulary")
        if vocab:
            lines.append("## 术语表 / Vocabulary")
            lines.append("")
            lines.append("| English Term | 中文翻译 | 备注 |")
            lines.append("| --- | --- | --- |")
            for entry in vocab:
                en = (entry.get("en") or "").replace("|", "\\|")
                zh = (entry.get("zh") or "").replace("|", "\\|")
                notes = (entry.get("notes") or "").replace("|", "\\|")
                lines.append(f"| {en} | {zh} | {notes} |")
            lines.append("")

        out_path.write_text("\n".join(lines), encoding="utf-8")

    def _write_md_table(self, lines: list[str], elem: ContentElement) -> None:
        rows = elem.table_rows
        if not rows:
            return

        max_cols = max(len(r) for r in rows)
        header = rows[0].copy()
        while len(header) < max_cols:
            header.append("")

        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        for row in rows[1:]:
            r = row.copy()
            while len(r) < max_cols:
                r.append("")
            lines.append("| " + " | ".join(r) + " |")
        lines.append("")

    def _save_image(
        self, elem: ContentElement, img_dir: Path, counter: int,
    ) -> Path | None:
        ext = elem.image_ext or "png"
        img_path = img_dir / f"img_{counter}.{ext}"
        try:
            img_path.write_bytes(elem.image_data)
            return img_path
        except Exception:
            return None
