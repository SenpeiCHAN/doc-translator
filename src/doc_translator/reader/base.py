"""Reader 抽象基类。"""

from abc import ABC, abstractmethod

from doc_translator.document import Document


class BaseReader(ABC):

    @abstractmethod
    def read(self, path: str) -> Document:
        ...
