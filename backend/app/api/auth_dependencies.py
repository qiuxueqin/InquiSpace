"""Backward-compatible imports for authentication dependencies."""

from app.api.dependencies import (
    Authenticated,
    CSRFProtected,
    CurrentUser,
    DatabaseSession,
    SettingsDependency,
    StudentUser,
    TeacherUser,
    get_current_auth,
    get_current_user,
    get_session,
    get_settings,
    require_csrf,
    require_student,
    require_teacher,
)

__all__ = [
    "Authenticated",
    "CSRFProtected",
    "CurrentUser",
    "DatabaseSession",
    "SettingsDependency",
    "StudentUser",
    "TeacherUser",
    "get_current_auth",
    "get_current_user",
    "get_session",
    "get_settings",
    "require_csrf",
    "require_student",
    "require_teacher",
]
