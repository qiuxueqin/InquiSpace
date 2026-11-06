"""External DTOs for P2 material, evidence, and parse-run endpoints."""

from pydantic import Field

from app.schemas.common import APIModel


class SourceView(APIModel):
    id: str
    task_id: str
    file_name: str
    file_type: str
    byte_size: int
    sha256: str
    status: str
    page_count: int | None = None
    total_lines: int | None = None
    parse_error: dict[str, object] | None = None
    warnings: list[dict[str, object] | str] = Field(default_factory=list)
    created_at: str


class EvidenceView(APIModel):
    id: str
    source_id: str
    text: str
    page_no: int | None = None
    paragraph_no: int
    start_line: int | None = None
    end_line: int | None = None
    disputed: bool
    source_label: str


class RunErrorView(APIModel):
    code: str
    message: str
    retryable: bool = False


class RunView(APIModel):
    id: str
    kind: str
    status: str
    display_message: str
    session_id: str | None = None
    version_id: str | None = None
    result: dict[str, object] | None = None
    error: RunErrorView | None = None
    created_at: str
    finished_at: str | None = None


class UploadSourceResult(APIModel):
    source: SourceView
    run: RunView
    revision: int


class LinkSourceRequest(APIModel):
    source_id: str


class LinkSourceResult(APIModel):
    source_id: str
    revision: int


class DetachSourceResult(APIModel):
    detached: bool
    revision: int


class EvidencePage(APIModel):
    items: list[EvidenceView]
    next_cursor: str | None = None


class TextLinesView(APIModel):
    source_id: str
    total_lines: int
    start_line: int
    lines: list[str]


class EvidenceSearchRequest(APIModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=6, ge=1, le=20)


class EvidenceSearchResult(APIModel):
    evidence: list[EvidenceView]
    insufficient_evidence: bool
