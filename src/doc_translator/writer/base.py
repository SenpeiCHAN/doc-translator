"""Writer 抽象基类。"""

from abc import ABC, abstractmethod

from doc_translator.document import Document


class BaseWriter(ABC):

    @abstractmethod
    def write(self, document: Document, output_path: str) -> None:
        ...
