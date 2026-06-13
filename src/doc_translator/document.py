"""统一数据模型。"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class ContentElement(BaseModel):
    """页面内的单一元素：段落、表格或图片。"""

    type: str  # "paragraph" | "table" | "image"
    text: str = ""
    translated_text: str = ""
    image_data: Optional[bytes] = None
    image_ext: Optional[str] = None  # "png", "jpeg" etc.
    table_rows: Optional[list[list[str]]] = None
    meta: dict = Field(default_factory=dict)  # 格式元数据


class Page(BaseModel):
    """一页内容。"""

    page_number: int
    elements: list[ContentElement] = Field(default_factory=list)
    native_text: str = ""
    translated_text: str = ""
    is_scanned: bool = False


class Document(BaseModel):
    """统一的输入文档内部表示。"""

    source_path: str
    source_type: str  # "docx" | "pdf"
    pages: list[Page] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
