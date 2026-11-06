from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.auth import users_router
from app.api.routes.dialogue import router as dialogue_router
from app.api.routes.materials import evidence_router, sources_router
from app.api.routes.materials import versions_router as material_versions_router
from app.api.routes.p3 import router as p3_router
from app.api.routes.p5 import router as p5_router
from app.api.routes.runs import router as runs_router
from app.api.routes.system import router as system_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.tasks import versions_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(tasks_router)
api_router.include_router(versions_router)
api_router.include_router(material_versions_router)
api_router.include_router(p3_router)
api_router.include_router(p5_router)
api_router.include_router(dialogue_router)
api_router.include_router(sources_router)
api_router.include_router(evidence_router)
api_router.include_router(runs_router)
