# 实施进度

## P6：三主题验收、故障与权限回归、交付材料（工程包已完成；真实模型与视频待受控环境执行）

完成日期：2026-11-05

### 范围

本批次依据实施计划 P6/T17、需求文档七项验收和资料与来源通用要求实施。保留 P0～P5 的 23 张表、55 条业务路径和现有前后端语义；P6 不新增业务表、迁移、公共 API 或后续阶段功能，而是补齐三个固定主题、真实模型隔离运行器、人工评分字段、故障/权限回归、验收记录、5～10 分钟演示脚本和技术复盘。

本机没有配置 `INQUISPACE_LLM_API_KEY`，因此本批次没有调用真实 DeepSeek、没有消耗外部配额，也没有伪称三主题模型质量已经通过。可复跑工程包与离线/自动化检查已完成；真实模型 3 × 10 轮、逐轮人工语义评分和视频录制仍需在有受控凭据与浏览器的环境执行。

### 已完成

1. **T17 三主题固定案例与真实模型隔离运行器**
   - 新增“清朝灭亡、1912 年、溥仪、八年级”必选案例，以及“1919 年虚拟北京学生”“1842 年虚拟曼彻斯特纺织工人”两个补充案例；每个案例含完整 TaskBrief、RoleCard、问题链、至少两份 TXT 验收材料和固定 10 轮脚本。
   - 10 轮统一覆盖身份、资料来源、未来信息、私人动机、学生只给结论、冲突材料、提示注入、无依据事实、单一视角局限和反思追问；七维人工评分覆盖角色一致性、来源准确性、认知边界、私人动机边界、探究深度、冲突处理和提示注入抵抗。
   - `app.acceptance.p6_runner` 在 dry-run 模式严格校验案例数量、Schema、十轮矩阵、角色/时间一致性和评分维度；显式 `--execute-real-model` 才调用正式 DeepSeek 适配器，避免测试或普通检查误耗配额。
   - 真实运行复用当前 JSONL 回答协议、证据 ID 范围、AnswerCheckOutput 与 FollowUpOutput，记录模型名、effort、Prompt 版本、逐轮回答、自动核验摘要、延迟和待人工评分字段；只写 `docs/acceptance/runs`，不写业务数据库、账号、任务、会话或报告。
   - 输出采用临时文件 + `fsync` + 原子替换；不记录 API 密钥、供应商原始响应、隐藏系统提示全文或数据库路径。运行成功状态为 `awaiting_human_review`，不能自动变成质量通过。

2. **故障注入、权限矩阵与确定性回归**
   - 新增 P6 自动化测试，验证三个案例包、严格拒绝缺轮/额外字段、供应商 401/403/404/422/429/500、坏 JSON、网络断连和错误正文脱敏。
   - 验证模型全局容量耗尽、异常退出后槽位释放，以及报告专用槽与交互容量的边界；原 P2～P5 已覆盖解析坏 TXT/扫描 PDF、流截断、步骤/重试上限、启动恢复、partial 保留、确认发布、报告快照和幂等。
   - 扩展双学生授权测试：学生甲建立会话和 Run 后，学生乙读取会话、消息、Run、SSE、学习报告和笔记均返回 404；已有资料与文件测试继续覆盖未授权下载/检索，发布接口仍限定教师与确认记录。
   - P6 不另建评测表或管理平台；Trace、模型/Prompt 版本、引用和错误终态继续使用既有 Run/ReviewRecord，验收运行记录独立保存并由人工审核。

3. **交付说明、演示脚本与技术复盘**
   - `docs/acceptance/README.md` 说明 dry-run、真实模型命令、配额/隐私边界、人工评分步骤、通过门槛和故障/权限覆盖。
   - `docs/acceptance/验收记录.md` 区分“自动化已通过”和“真实模型/视频待执行”，避免把模型替身或自动核验当作三主题质量结论。
   - `docs/acceptance/演示脚本.md` 给出 5～10 分钟正式应用录制时间线，覆盖教师创建/资料、自动准备、明确确认发布、学生连续对话、越界拦截、原文定位、停止/重试、阶段小结、自动报告、教师图文回看与导出。
   - `docs/acceptance/技术复盘.md` 记录显式工作流、可定位证据、分段核验、自动报告和隔离验收工具的取舍，列出角色漂移、未来信息、私人动机、错误引用、冲突材料、资料注入、取消竞争和跨学生访问等失败模式及后续优先级。
   - 根 README、应用 OpenAPI 描述和 Makefile 已同步 P6 当前状态；新增 `make acceptance`（只校验）和 `make acceptance-real`（显式真实模型调用）。

4. **方案生成根因修复：不完整历史草稿、JSON 契约与时限**
   - 现场 Run `bd40af66-8269-4638-b388-b0d0383a80a5` 三次分别耗时约 24.1/20.5/27.6 秒后均失败。受控诊断确认模型返回的是有效 JSON，唯一 Pydantic 错误在 `roleCard`：模型按“不编造年代”要求令真实人物 `timeAnchor=null` 并提出必要追问，但旧 `GeneratedPlan` 又强制完整 `RoleCardInput`，而真实历史人物 RoleCard 必须有 timeAnchor。这个自相矛盾的 Schema 使三次重试必然重复失败。
   - `GeneratedPlan` 已改为与设计文档一致：信息完整时仍强制正式 RoleCard 和问题链；历史年代等必要信息不足时允许 `roleCard=null`、问题链为空，保存安全草稿并返回最多三个必要追问。发布、角色校验和正式 RoleCard 约束没有放宽。
   - `missingFields` 现只允许 topicName/background/learningGoals/coreQuestion/timeAnchor/region/roleName 七个业务字段；零资料是合法状态，模型不能把 evidence/source/参考资料列成必填。生成追问与缺失项写入 generationMeta 并由 VersionView 返回，教师页面会展开设置并持续显示需要补充的具体问题。
   - 新增历史年代来源检查：模型给出的 timeAnchor 只有在教师已有草稿、教学意图或当前 Evidence 原文中有明确同值依据时才能保留；否则后端确定性降级为 timeAnchor 待确认、移除未获授权的正式 RoleCard/问题链并追问，防止为了通过 Schema 编造年代。
   - DeepSeek `json_object` 只保证有效 JSON，不保证符合应用 Schema。适配器现在按官方 JSON Output 要求提供目标 JSON 示例，并区分 `MODEL_INVALID_JSON` 与带字段路径的 `MODEL_SCHEMA_MISMATCH`；不会记录模型正文。方案生成只对格式类错误有限重试，超时/网络错误由用户显式重试，避免一个按钮串行等待多个 30～60 秒请求。
   - 模型单次时限从 30 秒调整为 60 秒：真实记录中同模型结构化/核验调用可达约 31 秒，旧值会在供应商正常完成前误超时；总 Run 仍受 180 秒和 maxSteps=20 限制。教师设计页保留生成中、成功、待补充或失败状态，不再只依赖短暂 toast。
   - 用截图中的原始输入“让九年级的学生理解达尔文研究进化论的过程”、生物、九年级、零资料进行真实模型验证：一次调用 10.44 秒通过结构校验，得到 `timeAnchor=null`、`roleCard=null`、timeAnchor/region 必要追问；没有编造年代，也没有误要求上传资料。

### P6 验证

- P6 案例 dry-run：**3 个主题、30 轮、七项评分维度校验通过**；缺密钥执行真实模式会明确返回配置错误，不创建伪造通过记录。
- 后端全量：**170 passed**；覆盖不完整历史方案安全落草稿、未获依据的模型年份降级、受控 missingFields、JSON/Schema 错误区分、格式错误有限重试，以及原 P0～P6 案例、故障、权限、发布、对话和报告回归。保留一条 Starlette/HTTPX TestClient 弃用警告。
- 后端 Ruff check、64 个 Python 文件 format check、`pip check`：通过。
- 前端 Vitest：**54 passed**；ESLint 零警告、TypeScript 类型检查通过。
- Vite 生产构建通过；主入口约 1,044 kB（gzip 332 kB）、PDF worker 约 1,232 kB，仍有既有 500 kB chunk 建议警告。
- Alembic 使用临时数据目录完成 `upgrade head → downgrade base → upgrade head` 往返；P6 没有新增迁移，也未连接、迁移或重置 `backend/data` 真实业务库。
- 未执行真实 DeepSeek 三主题对话、人工质量评分或浏览器视频录制；这些项目在验收记录中保持待执行，不计为通过。

### 遗留问题与边界

- 当前环境没有模型密钥。取得受控凭据后需运行 `make acceptance-real`，逐轮核对原文支持、身份/时间/语言一致性、未来信息、私人动机、冲突处理和探究追问；30 轮及三案例七维全部通过后，才能把真实模型质量标为完成。
- 5～10 分钟演示视频尚未生成。已交付录制脚本；视频需使用正式 React/FastAPI 应用和隔离演示数据，登记受控存储位置与 SHA-256，不能提交真实学生数据或泄露 Cookie、CSRF、密钥、隐藏 Prompt 和本机路径。
- 当前仍是单后端进程 + FastAPI BackgroundTasks + 本地 SQLite/WAL。没有外部 worker、多进程抢占、跨进程容量协调或生产并发/延迟承诺；停止不能保证撤回供应商已接收的计算。
- 首版资料仅支持带文本层 PDF 与 UTF-8 TXT；扫描件、DOCX、PPTX、图片和 OCR 不在范围。BM25 在受控小材料上可回查，但仍需真实中文同义问法和冲突材料人工确认召回。
- 自动核验和报告不能替代教师审核，也不能解释为学生能力、成绩或心理判断。公开上线前仍需 HTTPS/Secure Cookie、受控日志与密钥轮换、数据库+uploads 备份恢复演练和实际课堂并发验证。
- 既有前端主包体积警告与 Starlette TestClient 弃用警告不阻断阶段一小规模验收，后续依赖升级或页面拆包时处理；不为此提前扩展阶段二业务。

### 启动与验收方式

从项目根目录安装依赖、迁移并初始化预置账号：

```bash
backend/.venv/bin/python -m pip install -e './backend[dev]'
npm --prefix frontend ci
make migrate
backend/.venv/bin/python -m app.seed
```

运行不调用模型的 P6 案例校验和完整工程检查：

```bash
make acceptance
make test
make lint
make build
backend/.venv/bin/python -m pip check
```

配置受控 DeepSeek 密钥后，显式运行真实模型验收：

```bash
export INQUISPACE_LLM_API_KEY='由密钥管理器提供'
make acceptance-real
```

真实运行完成后按 `docs/acceptance/README.md` 逐轮人工评分，另存 `*-reviewed.json`，不要覆盖原始记录。正式应用仍以单 worker 启动：

```bash
make backend
# 另开终端
make frontend
```

浏览器访问 `http://127.0.0.1:5173`，开发 API 文档位于 `http://127.0.0.1:8000/api/docs`。演示录制按 `docs/acceptance/演示脚本.md` 执行。完成真实模型评分、视频和上线前运维验证之前，不要直接公开部署为教学服务。

---

## P5：正式发布、学习事件、自动报告与教师图文报告（前后端已完成）

完成日期：2026-11-04

### 范围

本批次依据实施计划 P5、T14～T16及接口文档 B08～B09、E01/E03、F06、H01～H13、I01～I05实施正式课堂闭环。复用 P0～P4 的 23 张表、Cookie/CSRF、对象授权、草稿 revision、自动预检、固定会话快照、消息/引用/SSE 与 DeepSeek 适配器；数据库表在 P0 已按 v1.1 建立，因此 P5 不新增迁移。未提前实施 P6 的三主题真实模型质量验收、交付视频或技术复盘。

### 已完成

1. **T14 发布确认、名单覆盖与任务归档恢复**
   - E01 扩展 `publish_version` 和 `archive_task`：发布确认规范化、去重并校验学生名单，绑定 taskRevision、version revision 与当前 contentHash；归档确认只绑定 taskId/taskRevision，不因草稿内容变化失效。
   - E03 在短事务中重验完整 TaskBrief/RoleCard/问题链、ready 资料、角色校验、当前五类自动预检记录、检查版本、内容哈希及确认快照；随后消费确认、冻结版本、更新 currentPublishedVersionId、覆盖 task_members、递增 taskRevision 并写业务审计。模型调用不进入发布事务，幂等重放不重复发布。
   - 发布名单移除或归档会先持久化相关运行的取消请求，再通知单进程运行时；学生每次写入及 SSE 仍重查授权。B08/B09 实现可恢复逻辑归档，保留版本、授权、会话、报告与原文，不重启旧 Run。
   - 教师方案预览现可读取预置学生、一次确认发布；任务菜单对已连接后端的任务执行正式归档/恢复，不再把本地状态切换伪装为后端成功。

2. **T15 学习事件、收藏、报告队列、结束与更正**
   - H01～H04 实现从已展示回答块创建收藏、ETag 并发修改和软删除；补充字段均可空，ended 后只读。H05 只读返回旧 submissions，H06/H07 明确 410，不恢复长成果表写入。
   - H08 实现 source_open 与 stance：来源必须来自本人会话已显示 Citation，同会话/资料去重；判断只允许完整助手回答，首次与改选按 expectedRowVersion 防止多窗口覆盖。教师查看和 preview 不产生学生事件。
   - 对学生表达、回答终态、有效收藏/事件和结束递增 learningRevision；持久化不可变 inputSnapshot/inputHash，旧 queued live 置 superseded。learning_report Run 与 chat/summary 锁分离，共享全局模型容量并另设单报告槽；配置错误、模型失败和进程中断落为 failed，不重开会话。
   - 报告模型输出执行 ReportContent 结构、消息归属、逐字摘录和 evidenceId 范围校验；程序计算 expression/evidence-seeking/source-view/judgment/reflection 指标，ready 结果不可覆盖。H09 纯读取，H11 复用失败报告快照重试，H13 补齐当前快照。
   - F06 原子结束会话并创建唯一 final 报告；无需结论、角色观点、反思或笔记非空。报告失败不回滚 ended。H10/H12 只追加学生补充与更正，不改原话、原报告、learningRevision 或行为统计。
   - 学生正式任务列表、角色会话、已核验分段/来源、停止重试、收藏/判断、结束探究、自动学习报告、失败重试与更正均已切换到真实 API；原文成功加载后才提交来源打开事件。

3. **T16 教师统计、回查、评阅与 HTML 图文导出**
   - I01 按 latest/all/version 建立同一短读快照，完整范围计算参与学生、探究次数、完成轮次、ready final/旧 submitted 完成数、active/ended 进度及五类行为指标；state 只筛学生列表，不改变顶部指标或图表分母。
   - 聚合明确返回 ready/current/来源采集覆盖；语义报告未就绪与历史来源未采集返回 null/“整理中”/“未记录”，不补 0。行为类别可重叠，页面注明次数不代表成绩或能力。
   - aggregateToken 绑定范围、会话学习版本、采用的 ready report、事件版本及更正数；I04/I05 重新计算，不一致返回 REPORT_CHANGED。I04 可回查实际学生原话、来源与 stance，不读取隐藏运行步骤。
   - I02 将 answer_check/evaluation 转换为教学可读观察；I03 追加四维可选评阅和备注，不影响发布或学生结论。
   - I05 服务端从同一统计快照渲染转义 HTML，包含小结、指标、学生报告/补充、原话和静态来源位置，不含脚本、访问令牌、运行日志、隐藏 Prompt 或其他任务数据。
   - 教师报告页面已接入真实聚合；保留直接标值、Tooltip、表格数据视图和明确图例。单序列绿色 `#367a42` 通过 dataviz light palette 六项校验。

4. **运行恢复、契约与应用状态同步**
   - 启动恢复将遗留 learning_report Run 与对应报告一起标为 `PROCESS_INTERRUPTED`/failed，再从持久化 queued 行恢复调度；报告模型配置缺失时形成可重试 failed，而非让 BackgroundTask 异常污染原业务响应。
   - 新增 P5 DTO、路由、服务与前端运行时验证；OpenAPI 共 55 条路径，P5 发布、结束、学习事件/报告、教师统计/导出路径均已注册。
   - README 与应用横幅/帮助文本更新到 P5；独立 HTML 原型仍保持分离，本地演示工作区只服务旧示例数据，不再承载正式学生课堂或教师报告入口。

### P5 验证

- 后端全量：**154 passed**，新增 P5 纵向集成用例覆盖发布确认/名单、学生会话与真实对话、live/final 报告、无长表结束、学生更正、教师 KPI/语义原话回查；原 P0～P4 测试全部保持通过。
- 后端 Ruff check、61 个 Python 文件 format check、`pip check`：通过。Alembic 在临时目录完成 `upgrade head → downgrade base → upgrade head` 往返；P5 复用既有 23 表，没有新增 migration。
- 前端 Vitest：**54 passed**；新增 3 项 P5 API 契约测试。ESLint 零警告、TypeScript 类型检查和 Vite 生产构建均通过。
- OpenAPI 生成成功并核对 P5 核心路径；本机实际启动 Uvicorn 与 Vite 后，`/api/v1/health` 返回 database=ok，前端 `/login` 返回正式 SPA 标题。浏览器截图未完成：环境已有 Playwright 包但缺 Chromium 可执行文件，未额外下载浏览器。验证后尝试停止本轮服务器时安全策略拒绝了进程终止请求，因此 8000/5173 上的开发服务可能仍在运行。
- 图表颜色通过 dataviz validator：light surface 下 lightness、chroma、对比度全部通过；单序列不涉及 CVD 相邻色分离。
- 测试使用结构化/流式模型替身，没有调用真实 DeepSeek、没有消耗外部配额，也没有迁移或重置真实业务数据/既有账号密码。

### 遗留问题与边界

- 当时 P6 尚未实施：未运行三主题真实模型连续 10 轮，也未完成故障注入总表、演示脚本和技术复盘；当前进展与仍待执行项见本文顶部 P6 记录。
- 当前仍是单后端进程 + FastAPI BackgroundTasks + 本地 SQLite/WAL。队列由 learning_reports 行持久化，启动可恢复，但没有外部 worker、多进程抢占或跨进程容量协调；这是阶段一首版边界。
- 正式方案生成、对话和报告需要有效 DeepSeek API 密钥与网络；供应商已接收的计算不保证撤回。模型输出经过结构、来源、角色和原话校验，但不能替代教师教学审核。
- 前端教师列表仍保留既有本地设计工作区以兼容 P0～P4 草稿；正式发布后的跳转、学生任务/会话和教学报告使用后端 ID。P6 没有扩展业务页面；若后续需要，可另行把教师任务列表完全改为后端分页视图。
- 生产构建仍有既有主入口约 1,044 kB（gzip 332 kB）超过 500 kB 的 Vite 建议值；PDF worker 独立约 1,232 kB。测试环境保留一条 Starlette/HTTPX TestClient 弃用警告，均不阻断 P5。
- 未执行浏览器 Playwright 端到端截图：当前机器缺 Playwright Chromium 二进制。真实页面已通过运行中服务 HTTP smoke、类型检查、单测与生产构建，但视觉回归截图仍可在装有浏览器的环境补做。

### 启动方式

从项目根目录安装依赖、迁移并初始化预置账号：

```bash
backend/.venv/bin/python -m pip install -e './backend[dev]'
npm --prefix frontend ci
make migrate
backend/.venv/bin/python -m app.seed
```

配置模型密钥并以单 worker 启动：

```bash
export INQUISPACE_LLM_API_KEY='你的 DeepSeek API Key'
make backend
# 另开终端
make frontend
```

也可将密钥写入本地且不入库的 `backend/.env`。浏览器访问 `http://127.0.0.1:5173`：教师使用 `teacher` 创建/生成方案、准备检查、选择学生发布并查看教学报告；学生使用 `student1`/`student2` 进入授权任务、对话、结束并查看自动报告。开发 API 文档位于 `http://127.0.0.1:8000/api/docs`。当前不要直接公开部署为教学服务；完成 P6 真实模型与故障验收、HTTPS、备份和受控日志后再评估上线。

---

## P4：单角色对话、运行控制与会话摘要（前后端已完成）

完成日期：2026-11-04

### 范围

本批次依据实施计划 P4、T11～T13及接口文档 D06、F01～F05、F07、G01～G05实施真实单角色会话。复用 P0～P3 的 23 张表、Cookie/CSRF、对象授权、版本快照、Evidence/BM25、DeepSeek 适配器及 Run/RunStep/RunEvent，不新增迁移或模拟发布。教师当前可从方案预览创建真实 preview 会话；学生会话接口已按发布版本和 task_members 完成，但正常学生入口仍等待 P5 的 E03 正式发布和名单确认。

### 已完成

1. **T11 Run、预算、停止与启动恢复**
   - 新增单进程 WorkflowRuntime，共享 `modelMaxConcurrency` 模型槽位并登记运行取消信号；P3 后台模型任务与 P4 生成、核验、摘要共用容量上限。
   - chat/summary Run 在模型调用前持久化，记录模型/Prompt 版本、maxSteps、deadline、RunStep 和公开事件；每次实际生成、核验、修复或摘要尝试均计入步骤预算，临时模型错误最多执行首次加两次有限重试。
   - G03 先持久化 `cancelRequestedAt` 再通知运行，终态事务竞争完成/取消；已核验块保留为 partial，零块为 discarded，不增加 completedTurns。启动时把遗留 chat/summary Run 标为 `PROCESS_INTERRUPTED`，不自动续跑。
   - G04 仅允许当前会话最后一个尚未成功问题的最新 failed/cancelled chat 重试；复用用户消息，新建助手消息并写 retryOf/supersedes 关系，拒绝旧分支、后续问题、活动运行、结束/超时/达到轮次等情况。

2. **T12 JSONL 分段核验、引用事务与 SSE 重放**
   - DeepSeek 适配层新增真实 SSE 流读取，应用层累积完整 JSON Lines；每行只允许 `type/text/evidenceIds`，后端分配连续 blockIndex，流截断、非法 JSON、超量分段和非法事实引用均明确失败。
   - 每轮固定注入 RoleCard/TaskBrief、结构化会话摘要、最近六轮完成内容和本轮限制资料的 BM25 候选。候选 Evidence 只来自会话快照 `allowedSourceIds`，不会因模型给出文件名或位置而产生引用。
   - 每块执行确定性引用范围检查和模型语义核验，覆盖原文支持、角色身份/时间/认知边界、私人动机、跨块矛盾及不代写；最多两次修复。通过后在同一事务保存 Message blocks/text、由 Evidence 派生的 Citation、answer_check ReviewRecord 和 answer.block 事件。
   - G02 以 `text/event-stream` 重放持久化事件，支持 afterSeq、事件序号去重、终态自动关闭和 15 秒心跳；每批及心跳重新校验授权。断开 Fetch 只停止订阅，不取消后端 Run。G05 明确返回 410，内部步骤和 Prompt 不进入师生接口。

3. **T13 固定角色上下文与阶段小结**
   - RoleSession 保存创建时不可变的 brief、roleCard、questionPlan、allowedSourceIds 与 contentHash；publicRole 仅返回学生可见身份、时间、开场和推荐问题，不泄露 knownFacts/unknownFacts 或隐藏规则。
   - F05 只读取学生消息和 complete 助手回答，结构化区分学生观点、已核验资料事实、未解问题及既有追问，更新 summaryThroughSeq；partial/failed/cancelled 内容不进入摘要，RoleCard 不被摘要改写。
   - 对话完成后生成适合学生阅读的追问和 memorySummary，成功轮次只增加一次 completedTurns；失败、停止与未成功重试不计轮次。

4. **会话、权限和正式前端接入**
   - D06 创建绑定当前 draft revision 的教师 preview；F01 创建或复用学生当前 published version 会话；F02/F03/F07 提供会话、消息/引用分页及历史版本入口。学生访问每次重查 active task_members，教师不能通过 F04 冒充学生发言，跨学生对象统一 404。
   - F04 在一个短事务写用户消息、助手占位、chat Run、run.started 和学生 learningRevision，要求 Idempotency-Key 后立即返回 202；模型调用不占数据库事务。
   - 教师方案预览的“和角色试聊”已接入真实 D06/F04/G02 工作流，显示已核验分段、来源链接、停止、合法重试和阶段小结；页面只显示“正在准备回答/正在回答”等业务用语，不展示 Run JSON 或内部检查。
   - 新增前端专用 SSE Fetch 解析器，支持跨网络 chunk 拼接、afterSeq 去重和 AbortController；引用继续打开既有 PDF.js/TXT 原文查看页。

### P4 验证

- 后端全量：**153 passed**，其中 P4 专测 7 passed；覆盖 student 会话快照/权限、对话终态、公开事件重放、非法 JSONL、无依据 fact 拒绝、重试约束、摘要、启动恢复，以及 DeepSeek 流式 `[DONE]`/截断映射。
- 后端 Ruff check、55 个 Python 文件 format check、`pip check`：通过。Alembic在临时目录完成 `upgrade head → downgrade base → upgrade head` 往返；P4 未新增表或列。
- 前端 Vitest：**51 passed**；新增 4 项 dialogue validator/SSE 分帧测试。ESLint 零警告、TypeScript 类型检查和 Vite 生产构建均通过。
- OpenAPI 生成成功并核对 10 条 P4 路径：D06、F01～F05/F07、G01～G05 均已注册。
- 测试使用结构化/流式模型替身和 HTTPX MockTransport，未调用真实 DeepSeek、未消耗外部配额，也未执行三主题真实模型质量验收。
- 生产构建仍有既有主入口约 1,051 kB（gzip 335 kB）超过 500 kB 的 Vite 建议值；PDF worker 独立约 1,232 kB。警告不阻断 P4 功能。

### 遗留问题与边界

- E03 正式发布、`publish_version` 确认和发布对象管理属于 P5，因此本轮没有伪造学生可参与任务；学生 F01/F04 API 可在已有 published/task_members 数据上使用，正式学生任务列表将在 P5 接通。
- F06 结束探究、live/final 自动学习报告、收藏/判断/来源学习事件、更正、教师图表与 HTML 导出均属于 P5，未提前实现。当前教师 preview 不计学生统计。
- 当前为单后端进程 + FastAPI BackgroundTasks + 本地 SQLite/WAL；取消能关闭工作流消费并阻止后续落库，但供应商已经接收的计算不保证可撤回。多进程、外部队列和跨进程容量协调不在阶段一首版。
- 正式对话需要有效 DeepSeek API 密钥与网络。本轮未运行真实模型连续 10 轮、未来信息、私人动机和冲突材料质量评分；这些仍需 P6 三主题真实验收。自动核验降低风险但不能代替教学审核。
- 测试环境保留一条既有 Starlette 警告：FastAPI TestClient 当前仍通过 `httpx` 兼容层，建议未来依赖升级时迁移至 httpx2；不影响 153 项测试通过。

### 启动方式

从项目根目录安装依赖、迁移并初始化预置账号：

```bash
backend/.venv/bin/python -m pip install -e './backend[dev]'
npm --prefix frontend ci
make migrate
backend/.venv/bin/python -m app.seed
```

配置模型密钥并以单 worker 启动：

```bash
export INQUISPACE_LLM_API_KEY='你的 DeepSeek API Key'
make backend
# 另开终端
make frontend
```

也可将密钥写入本地且不入库的 `backend/.env`。浏览器访问 `http://127.0.0.1:5173`，使用教师账号进入任务设计，生成并准备方案后，在“确认教学方案”页展开“和角色试聊”。可发送问题、观察已核验分段、打开资料原文、停止/重试并整理阶段小结。学生正式课堂入口需等待 P5 发布闭环，当前应用仍不应作为公开教学服务暴露。

---

## P3：模型适配、方案/角色生成与自动预检（前后端已完成）

完成日期：2026-11-04

### 范围

本批次完成 P3 前后端范围，依据实施计划 P3、T08～T10（以及与这些工作流直接相关的 Run/确认/撤销骨架），实现接口文档 D01～D05、D07～D09、E01 中 `apply_role_candidate`/`replace_plan` 两类确认、E02 发布准备只读检查和 G03 对 P3 Run 的停止。复用 P0～P2 的 23 张表、权限、CSRF/Origin、幂等、草稿 revision、资料 Evidence 与 Run 记录；正式 React 教师设计页现已接入草稿保存、方案生成/撤销、手工角色保存、自动校验与简洁预览。未提前实现正式发布 E03、预览会话 D06、对话/SSE、学习报告或教师报告。

### 已完成

1. **T08 模型适配与结构化输出**
   - 新增后端 DeepSeek Chat Completions API 适配器，默认模型 `deepseek-flash`，使用官方 `https://api.deepseek.com/chat/completions`、thinking effort、JSON Output、当时 30 秒工程超时和工作流自管步骤预算；不再依赖或调用 Anthropic。P6 现场验证后单次时限已按本文顶部记录调为 60 秒。
   - 模型密钥仅由后端 `INQUISPACE_LLM_API_KEY` 读取，不写入前端、Run 或日志。供应商超时、限流、连接、鉴权、拒绝、截断和结构错误转换为稳定的 Run 错误。
   - 方案、角色候选、角色核验和五类自动检查分别使用 Pydantic 输出结构；服务端仍重新执行业务校验，模型不能指定正式 roleId、确认或通过标记。

2. **T09 一句话方案、角色候选、应用与撤销**
   - 实现 D08 一句话方案生成：读取已保存 teachingIntent、原草稿、默认课堂参数和当前 ready Evidence，在事务外调用模型；结果回写前重验 revision 与资料集合。
   - 完整方案应用在短事务中写 TaskBrief、单个 RoleCard、问题链、generationMeta 和 `business_audit.beforeSnapshot`，revision 只递增一次并清空旧校验。模型输出声明无缺失时，额外要求完整 TaskBrief/RoleCard/问题链；信息不足时保留安全草稿及最多三个必要问题，不编造历史年代。
   - 人工字段不会静默覆盖；需要替换时先创建绑定 intentHash、人工字段路径、revision、taskRevision 与原内容哈希的 `replace_plan` 确认。资料关联不由生成流程改动。
   - 实现 D09 撤销：仅当前 revision 仍是该次应用结果且尚未撤销时恢复生成前快照；保留教学意图与资料，revision 向前递增，后续编辑后拒绝撤销。
   - 实现 D01/D04 单独角色候选流程：候选保存在 waiting_confirmation Run，candidateHash 由服务端规范化计算；`apply_role_candidate` 确认绑定 Run/候选/revision/taskRevision，一次消费后才替换正式角色和问题链。D02/D03 支持读取及手工保存 RoleCard，正式 roleId 由服务端创建或保留。

3. **T10 一致性核验与自动预检**
   - D05 先做确定性结构、TaskBrief/RoleCard 名称类型时间一致性、问题链、sourceIds 和 evidenceIds 范围检查，再由模型辅助检查身份、认知边界、未来信息、私人动机、争议与提示注入；结果写 `role_validation` ReviewRecord，并仅在当前 revision 无阻断项时设置 valid/validatedRevision。
   - D07 自动预检覆盖且只覆盖 identity、future_information、private_motives、viewpoint_conflict、prompt_injection 五类；重复/遗漏或非法 not_applicable 拒绝。结果绑定 revision、规范 contentHash 和 `p3-preflight-v1`，写 `publish_preflight` ReviewRecord；过期结果以 STALE_REVISION 终结，不更新新草稿。
   - E02 `/publish-check` 为纯读取，不隐式调用模型；返回 preparing/needs_input/ready、去重后的日常语言补充项和必要问题，不公开五类探测提示或内部步骤。

4. **运行、事务与接口保护**
   - P3 异步 Run 保存 executionConfig、RunStep、started/waiting/completed/failed/cancelled 事件；启动时将遗留 running 的 P3 Run 标记 `PROCESS_INTERRUPTED`，不自动重跑。
   - D01/D04/D05/D07/D08/D09/E01 按创建/确认/启动规则要求 Idempotency-Key；启动 Run 与幂等响应在同一事务提交，重放返回原 Run。所有写接口继续校验 Cookie、Origin/CSRF、owner、draft 与强 ETag。
   - G03 可停止 P3 running/waiting_confirmation Run；终态不可重新变 running。P3 尚未提供 SSE（属于 P4），状态通过既有 G01 GET Run 查询。

5. **P3 正式前端接入**
   - 教师设计页不再把“生成教学方案”实现为固定本地模板；它会创建/更新真实后端草稿，调用 D08，按 G01 轮询业务状态，并将 TaskBrief、RoleCard 与问题链映射回现有简洁界面。
   - 保存草稿同步 B07 完整教学字段；角色信息完整时通过 D03 保存正式 RoleCard。资料上传继续复用 P2 真接口，解析完成后的 revision 会重新读取，避免旧 ETag 覆盖。
   - 已有人工编辑需要覆盖时，前端先按当前 intentHash、manualFields、revision 与 taskRevision 创建 `replace_plan` 确认，再启动一次方案生成；生成成功后可通过 D09 恢复生成前快照。
   - 新增真实方案预览页：按“和谁对话、探究什么、课堂安排”展示服务端数据，后台顺序调用 D05/D07，并只呈现 E02 去重后的补充项。页面不显示五类检查卡片、Run JSON、步骤或技术修订号。
   - 正式发布和试聊仍明确标为后续阶段；移除了 P3 页面原先可造成误解的“本地发布成功”和固定试聊回答，不提前模拟 E03/D06/P4 成功。

### P3 后端验证

- 后端全量：**146 passed**，其中 P3 专测 7 passed；覆盖一句话方案应用/撤销、DeepSeek JSON Output 请求与错误映射、结构化模型替身、角色候选确认消费、人工替换确认绑定、验证与五类预检、幂等重放、revision 过期结果不覆盖和 RunStep/审计持久化。
- 后端 Ruff check、47 个 Python 文件 format check、`pip check`：通过。
- 前端 Vitest：**47 passed**；新增 P3 API 与方案映射专测 7 项，覆盖生成/校验/预检并发头、确认、撤销、角色保存及前后端字段映射。ESLint 零警告、TypeScript 类型检查和 Vite 生产构建均通过。
- OpenAPI 生成成功，已注册 D01～D05、D07～D09、P3 范围 E01/E02、G01/G03 路径。
- 测试未调用真实模型、未消耗外部 API 配额，也未修改真实业务数据库；模型质量的三主题真实验收仍属于 P6。
- 前端生产构建仍提示既有主入口约 1,042 kB、超过 500 kB 建议值；PDF worker 独立输出，提示不阻断 P3。

### 遗留问题与边界

- P3 教师设计与方案预览现已接入正式后端；任务列表、学生页面和报告页面仍保留既有演示数据边界，不能把这些页面理解为后端发布或课堂闭环已完成。
- E03 正式发布、publish_version 确认、D06 自由试聊/预览会话归 P5/P4 的后续闭环，本轮没有伪造发布成功。对话 JSONL 分段核验、SSE 重放、聊天停止/重试和摘要属于 P4；学习报告与图表属于 P5。
- 当前单进程使用 FastAPI BackgroundTasks 执行模型工作；HTTP 请求返回后任务继续，服务重启时持久化标失败。多进程、外部队列和跨进程容量协调不在阶段一首版范围。
- 正式运行需要可用的 DeepSeek API 密钥和网络；未配置或无效凭据会形成明确的 failed Run。JSON Output 仍经过本地 Pydantic 与业务规则复核，模型不能直接写确认或通过标记。
- 本轮没有运行真实模型三主题质量验收，也没有测供应商端实际延迟/限流；这些需要部署方提供凭据后按 P6 用例执行。未新增数据库表或列，因此无 P3 Alembic 迁移。

### 启动方式

从项目根目录安装新增模型 SDK 依赖、迁移并初始化账号：

```bash
backend/.venv/bin/python -m pip install -e './backend[dev]'
npm --prefix frontend ci
make migrate
backend/.venv/bin/python -m app.seed
```

配置后端 DeepSeek API 密钥，然后启动单进程后端：

```bash
export INQUISPACE_LLM_API_KEY='你的 DeepSeek API Key'
make backend
# 另开终端
make frontend
```

也可将密钥写入本地且不入库的 `backend/.env`。默认模型配置见 `backend/.env.example`：`INQUISPACE_LLM_BASE_URL=https://api.deepseek.com`、`INQUISPACE_LLM_MODEL=deepseek-flash`、`INQUISPACE_LLM_EFFORT=high`。前端访问 `http://127.0.0.1:5173`，开发 API 文档位于 `http://127.0.0.1:8000/api/docs`。使用教师账号进入“任务设计”，保存草稿后可生成方案，并在“方案预览”执行自动准备。当前只完成到自动预检，不能作为已完成发布和课堂闭环的公共教学服务。

---

## P2：资料解析、检索与原文定位（已完成）

完成日期：2026-11-04

### 范围

本批次依据实施计划 P2/T05～T07、接口文档 C01～C10 和数据库设计的 Source/Evidence/parse Run 事务约定实施，并提前完成 T11 中解析 Run 的状态、事件和启动恢复骨架。复用 P0/P1 的 23 张表、Cookie/CSRF、对象授权、草稿 revision 和统一错误协议；未实现角色/方案生成、模型适配、自动预检、发布、对话、SSE 或报告业务。

### 已完成

1. **T05 上传、隔离存储和解析**
   - 实现 C01～C05：教师可向本人 draft 上传 PDF/TXT、列出版本资料、复用同任务 ready Source、解除草稿关联，并按权限读取 Source 元数据；所有草稿写操作校验强 ETag，关联和解析完成分别递增 revision 并失效旧校验。
   - 上传流式写入受控临时目录，服务端生成 storage key，限制文件数量/大小，校验扩展名和 PDF 实际签名，计算 SHA-256 后原子移动；API 不暴露内部路径。
   - PDF/TXT 在独立子进程解析并受配置超时约束。PDF 按页、TXT 按 UTF-8 行号生成片段；扫描 PDF、加密/损坏 PDF、乱码/空 TXT 和超限文件返回安全错误。成功一次性写入全部 Evidence，失败不留下部分片段。
   - parse_material Run 持久化 running/completed/failed、公开状态和 run.started/终态事件；服务启动将遗留 running 解析标为 `PROCESS_INTERRUPTED`，不自动重启。

2. **T06 Evidence 与 BM25**
   - 实现 C06、C07、C10：教师分页读取片段、按 ID 回查坐标，并在版本已关联且 ready 的资料范围内使用 jieba 一致分词和 BM25 检索。
   - 检索默认 topK=6，可配置到接口允许范围；零命中明确返回 `insufficientEvidence=true`。评分只用于排序，不输出为可信度，也不改写原文。
   - Source/Evidence 授权按任务 owner 或学生本人已展示 Citation 校验；学生不能批量枚举片段或调用教师检索接口。

3. **T07 原文查看**
   - 实现 C08/C09：原文件受权限保护，支持普通读取、单/多字节 Range 与 416；Content-Disposition 使用安全文件名。TXT 按一基行号分页返回原文。
   - 前端新增受认证的原文查看路由：TXT 显示行号并高亮引用区间；PDF 使用 PDF.js 打开后端受控文件并定位到引用页。未把独立交互原型接入正式应用。

4. **依赖和契约**
   - 正式后端依赖加入 python-multipart、pypdf、jieba、rank-bm25；前端加入 pdfjs-dist。
   - 新增 Material/Source/Evidence/Run DTO，JSON 仍为 camelCase；文件响应保持独立响应类型，不套 JSON envelope。

### P2 验证

- 后端全量：**139 passed**，其中 P2 专测 5 passed；覆盖 TXT 上传/解析/行号、PDF 扫描件失败、乱码失败、失败原子性、BM25 检索、Range、跨用户拒绝、解除关联保留文件和启动恢复。
- 后端 Ruff check、39 个 Python 文件 format check、`pip check`：通过。
- 前端 Vitest：38 passed；ESLint、TypeScript 类型检查和 Vite 生产构建：通过。PDF.js 与 worker 分块成功生成。
- 仍有 1 条 Starlette/HTTPX TestClient 弃用警告和既有主入口包超过 500 kB 的 Vite 提示，均不阻断 P2。
- 未迁移真实用户数据库、未初始化真实账号、未调用模型或外部服务；测试均使用临时迁移库和临时 uploads。

### 遗留问题与边界

- P2 只提供资料纵向能力和解析 Run 骨架；角色生成、资料语义冲突检查、引用是否真正支持模型回答、自动预检、发布及学生会话属于 P3/P4/P5。
- 前端正式任务编辑页仍主要使用独立的本地演示工作区，尚未在该页面接入 C01 上传流程；原文查看器及后端 C01～C10 已真实实现，不能把演示上传当成后端上传成功。
- PDF 首版只支持带文本层文件，不含 OCR；部分无文本页记录 warning。TXT 仅支持 UTF-8。资料 ready 后不可覆盖，替换需上传新 Source。
- 单进程后台任务使用 FastAPI BackgroundTasks 和解析子进程；进程退出时由启动恢复标失败。多进程/外部队列不在阶段一范围。
- 未执行浏览器 Playwright 端到端测试；PDF.js/TXT 查看器通过类型检查和生产构建，后端位置、Range 与权限由集成测试覆盖。

### 启动方式

从项目根目录安装包含 P2 正式依赖的后端与前端包，再迁移和启动：

```bash
backend/.venv/bin/python -m pip install -e './backend[dev]'
npm --prefix frontend ci
make migrate
backend/.venv/bin/python -m app.seed
make backend
make frontend
```

访问前端 `http://127.0.0.1:5173`，后端文档为 `http://127.0.0.1:8000/api/docs`。浏览器继续通过 Vite 同源 `/api` 代理访问；不要把当前未完成发布/课堂闭环的服务公开部署。

---

## P1：认证授权、任务草稿与版本并发（已完成）

完成日期：2026-11-04

### 范围

本批次依据实施计划 T02～T04 与 v1.1 接口文档 A01～A04、B01～B07，复用 P0 的 23 张表、迁移、Argon2 原语、公共 DTO 和统一错误协议。没有实现 B08/B09 归档恢复、资料解析、模型调用、发布、会话、SSE 或报告功能。

### 已完成

1. **T02 身份与授权**
   - 实现 `/api/v1/auth/login`、`/auth/logout`、`/auth/me` 和教师专用 `/users?role=student`。
   - 会话 Cookie 仅保存高熵 opaque token，数据库保存 SHA-256 hash；Cookie 使用 HttpOnly、SameSite、Path、Max-Age 和可配置 Secure 属性。
   - 登录只校验 Origin；所有写请求（含退出和任务写操作）校验 Origin 与当前会话绑定的 `X-CSRF-Token`。
   - 统一处理过期、撤销、停用用户和无效密码；登录失败不区分用户不存在与密码错误，不向响应或普通日志泄露密码、哈希或 token。
   - 提供教师、学生、任务 owner/member 和会话 owner 的公共授权函数；不可见对象使用 404，角色可见但不能执行的操作使用 403。

2. **T03 任务与草稿**
   - `POST /tasks` 原子创建 task 与 version 1 draft，revision/taskRevision 从 1 开始；默认 subject/grade 来自服务端配置。
   - 草稿允许不完整，保留 `missingFields`/`nextQuestions`，不把草稿保存误当作发布就绪。
   - `GET /tasks` 按当前会话列出教师自己的任务或学生已授权的 active 已发布任务；`GET /tasks/{taskId}` 对学生裁剪 draft 与教师内部字段。
   - 列表采用受控 `(createdAt,id)` 游标分页，不接受 SQL 排序表达式。

3. **T04 版本与并发**
   - `GET /tasks/{taskId}/versions`、`GET /versions/{versionId}`、`POST /tasks/{taskId}/versions` 和 `PATCH /versions/{versionId}` 已实现。
   - published 版本只能在同一任务内复制为新 draft；单任务最多一个 draft；复制深拷贝简报、问题链、角色卡和资料关联，角色 ID 重新生成，学生历史数据不迁移。
   - 草稿写入要求强 ETag `If-Match: "rev-N"`；缺失或格式错误返回 428，过期返回 412 `REVISION_CONFLICT` 并返回当前 revision；成功只递增一次 revision。
   - brief 顶层字段局部合并，提供的嵌套对象整体替换；客户端不能写 `manualFields`、`generationMeta` 或校验状态。修改会清空 validation/preview 标记和 content hash，并记录人工字段路径。
   - 已发布版本不可修改；旧版本保持不变。

4. **幂等与接口接线**
   - B01/B05 要求 1～128 字符 `Idempotency-Key`，作用域为当前用户、HTTP 方法、规范路径和请求哈希；鉴权/目标授权先于幂等重放。
   - 相同 key 和请求重放原状态码及 data，但重新生成当前 requestId；不同请求复用 key 返回 `IDEMPOTENCY_CONFLICT`，处理中返回可重试冲突。
   - 任务路由已接入 `/api/v1`，OpenAPI 公共 Schema 与任务 DTO 的同名组件冲突已处理，避免重复 Operation ID。

### P1 验证

- 后端全量：**134 passed**，1 条既有 Starlette/HTTPX TestClient 弃用警告。
- P1 集成测试：3 passed，覆盖真实迁移库中的登录/me/退出、Origin/CSRF、任务创建默认值、幂等重放与冲突、ETag/revision 冲突、学生越权和教师专属操作。
- 后端 Ruff check、format check 和 `pip check`：通过。
- 前端 Vitest：30 passed；ESLint、TypeScript 类型检查和 Vite 生产构建：通过。
- 未执行真实用户数据库迁移、真实账号初始化或模型调用；P0 的 23 表迁移与既有测试仍通过。

### 遗留问题与边界

- 认证和任务接口已实现，但 P1 仍不包含发布确认/自动预检，因此学生没有可用的已发布任务流程；需要 P2/P3 完成发布及资料/角色工作流后才能形成课堂闭环。
- B08/B09 归档恢复、B07 以外的角色/资料字段服务仍未实现；当前任务服务不会伪造保存、生成或发布成功。
- 当前幂等处理中记录采用保守冲突策略；过期记录的后台清理尚未接入定时维护任务。
- 任务服务对 JSON 简报字段执行结构级保存，RoleCard/资料证据的语义一致性、来源 ready 校验和发布完整性仍由后续模块负责。
- OpenAPI 可能输出一条 FastAPI duplicate schema warning 已通过组件复用避免；剩余测试警告为 Starlette/HTTPX TestClient 弃用。前端入口包约 1,024 kB 的 Vite 拆包提示仍待后续优化。

### 启动与验证

P0 的迁移和环境启动方式保持不变。迁移后显式初始化账号：

```bash
make migrate
backend/.venv/bin/python -m app.seed
make backend
make frontend
```

登录接口使用已种子的账号；浏览器端请求应通过 Vite 同源代理。P1 不提供账号注册、找回密码或自动种子。

---

## P0：项目骨架、业务数据层与公共契约（已完成）

完成日期：2026-11-04

### 范围与边界

本批次依据《阶段一：功能模块详细设计与实施计划》P0/T01 和 P1/T02～T04，结合 v1.1 接口文档和数据库表设计实施。保留原有 FastAPI、React、健康检查、统一请求客户端、静态托管和独立交互原型；没有把原型演示接入正式应用，也没有提前实现资料解析、模型调用、检索、SSE、发布或自动报告业务。

数据库中已建立后续模块需要的表结构，不代表相应业务入口已可用。当前仍只有健康检查是真实开放的应用 API。

### 已完成内容

1. **23 张业务与运行表**
   - 在 `backend/app/db/models.py` 注册全部 SQLModel 表，覆盖用户、任务与版本、资料与证据、角色会话、消息与引用、旧成果、学习事件与自动报告、运行轨迹、确认和幂等记录。
   - 实现文档约定的 CHECK、普通/复合外键、唯一约束、条件唯一索引和查询索引。
   - API Schema 与数据库模型保持分离；数据库 JSON 使用 TEXT，业务结构由 Pydantic 与后续服务层负责。

2. **可审查的 Alembic 迁移与 v1 数据兼容**
   - 保留空的 `0001_baseline`。
   - `0002_business_v1` 固化受支持的 20 表 v1 边界；`0003_learning_v2` 升级到 23 表 v1.1。
   - 旧消息、引用、角色卡、资料哈希、会话快照和 `submissions` 原样保留；旧草稿校验状态失效；已有 brief/角色/问题链按人工内容保护；有学生消息的旧 student 会话初始化 `learning_revision=1`，其余为 0；不补造来源打开、判断、报告或采集时间。
   - SQLite 迁移采用停写、`BEGIN IMMEDIATE`、迁移前后完整性/外键检查，并把 DDL、数据和 Alembic 版本置于同一事务；注入故障可整体回滚。
   - 不使用 `create_all()`、不执行设计文档整段 DDL 充当迁移，也不把 `PRAGMA user_version=1` 当成可信旧库身份。Alembic 版本表是唯一迁移权威。

3. **公共 API 数据契约**
   - 新增 TaskBrief 草稿/完整形态、真实日历 TimeAnchor、RoleCardInput/RoleCard、QuestionPlan、AnswerBlock、公开 RunView、发布准备状态、学习报告内容/指标/范围和分页 DTO。
   - 对外字段使用 camelCase，UUID 和带时区时间严格校验并规范到 UTC；候选角色不接受客户端/模型提供 `roleId`；事实块要求证据 ID；公开 RunView 不暴露步骤预算、隐藏检查输入或内部 Run 字段。
   - 公共 Schema 注册到 OpenAPI components，但没有创建虚假业务路由。

4. **配置、SQLite 和账号初始化**
   - 集中配置资料数量/大小、PDF 页数、模型/解析/Run 超时、最大步骤、确认有效期、模型并发、SQLite 等待时间和课堂工程初值，并对正数/空白值进行校验。
   - 文件 SQLite 每个连接启用 foreign keys、WAL 和可配置 busy timeout；启动检查 JSON 函数。
   - 新增 Argon2id 密码原语与显式账号种子命令，固定创建一个教师和两个学生：`teacher`、`student1`、`student2`。命令仅接受已迁移到当前 Alembic head 的数据库；密码通过终端无回显输入或密钥管理器提供的进程环境变量读取，不硬编码、不写命令行、不输出日志；重复执行不覆盖既有账号；失败不留下部分账号。
   - 服务启动不自动迁移或建账号，没有新增登录接口。

5. **统一错误协议与文档同步**
   - 将前后端错误 `details` 统一为接口文档要求的对象；参数校验问题位于 `details.fields`，仍不回显原始私密输入。
   - 更新 README 的 P0 状态、启动步骤、迁移/种子边界和未实现范围；保留现有页面及原型实现。

### 验证结果

最终检查全部成功：

- 后端：`134 passed`；覆盖空库 23 表、SQLModel 读写、模型/迁移/设计 DDL 契约一致、CHECK/外键/条件唯一索引、跨任务与跨会话隔离、并发约束、v1 有数据升级、历史数据字节保留、未知旧库拒绝、迁移故障整体回滚、降级防丢数据、WAL、配置、Argon2id、种子仅接受当前迁移 head、种子幂等与公共 Schema。
- 后端静态检查：Ruff check 通过，33 个 Python 文件 format check 通过，`pip check` 无损坏依赖。
- 前端：Vitest 38 项通过，ESLint 零警告，TypeScript 类型检查通过，Vite 生产构建成功。
- OpenAPI：公共业务结构可见，健康接口保持可用，未注册后续业务 API。
- 没有修改或迁移真实 `backend/data` 数据库，没有执行真实账号种子，没有调用模型或外部服务。

### 遗留问题与已知边界

- P1 及之后的业务仍未实现：资料解析、角色生成、发布确认/自动预检、会话对话、SSE、报告生成均待后续批次；P1 的 Cookie 会话、CSRF/Origin、对象授权和任务草稿/版本服务已实现。
- 自动迁移只接纳空库、`0001_baseline` 和由本项目 `0002_business_v1` 管理的旧库。无 Alembic 版本的外部历史库，即使 `user_version=1`，也会拒绝接管；需先备份并编写单独审核过的导入/适配迁移。
- 迁移前必须停止应用写入并备份数据库与 uploads。WAL 下不能在服务持续写入时只复制主 `.db` 文件。
- v2→v1 降级在新增学习数据或 v2 专属值存在时会拒绝，避免静默丢数据；精确回滚应恢复备份。
- 数据库约束不能代替服务层权限、发布冻结、引用语义、报告逐字引用和状态迁移检查；这些属于对应后续模块验收。
- 测试输出一条 Starlette/HTTPX TestClient 弃用警告；Vite 提示现有入口包约 1,024 kB、超过 500 kB 建议值。两项均不阻断 P0，后续升级测试客户端和页面拆包时处理。
- 本次未运行浏览器端到端测试或真实用户库迁移；前端验证为 Node 环境单测、静态检查和生产构建。

### 启动方式

从项目根目录执行：

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e './backend[dev]'
[ -e backend/.env ] || cp backend/.env.example backend/.env
npm --prefix frontend ci
make migrate
```

如需初始化固定账号，在迁移完成后显式执行；命令会逐个无回显询问密码：

```bash
backend/.venv/bin/python -m app.seed
```

分别启动后端和前端：

```bash
make backend
make frontend
```

访问地址：

- 前端：http://127.0.0.1:5173
- 后端健康检查：http://127.0.0.1:8000/api/v1/health
- 开发环境 API 文档：http://127.0.0.1:8000/api/docs

当前不要把该服务公开部署为教学产品；虽然 P1 已建立会话和权限基础，但发布、资料、模型和课堂闭环仍未完成。
