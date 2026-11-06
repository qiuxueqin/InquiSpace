from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DatabaseSession
from app.core.errors import AppError
from app.schemas.common import APIModel, Envelope

router = APIRouter(tags=["System"])


class Health(APIModel):
    status: str = "ok"
    service: str = "inquispace"
    version: str = "0.1.0"
    database: str = "ok"


@router.get("/health", response_model=Envelope[Health])
def health(request: Request, session: DatabaseSession) -> Envelope[Health]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise AppError("DATABASE_UNAVAILABLE", "数据库不可用", 503, retryable=True) from exc
    return Envelope(data=Health(), request_id=request.state.request_id)
