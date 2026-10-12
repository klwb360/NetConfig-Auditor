"""Lossless, bounded decoding for configuration imports; never guess by replacing bytes."""
from __future__ import annotations

import codecs
import unicodedata

MAX_CONFIG_BYTES = 2 * 1024 * 1024
ENCODINGS = ("auto", "utf-8", "gb18030", "gbk", "utf-16")
_BINARY_PREFIXES = (b"PK\x03\x04", b"PK\x05\x06", b"\x1f\x8b", b"%PDF-", b"\x89PNG", b"\xff\xd8\xff", b"MZ", b"\x7fELF")


def decode_config_bytes(data: bytes, encoding: str = "auto") -> tuple[str, str]:
    """Return original text (except its leading BOM) and the codec actually used.

    Auto detects UTF-8/UTF-16 BOMs, then tries strict UTF-8 and strict GB18030.
    UTF-16 requires a BOM to identify byte order; no lossy fallback or line
    ending normalization occurs.
    Errors contain no configuration bytes or text and can be displayed directly.
    """
    if not isinstance(data, bytes):
        raise ValueError("配置输入必须为字节")
    if encoding not in ENCODINGS:
        raise ValueError("编码必须为 auto / utf-8 / gb18030 / gbk / utf-16")
    if len(data) > MAX_CONFIG_BYTES:
        raise ValueError("配置超过 2 MiB 限制")
    if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)) or data.startswith(_BINARY_PREFIXES):
        raise ValueError("配置必须为文本，不能导入二进制文件")
    if encoding != "auto" and ((data.startswith(codecs.BOM_UTF8) and encoding != "utf-8") or
                                (data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) and encoding != "utf-16")):
        raise ValueError("指定编码与配置 BOM 不匹配，请选择正确编码")
    used = encoding
    raw = data
    try:
        if encoding in ("auto", "utf-8") and data.startswith(codecs.BOM_UTF8):
            used, raw = "utf-8-sig", data[len(codecs.BOM_UTF8):]
            text = raw.decode("utf-8")
        elif encoding in ("auto", "utf-16") and data.startswith(codecs.BOM_UTF16_LE):
            used, raw = "utf-16-le", data[len(codecs.BOM_UTF16_LE):]
            text = raw.decode(used)
        elif encoding in ("auto", "utf-16") and data.startswith(codecs.BOM_UTF16_BE):
            used, raw = "utf-16-be", data[len(codecs.BOM_UTF16_BE):]
            text = raw.decode(used)
        elif encoding == "auto":
            try:
                text, used = data.decode("utf-8"), "utf-8"
            except UnicodeDecodeError:
                text, used = data.decode("gb18030"), "gb18030"
        elif encoding == "utf-16":
            raise ValueError("UTF-16 配置必须带 BOM 以确定字节序")
        else:
            text = data.decode(encoding)
    except UnicodeError:
        raise ValueError("配置字节无法按指定编码严格解码；请选择正确编码") from None
    if len(text.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ValueError("解码后的配置超过 2 MiB 限制")
    if any(unicodedata.category(char) == "Cc" and char not in "\r\n\t" for char in text):
        raise ValueError("配置含控制字符或二进制数据，请先移除终端转义序列")
    if not text.strip():
        raise ValueError("配置为空")
    return text, used
