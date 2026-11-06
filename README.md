# InquiSpace · 知境

阶段一「单角色沉浸式探究」的前后端首版实现。当前目标是完成小规模验收所需的业务闭环与可复跑验证，**不是未经验证即可公开部署的教学产品**。

## 依据与当前范围

固定依据：[阶段一需求文档](docs/阶段一需求文档.md)、[阶段一实现方案](docs/阶段一实现方案.md)。实施以 2026-11-04 的 v1.1 [模块计划](docs/阶段一_功能模块详细设计与实施计划.md)、[接口契约](docs/阶段一_接口文档.md)、[数据库设计](docs/阶段一_数据库表设计.md)为准，其中已确认的交互变更优先于上游旧流程。当前已完成 P0～P5 业务与 P6 可复跑验收工程包，不修改独立的 [HTML 原型](opendesign-prototype/)。

已建立：

- React + TypeScript + Vite + Ant Design 页面框架、路由与统一请求客户端。
- FastAPI 应用工厂、配置、请求 ID、统一响应和异常处理、OpenAPI。
- SQLModel / SQLite 连接、会话依赖、外键检查与连接等待设置。
- Alembic 空基线后的 23 张业务/运行表、约束、索引与 v1→v2 迁移。
- 独立公共数据 Schema、文档一致的错误详情对象及显式账号种子命令。
- P1 接口专测覆盖登录/退出/CSRF/Origin、任务创建与默认值、幂等重放、ETag/revision 冲突及跨用户授权。
- 前端构建产物由后端同源托管的可选配置。
- P0 公共 API Schema、错误协议、迁移/约束、WAL 和安全种子的自动化测试。
- P1 Cookie 会话、CSRF/Origin、教师/学生授权、任务草稿、版本复制、ETag/If-Match 和幂等请求基础。

- P2 PDF/TXT 解析、Evidence/BM25 检索与受权限保护的原文定位。
- P3 DeepSeek 模型适配、一句话方案、角色候选、撤销、一致性校验和五类自动预检。
- P4 固定角色会话、JSONL 分段核验、SSE、停止/重试与会话摘要。
- P5 教师确认发布、任务归档恢复、学习事件/收藏、自动学习报告、更正、教师图文统计与 HTML 导出。
- P6 三主题固定验收案例、真实模型隔离运行器、七维人工评分字段、故障/权限回归、验收记录、演示脚本和技术复盘。

P6 可复跑工程包已完成；当前环境未配置 DeepSeek 密钥，因此三主题真实模型 3 × 10 轮、人工语义评分和 5～10 分钟视频仍待在有受控凭据与浏览器的环境执行。不能用模型替身或案例校验结果宣称这些项目已经通过。详见 [P6 验收运行手册](docs/acceptance/README.md)和[验收记录](docs/acceptance/验收记录.md)。

## 开发环境

- Python 3.12–3.15。
- Node.js 22.12+（推荐受支持的 LTS 版本），npm。
- 运行迁移、静态页面和不调用模型的接口测试不需要模型密钥；正式方案生成、对话核验和自动报告需要 DeepSeek API 密钥。
- 不需要 Redis、外部数据库或多进程队列。

以下命令从项目根目录开始。Python 虚拟环境仅安装在项目内，不修改系统 Python。

### 1. 后端

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e './backend[dev]'
# 仅首次创建配置；保留已有 .env
[ -e backend/.env ] || cp backend/.env.example backend/.env
make migrate
# 迁移后按需初始化固定账号（交互式无回显输入密码）
backend/.venv/bin/python -m app.seed
make backend
```

- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- API 文档：<http://127.0.0.1:8000/api/docs>
- OpenAPI：<http://127.0.0.1:8000/api/openapi.json>

首次启动会创建本地数据和上传目录，不会自动修改业务表。数据库迁移需要显式执行。默认数据目录为 backend/data，与启动命令所在目录无关。

迁移完成后按需显式创建固定的 `teacher`、`student1`、`student2` 账号：

```bash
backend/.venv/bin/python -m app.seed
```

命令默认通过终端无回显输入并二次确认密码。自动化环境可由密钥管理器临时注入 `INQUISPACE_SEED_TEACHER_PASSWORD`、`INQUISPACE_SEED_STUDENT1_PASSWORD`、`INQUISPACE_SEED_STUDENT2_PASSWORD`；不要写入 `.env`、命令行或仓库。重复执行不会修改既有同名账号的密码、角色或资料。

### 2. 前端

另开一个终端，在项目根目录执行：

```bash
cd frontend
npm ci
npm run dev
```

访问 <http://127.0.0.1:5173>。Vite 将 `/api` 请求代理给本机 8000 端口，浏览器使用同源请求，不需要开放跨域。首页健康检查读取真实后端状态；后端未启动时显示失败并可重试。

仓库已有 package-lock.json，使用 `npm ci` 安装锁定的前端依赖。

### 3. 检查与测试

```bash
backend/.venv/bin/pytest backend/tests -q
backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend

cd frontend
npm run typecheck
npm run lint
npm test
npm run build
```

也可使用根目录 Makefile 的 `backend`、`frontend`、`migrate`、`test`、`lint`、`build` 目标。P6 案例只校验用 `make acceptance`；显式调用真实模型并消耗外部配额用 `make acceptance-real`。先安装各端依赖。

## 目录与扩展边界

```text
frontend/
  src/                  React 页面、布局、主题、路由和 API 客户端
backend/
  app/
    api/                HTTP 路由、依赖注入
    core/               配置与异常处理
    schemas/            对外请求/响应结构，不等同于数据库表
    db/                 数据库连接与模型注册
    acceptance/         P6 三主题真实模型隔离验收运行器
    main.py             应用工厂、生命周期和可选静态托管
  migrations/           显式数据库版本迁移
  tests/                框架与迁移测试
  .env.example          后端环境变量示例
  pyproject.toml        Python 依赖与工具配置
  data/                 运行时数据库/上传目录，忽略提交
opendesign-prototype/    原有独立原型，保留不动
docs/                   设计文档、P6 案例、验收记录、演示脚本与技术复盘
```

业务实现时按需新增 `services/`、`workflows/`、`tools/`、`integrations/`：业务权限与事务归服务层；编排负责步骤、停止和确认；工具负责受控读写；模型供应商适配留在后端。不为尚未实现的模块创建大量空类或“成功”占位接口。

## 当前 API 约定

API 前缀 `/api/v1`，JSON 使用 camelCase，服务端生成请求 ID，同时返回 `X-Request-ID` 响应头。

```json
{
  "data": {
    "status": "ok",
    "service": "inquispace",
    "version": "0.1.0",
    "database": "ok"
  },
  "requestId": "server-generated-uuid"
}
```

失败统一返回：

```json
{
  "error": {
    "code": "HTTP_404",
    "message": "资源不存在",
    "details": {},
    "retryable": false
  },
  "requestId": "server-generated-uuid"
}
```

当前已注册 P0～P5 业务接口；P6 只新增离线验收工具与交付文档，不新增公共业务 API。SSE 和文件下载使用独立响应类型，不套 JSON envelope。不存在的 API 返回 404，不返回假数据。参数错误不回显输入值，未处理异常不将堆栈和私密正文发给客户端。

## 数据库策略

P0 已按评审迁移落地全部 23 张表；表存在仅代表后续模块具备持久化结构，不代表对应业务已实现。`0001_baseline` 保留为空基线，`0002_business_v1` 建立兼容旧阶段一结构，`0003_learning_v2` 增加 v1.1 学习事件、自动报告和更正，并迁移受支持的 v1 数据。Alembic `alembic_version` 是唯一迁移权威；不另行维护 `PRAGMA user_version`。

- 不使用 `create_all()` 充当数据库升级。
- 新模型在 app/db/models.py 注册到 SQLModel metadata，再生成并人工检查迁移。
- SQLite 每个连接启用 `foreign_keys`、WAL（内存库除外），并按配置设置 `busy_timeout`；启动检查 JSON 函数。
- 原始资料保存在受控目录，通过逐请求授权的文件/TXT 接口读取，不作为公共静态资源。
- 使用 Alembic 版本表管理迁移，不同时维护 `PRAGMA user_version` 作为第二套迁移真相。

## 构建后同源运行

```bash
cd frontend
npm run build
cd ../backend
INQUISPACE_ENVIRONMENT=production INQUISPACE_SERVE_FRONTEND=true \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

后端托管 frontend/dist；浏览器深层页面路由返回 SPA 入口，不存在的 API 或静态资源仍返回 404。未构建前端时，开启托管会明确报错。production 关闭 OpenAPI 文档入口。数据库与 uploads 不属于静态文件目录。

这只是生产构建运行方式，**并不表示已完成生产容量、安全运维或真实模型质量验收**。公开部署前仍需配置 HTTPS、受控密钥/日志/备份，并在有凭据的环境执行 P6 三主题真实模型与人工评分。当前不要直接向公共网络开放为教学服务。

## 验证记录与限制

本次环境为 macOS、Python 3.15。后端 **170 项测试通过**，含 P6 案例与权限/故障回归，以及不完整历史方案安全落草稿、模型年份来源校验、受控 missingFields、JSON/Schema 错误区分和格式错误有限重试；前端 **54 项测试**、ESLint、TypeScript 类型检查和生产构建通过。Alembic 在临时目录完成 `upgrade head → downgrade base → upgrade head` 往返；P6 不新增业务表、迁移或公共 API。

后端 Ruff 规范/格式检查、`pip check` 均通过。测试依赖仍输出一条 Starlette/HTTPX TestClient 弃用告警；Vite 构建提示主入口约 1,044 kB、PDF worker 约 1,232 kB，均不阻断阶段一小规模验收，但后续依赖升级和页面拆包时需复核。

自动化测试使用模型替身或 MockTransport，没有消耗外部 API 配额。三主题案例的离线 Schema/十轮矩阵已通过；当前环境没有 `INQUISPACE_LLM_API_KEY`，真实 DeepSeek 3 × 10 轮、人工语义评分及演示视频尚未执行。正式模型功能需要有效 DeepSeek API 密钥与网络，执行方式见 [P6 验收运行手册](docs/acceptance/README.md)。
