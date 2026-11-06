"""A01-A04 authentication and public student roster endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import Field
from sqlmodel import select

from app.api.dependencies import Authenticated, DatabaseSession, SettingsDependency, TeacherUser
from app.db.models import User
from app.schemas.common import APIModel, Envelope
from app.services.auth import login as authenticate
from app.services.auth import logout as end_session
from app.services.auth import public_user

router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/users", tags=["Users"])


class LoginRequest(APIModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class UserView(APIModel):
    id: str
    display_name: str
    role: Literal["teacher", "student"]


class LoginData(APIModel):
    user: UserView
    csrf_token: str


class LogoutData(APIModel):
    logged_out: bool = True


class RosterItem(APIModel):
    id: str
    display_name: str


class RosterData(APIModel):
    items: list[RosterItem]
    next_cursor: str | None = None


def as_user_view(user: User) -> UserView:
    return UserView.model_validate(public_user(user))


@router.post("/login", response_model=Envelope[LoginData])
def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: DatabaseSession,
    config: SettingsDependency,
) -> Envelope[LoginData]:
    user, csrf_token = authenticate(
        db, config, payload.username, payload.password, request=request, response=response
    )
    return Envelope(
        data=LoginData(user=as_user_view(user), csrf_token=csrf_token),
        request_id=request.state.request_id,
    )


@router.post("/logout", response_model=Envelope[LogoutData])
def logout(
    request: Request,
    response: Response,
    db: DatabaseSession,
    auth: Authenticated,
    config: SettingsDependency,
) -> Envelope[LogoutData]:
    session, _ = auth
    end_session(db, config, request, response, session)
    return Envelope(data=LogoutData(), request_id=request.state.request_id)


@router.get("/me", response_model=Envelope[LoginData])
def me(request: Request, auth: Authenticated) -> Envelope[LoginData]:
    session, user = auth
    return Envelope(
        data=LoginData(user=as_user_view(user), csrf_token=session.csrf_token),
        request_id=request.state.request_id,
    )


@users_router.get("", response_model=Envelope[RosterData])
def student_roster(
    request: Request,
    role: Literal["student"],
    teacher: TeacherUser,
    db: DatabaseSession,
) -> Envelope[RosterData]:
    students = db.exec(
        select(User).where(User.role == role).where(User.is_active == 1).order_by(User.created_at)
    ).all()
    return Envelope(
        data=RosterData(
            items=[RosterItem(id=user.id, display_name=user.display_name) for user in students]
        ),
        request_id=request.state.request_id,
    )
