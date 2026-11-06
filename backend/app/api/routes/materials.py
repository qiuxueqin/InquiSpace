"""C01--C10 source, evidence, and original-file routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Header, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse

from app.api.dependencies import (
    CurrentUser,
    DatabaseSession,
    SettingsDependency,
    TeacherCSRF,
    TeacherUser,
)
from app.schemas.common import Envelope
from app.schemas.material_dtos import (
    DetachSourceResult,
    EvidencePage,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    EvidenceView,
    LinkSourceRequest,
    LinkSourceResult,
    RunView,
    SourceView,
    TextLinesView,
    UploadSourceResult,
)
from app.services import materials, tasks

versions_router = APIRouter(prefix="/versions", tags=["Materials"])
sources_router = APIRouter(prefix="/sources", tags=["Materials"])
evidence_router = APIRouter(prefix="/evidence", tags=["Materials"])
runs_router = APIRouter(prefix="/runs", tags=["Runs"])


def _envelope(
    request: Request, data: object, *, status: int = 200, etag: str | None = None
) -> JSONResponse:
    headers = {"X-Request-ID": request.state.request_id}
    if etag is not None:
        headers["ETag"] = etag
    return JSONResponse(
        status_code=status,
        content={"data": jsonable_encoder(data), "requestId": request.state.request_id},
        headers=headers,
    )


@versions_router.post(
    "/{version_id}/sources", response_model=Envelope[UploadSourceResult], status_code=202
)
def upload_source(
    request: Request,
    background: BackgroundTasks,
    version_id: str,
    file: Annotated[UploadFile, File()],
    session: DatabaseSession,
    user: TeacherCSRF,
    settings: SettingsDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> JSONResponse:
    expected = tasks.parse_if_match(if_match)
    result, run_id = materials.create_upload(
        session,
        user,
        version_id,
        expected_revision=expected,
        filename=file.filename,
        file=file.file,
        settings=settings,
    )
    background.add_task(materials.process_parse_run, request.app.state.engine, settings, run_id)
    return _envelope(request, result, status=202, etag=tasks._etag(result.revision))


@versions_router.get("/{version_id}/sources", response_model=Envelope[list[SourceView]])
def list_sources(
    request: Request, version_id: str, session: DatabaseSession, user: TeacherUser
) -> Envelope[list[SourceView]]:
    return Envelope(
        data=materials.list_sources(session, user, version_id), request_id=request.state.request_id
    )


@versions_router.post("/{version_id}/source-links", response_model=Envelope[LinkSourceResult])
def link_source(
    request: Request,
    version_id: str,
    payload: LinkSourceRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    settings: SettingsDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> JSONResponse:
    result = materials.link_source(
        session,
        user,
        version_id,
        payload.source_id,
        expected_revision=tasks.parse_if_match(if_match),
        settings=settings,
    )
    return _envelope(request, result, etag=tasks._etag(result.revision))


@versions_router.delete(
    "/{version_id}/sources/{source_id}", response_model=Envelope[DetachSourceResult]
)
def detach_source(
    request: Request,
    version_id: str,
    source_id: str,
    session: DatabaseSession,
    user: TeacherCSRF,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> JSONResponse:
    result = materials.detach_source(
        session,
        user,
        version_id,
        source_id,
        expected_revision=tasks.parse_if_match(if_match),
    )
    return _envelope(request, result, etag=tasks._etag(result.revision))


@versions_router.post(
    "/{version_id}/evidence-search", response_model=Envelope[EvidenceSearchResult]
)
def search_evidence(
    request: Request,
    version_id: str,
    payload: EvidenceSearchRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
) -> Envelope[EvidenceSearchResult]:
    return Envelope(
        data=materials.search_evidence(session, user, version_id, payload.query, payload.top_k),
        request_id=request.state.request_id,
    )


@sources_router.get("/{source_id}", response_model=Envelope[SourceView])
def get_source(
    request: Request, source_id: str, session: DatabaseSession, user: CurrentUser
) -> Envelope[SourceView]:
    return Envelope(
        data=materials.get_source(session, user, source_id), request_id=request.state.request_id
    )


@sources_router.get("/{source_id}/evidence", response_model=Envelope[EvidencePage])
def list_evidence(
    request: Request,
    source_id: str,
    session: DatabaseSession,
    user: TeacherUser,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> Envelope[EvidencePage]:
    return Envelope(
        data=materials.list_evidence(session, user, source_id, limit=limit, cursor=cursor),
        request_id=request.state.request_id,
    )


@evidence_router.get("/{evidence_id}", response_model=Envelope[EvidenceView])
def get_evidence(
    request: Request, evidence_id: str, session: DatabaseSession, user: CurrentUser
) -> Envelope[EvidenceView]:
    return Envelope(
        data=materials.get_evidence(session, user, evidence_id),
        request_id=request.state.request_id,
    )


@sources_router.get("/{source_id}/file", response_class=FileResponse)
def get_file(
    source_id: str,
    session: DatabaseSession,
    user: CurrentUser,
    settings: SettingsDependency,
) -> FileResponse:
    source = materials.accessible_source(session, user, source_id)
    path = materials.storage_path(settings, source)
    return FileResponse(
        path,
        media_type=materials.file_media_type(source),
        filename=materials.safe_download_name(source),
        content_disposition_type="inline",
        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, no-store"},
    )


@sources_router.get("/{source_id}/text", response_model=Envelope[TextLinesView])
def get_text(
    request: Request,
    source_id: str,
    session: DatabaseSession,
    user: CurrentUser,
    settings: SettingsDependency,
    start_line: int = Query(default=1, ge=1, alias="startLine"),
    limit: int = Query(default=200, ge=1, le=500),
) -> Envelope[TextLinesView]:
    return Envelope(
        data=materials.text_lines(
            session, user, source_id, settings, start_line=start_line, limit=limit
        ),
        request_id=request.state.request_id,
    )


@runs_router.get("/{run_id}", response_model=Envelope[RunView])
def get_run(
    request: Request, run_id: str, session: DatabaseSession, user: CurrentUser
) -> Envelope[RunView]:
    return Envelope(
        data=materials.get_run(session, user, run_id), request_id=request.state.request_id
    )
