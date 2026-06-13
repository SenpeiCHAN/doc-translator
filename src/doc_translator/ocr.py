"""OCR 模块：Tesseract / PaddleOCR 封装。"""

from __future__ import annotations

import logging
import shutil
import subprocess

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

TESSERACT_LANGS = "chi_sim+eng"


def tesseract_available() -> bool:
    """检查 Tesseract 是否安装并包含中文语言包。"""
    if not shutil.which("tesseract"):
        return False
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True, text=True, timeout=5,
        )
        return "chi_sim" in result.stdout
    except Exception:
        return False


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """OCR 前预处理：灰度、对比度增强、锐化、自适应阈值二值化。"""
    image = image.convert("L")
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = image.filter(ImageFilter.SHARPEN)
    image = image.point(lambda x: 255 if x > 140 else 0)
    return image


def ocr_image_tesseract(image: Image.Image) -> str:
    """对单张 PIL Image 执行 Tesseract OCR。"""
    processed = preprocess_for_ocr(image)
    import pytesseract

    text = pytesseract.image_to_string(
        processed, lang=TESSERACT_LANGS, config="--psm 6"
    )
    return text.strip()


def ocr_image_paddle(image: Image.Image) -> str:
    """使用 PaddleOCR（如果可用）对单张图片执行 OCR。"""
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        logger.error("PaddleOCR 未安装，使用 pip install paddleocr paddlepaddle")
        raise

    ocr = PaddleOCR(lang="ch", use_angle_cls=True, show_log=False)
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        image.save(f.name)
        tmp_path = f.name

    try:
        result = ocr.ocr(tmp_path, cls=True)
        if not result or not result[0]:
            return ""
        lines = [line[1][0] for line in result[0]]
        return "\n".join(lines)
    finally:
        os.unlink(tmp_path)
