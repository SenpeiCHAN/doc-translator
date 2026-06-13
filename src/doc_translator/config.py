"""配置加载：CLI > 环境变量 > .env > 默认值。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    api_key: str = ""
    api_base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    output_dir: str = "./translated"
    output_format: str = "docx"  # "docx" | "md"
    chars_per_page: int = 3000
    workers: int = 3
    temperature: float = 0.1
    ocr_engine: str = "tesseract"
    ocr_force: bool = False
    no_vocabulary: bool = False
    dry_run: bool = False
    verbose: bool = False
    quiet: bool = False
    input_files: list[str] = field(default_factory=list)

    @classmethod
    def from_env_and_args(cls, **overrides) -> Config:
        load_dotenv()

        cfg = cls(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            api_base_url=os.getenv(
                "DEEPSEEK_API_BASE_URL", "https://api.deepseek.com"
            ),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            output_dir=os.getenv("DOC_TRANSLATOR_OUTPUT_DIR", "./translated"),
            chars_per_page=int(
                os.getenv("DOC_TRANSLATOR_CHARS_PER_PAGE", "3000")
            ),
            workers=int(os.getenv("DOC_TRANSLATOR_WORKERS", "3")),
        )

        for key, val in overrides.items():
            if val is not None and hasattr(cfg, key):
                setattr(cfg, key, val)

        return cfg

    def resolve_output_dir(self) -> Path:
        path = Path(self.output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
