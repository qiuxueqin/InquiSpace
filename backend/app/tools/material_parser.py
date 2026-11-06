"""Pure parsing helpers executed in an isolated worker process."""

from __future__ import annotations

import re
from pathlib import Path

PARSER_VERSION = "p2-v1"


class ParseFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _paragraphs(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]


def parse_txt(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ParseFailure("TEXT_DECODE_FAILED", "TXT 文件不是有效的 UTF-8 文本") from exc
    if not text.strip():
        raise ParseFailure("TEXT_DECODE_FAILED", "TXT 文件没有可用文本")
    lines = text.splitlines()
    evidence: list[dict[str, object]] = []
    start: int | None = None
    buffer: list[str] = []
    paragraph_no = 0
    for line_no, line in enumerate(lines + [""], start=1):
        if line.strip():
            if start is None:
                start = line_no
            buffer.append(line)
            continue
        if start is None:
            continue
        paragraph_no += 1
        evidence.append(
            {
                "text": "\n".join(buffer).strip(),
                "pageNo": None,
                "paragraphNo": paragraph_no,
                "startLine": start,
                "endLine": line_no - 1,
            }
        )
        start = None
        buffer = []
    if not evidence:
        raise ParseFailure("TEXT_DECODE_FAILED", "TXT 文件没有可用文本")
    return {
        "pageCount": None,
        "totalLines": max(1, len(lines)),
        "warnings": [],
        "evidence": evidence,
    }


def parse_pdf(path: Path, max_pages: int) -> dict[str, object]:
    from pypdf import PdfReader
    from pypdf.errors import FileNotDecryptedError, PdfReadError

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except Exception as exc:
                raise ParseFailure("PDF_ENCRYPTED", "PDF 已加密，无法解析") from exc
            if not unlocked:
                raise ParseFailure("PDF_ENCRYPTED", "PDF 已加密，无法解析")
        page_count = len(reader.pages)
        if page_count == 0:
            raise ParseFailure("OCR_REQUIRED", "PDF 没有可读取的页面")
        if page_count > max_pages:
            raise ParseFailure("PDF_TOO_MANY_PAGES", f"PDF 最多支持 {max_pages} 页")
        evidence: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []
        for page_no, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except FileNotDecryptedError as exc:
                raise ParseFailure("PDF_ENCRYPTED", "PDF 已加密，无法解析") from exc
            paragraphs = _paragraphs(text)
            if not paragraphs:
                warnings.append({"code": "PAGE_WITHOUT_TEXT", "pageNo": page_no})
                continue
            for paragraph_no, paragraph in enumerate(paragraphs, start=1):
                evidence.append(
                    {
                        "text": paragraph,
                        "pageNo": page_no,
                        "paragraphNo": paragraph_no,
                        "startLine": None,
                        "endLine": None,
                    }
                )
    except ParseFailure:
        raise
    except (PdfReadError, ValueError, OSError) as exc:
        raise ParseFailure("PDF_INVALID", "PDF 文件无法读取") from exc
    if not evidence:
        raise ParseFailure("OCR_REQUIRED", "PDF 没有文本层，首版不支持扫描件 OCR")
    return {
        "pageCount": page_count,
        "totalLines": None,
        "warnings": warnings,
        "evidence": evidence,
    }


def parse_material(path_text: str, file_type: str, max_pages: int) -> dict[str, object]:
    path = Path(path_text)
    if file_type == "txt":
        return parse_txt(path)
    if file_type == "pdf":
        return parse_pdf(path, max_pages)
    raise ParseFailure("UNSUPPORTED_FILE_TYPE", "仅支持 PDF 和 UTF-8 TXT")
