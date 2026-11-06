# AGENTS.md

This file provides guidance to Codex (claude.ai/code) when working with code in this repository.

## Project scope and design sources

InquiSpace / 知境 is a Chinese-language, single-role inquiry-learning application. The workspace contains two separate implementations:

- **`frontend/` + `backend/`: application scaffold.** React/TypeScript/Ant Design and FastAPI/SQLModel/SQLite. Only the health endpoint is implemented; teacher/student pages are explicitly unconnected shells. There is no authentication, business schema, seed account, task persistence, model integration, retrieval, or SSE yet. Navigation is development preview, not identity switching or authorization. Do not turn missing features into simulated successful operations.
- **`opendesign-prototype/`: standalone interactive HTML prototype.** It has browser-persisted demonstration workflows and template-generated responses, not real backend or model capabilities. It is not imported or built by the application. Leave it separate unless the task targets the prototype.

Read the relevant design sources before implementing business features:

- [Original requirements](docs/阶段一需求文档.md) and [technical approach](docs/阶段一实现方案.md) establish the single-role scope and technical direction.
- The **v1.1 implementation documents dated 2026-11-04** explicitly update selected interactions without rewriting those upstream documents: [module design and implementation plan](docs/阶段一_功能模块详细设计与实施计划.md), [API contract](docs/阶段一_接口文档.md), and [database design](docs/阶段一_数据库表设计.md). They specify one-sentence teaching-plan generation, automatic internal checks, explicit teacher publication confirmation, student dialogue, and automatic learning reports instead of mandatory long submission forms. Technical traces remain internal. Reports may summarize students' expressed ideas, never invent unexpressed conclusions. These are implementation contracts, not evidence that the features exist.
- [Prototype design handoff](opendesign-prototype/DESIGN.md) and [current interaction changes](opendesign-prototype/简洁界面改版说明.md) describe the confirmed visual/interaction reference. Arbitrary prototype behavior does not independently change requirements.

Some design links still point to an older absolute `/Users/qxq/Documents/Codex/...` workspace; use the corresponding files here. The root README describes the scaffold but predates the v1.1 interaction changes. Its claims that Node/npm and a frontend lockfile are unavailable are also historical: `frontend/package-lock.json` exists. No Cursor or Copilot instruction files were found when this guidance was created.

## Development commands

Run from the workspace root unless a command explicitly changes directory. Requires Python 3.12–3.15 and Node.js 22.12+ with npm. No model credentials, Redis, or external database are needed for the scaffold.

### Setup and development servers

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e './backend[dev]'
# Only if backend/.env does not already exist:
cp backend/.env.example backend/.env
npm --prefix frontend ci
make migrate

# Run in separate terminals:
make backend
make frontend
```

- `make backend`: Uvicorn with reload at `http://127.0.0.1:8000`.
- `make frontend`: Vite at `http://127.0.0.1:5173` (strict port). `/api` is proxied to port 8000; retain same-origin browser requests rather than adding CORS for local development.
- Health: `/api/v1/health`; development Swagger UI: `/api/docs`; OpenAPI: `/api/openapi.json`.
- `make migrate`: runs `alembic upgrade head` from `backend/`. Application startup does not run migrations.

### Checks and targeted tests

```sh
make test     # Backend pytest + frontend Vitest; excludes prototype
make lint     # Ruff check + format check, ESLint + TypeScript
make build    # TypeScript build + Vite production bundle

# Backend suite / single test
backend/.venv/bin/pytest backend/tests -q
backend/.venv/bin/pytest backend/tests/test_framework.py::test_health_and_storage -q
backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend

# Frontend suite / file / single test
npm --prefix frontend test
npm --prefix frontend test -- src/api/client.test.ts
npm --prefix frontend test -- src/api/client.test.ts -t '区分网络失败'
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

Frontend tests run in Vitest's **Node environment**, not a browser, and currently discover only `src/**/*.test.ts`. Backend framework tests cover health/storage, errors, OpenAPI, static hosting, and migration round-trips. These tests do not establish business-feature or real-model acceptance.

### Built frontend served by the backend

```sh
make build
(cd backend && INQUISPACE_ENVIRONMENT=production INQUISPACE_SERVE_FRONTEND=true \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1)
```

This serves `frontend/dist` on the backend origin and disables API documentation in production. Frontend hosting fails explicitly if the build is missing. SPA routes fall back to `index.html`, but missing API routes/static assets remain 404. This deployment mode is not production readiness: authentication, object permissions, CSRF/Origin enforcement, and other business safeguards are not implemented. Do not expose the scaffold as a public teaching service.

## Architecture and extension boundaries

### Frontend

`src/main.tsx` provides React StrictMode, Ant Design's Chinese locale, and shared theme tokens; `src/styles.css` supplies application styling. `src/router.tsx` nests teacher/student/system pages inside `AppShell`, which owns responsive navigation and the route outlet. Resource navigation only formats a route; it does not verify that a task or session exists.

The real request path is `OverviewPage` → `api/health.ts` → `api/client.ts` → `/api/v1/health`. The shared `request()` client requires a runtime data validator, accepts only same-origin `/api/` paths, sends same-origin credentials, rejects redirects, and distinguishes HTTP, network, timeout, cancellation, and invalid-response failures via `ApiClientError`. Requests default to a 15-second timeout and accept an `AbortSignal`; the health page cancels on effect cleanup. Future JSON endpoint modules should follow this contract rather than treating a TypeScript assertion as response validation. The optional CSRF header is only a client capability, not implemented authentication.

TypeScript is strict with `noUncheckedIndexedAccess` and `verbatimModuleSyntax`; ESLint enforces type-only imports and zero warnings.

### Backend and persistence

`app/main.py` exposes `create_app(settings=None)` and the ASGI `app`; `api/router.py` assembles the versioned routes, and `api/dependencies.py` provides request dependencies. `core/` owns settings and errors, `schemas/` owns external API shapes, and `db/` owns persistence. Keep API schemas distinct from database models.

Settings use the `INQUISPACE_` environment prefix and load `backend/.env` by an absolute path. FastAPI lifespan creates the engine on `app.state.engine`, initializes data/upload directories, checks SQLite, and disposes the engine on shutdown. Request dependencies open and close SQLModel sessions but do **not** auto-commit; future writes need explicit service-layer transaction ownership. Tests inject temporary settings/data directories rather than using the real database.

The JSON contract uses camelCase and server-generated request IDs, including the `X-Request-ID` response header. Success is `{ data, requestId }`; errors are `{ error: { code, message, details, retryable }, requestId }`. The **implemented** error `details` is an array, including in frontend runtime validation; the v1.1 API document also shows object-shaped details. Reconcile both ends explicitly when implementing that planned contract. SSE and file responses must use separate response types, not the JSON client/envelope.

SQLModel models must be registered in `app/db/models.py` so Alembic sees their metadata. `0001_baseline` is deliberately empty of business tables. Add models and reviewed Alembic migrations per implemented module; do not use `create_all()` as schema migration or execute the design document's entire DDL as if it were the current schema. Alembic's version table is the migration authority, not a parallel `PRAGMA user_version` system.

SQLite connections enable foreign keys and `busy_timeout=5000`; startup checks JSON support. WAL is not currently enabled. Runtime data and uploads default to `backend/data/`, independently of the process working directory, and are not public static assets.

For future business code, the README defines these boundaries (directories are not yet implemented): `services/` for permissions and transactions, `workflows/` for orchestration/stop/confirmation, `tools/` for controlled reads and writes, and `integrations/` for backend-only model-provider adapters. The planned deployment is a single backend process with local persistence; do not infer that queues, vector databases, or a multi-agent framework are required.

## Standalone prototype

```sh
node opendesign-prototype/serve.mjs                  # http://127.0.0.1:4173
node --test opendesign-prototype/tests/model.test.cjs
node --check opendesign-prototype/src/model.js
node --check opendesign-prototype/src/app.js
```

`src/model.js` exposes the state rules to both the browser (`PrototypeModel`) and Node tests; `src/app.js` handles DOM interaction, localStorage, and simulated execution. `build.mjs` inlines `src/page.html`, `src/style.css`, `src/model.js`, and `src/app.js` into the standalone `index.html`.

The build intentionally refuses to overwrite an existing `index.html`. Before using `node opendesign-prototype/build.mjs --replace-generated`, check whether the HTML contains OpenDesign edits and preserve any exported master; rebuilding from older sources can destroy those changes. The root `make build` does not rebuild the prototype.

Use `http://127.0.0.1:4173/?review=qa#tasks` for isolated browser checks. It uses `zhijing-opendesign-v2-qa`, separate from normal `zhijing-opendesign-v2` storage. Preserve existing demonstration history and legacy `zhijing-opendesign-v1` data. Old submission tests cover compatibility, not a requirement to restore the old mandatory submission form.
