from contextlib import asynccontextmanager
from pathlib import Path
from threading import Thread
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from pydantic.json_schema import models_json_schema
from sqlalchemy import inspect

from app.api.router import api_router
from app.core.config import Settings
from app.core.errors import install_error_handlers
from app.db.session import create_db_engine, initialize_storage
from app.integrations.deepseek_model import create_model
from app.schemas.contracts import PUBLIC_SCHEMAS
from app.services.dialogue import fail_interrupted_dialogue_runs
from app.services.learning import fail_interrupted_report_runs, resume_pending_reports
from app.services.materials import fail_interrupted_runs
from app.services.p3 import fail_interrupted_p3_runs
from app.workflows.runtime import WorkflowRuntime


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = create_db_engine(config)
        application.state.engine = engine
        application.state.workflow_runtime = WorkflowRuntime(config.model_max_concurrency)
        try:
            initialize_storage(config, engine)
            if inspect(engine).has_table("agent_runs"):
                fail_interrupted_runs(engine)
                fail_interrupted_p3_runs(engine)
                fail_interrupted_dialogue_runs(engine)
                fail_interrupted_report_runs(engine)
                Thread(
                    target=resume_pending_reports,
                    args=(engine, config, application.state.workflow_runtime, create_model),
                    daemon=True,
                ).start()
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="InquiSpace API",
        version="0.1.0",
        description=(
            "阶段一 P0～P5 业务与 P6 验收工具已实现：认证、草稿、资料、方案与自动预检、"
            "正式发布、单角色对话、学习事件与自动报告，以及教师图文统计和导出。"
        ),
        docs_url="/api/docs" if config.environment != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if config.environment != "production" else None,
        lifespan=lifespan,
    )
    application.state.settings = config

    def custom_openapi() -> dict[str, object]:
        if application.openapi_schema is not None:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title,
            version=application.version,
            description=application.description,
            routes=application.routes,
        )
        _, public_schema = models_json_schema(
            [(model, "validation") for model in PUBLIC_SCHEMAS],
            by_alias=True,
            ref_template="#/components/schemas/{model}",
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, definition in public_schema.get("$defs", {}).items():
            # Route DTOs are authoritative when a public model name is reused;
            # standalone P0 schemas are added only when FastAPI did not already
            # register a component under that name.
            components.setdefault(name, definition)
        application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = custom_openapi

    @application.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    install_error_handlers(application)
    application.include_router(api_router)

    if config.serve_frontend:
        dist = config.frontend_dist.resolve()
        if not (dist / "index.html").is_file():
            raise RuntimeError("Frontend build missing; run npm run build in frontend first")

        @application.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> FileResponse:
            # API failures and missing assets must not silently become successful HTML responses.
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404)
            target = (dist / path).resolve()
            if not target.is_relative_to(dist):
                raise HTTPException(404)
            if target.is_file():
                return FileResponse(target)
            if path.startswith("assets/") or Path(path).suffix:
                raise HTTPException(404)
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return application


app = create_app()
