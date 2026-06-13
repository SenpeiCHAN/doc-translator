"""Token 估算（tiktoken）。"""

import tiktoken

_ENCODING = None


def _get_encoding():
    global _ENCODING
    if _ENCODING is None:
        _ENCODING = tiktoken.get_encoding("cl100k_base")
    return _ENCODING


def count_tokens(text: str) -> int:
    enc = _get_encoding()
    return len(enc.encode(text))
