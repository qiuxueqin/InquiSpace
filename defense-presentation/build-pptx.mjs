import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const WORKSPACE = "/Users/qxq/Documents/InquiSpace";
const SKILL_DIR = "/Users/qxq/.codex/plugins/cache/openai-primary-runtime/presentations/26.1030.10813/skills/presentations";
const RUNTIME_PYTHON = "/Users/qxq/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";
const RUNTIME_NODE_MODULES = "/Users/qxq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES = RUNTIME_NODE_MODULES;
process.env.RUNTIME_NODE_MODULES = RUNTIME_NODE_MODULES;
const BUILD_DIR = path.join(WORKSPACE, ".codex-ppt-build");
const RENDER_DIR = path.join(BUILD_DIR, "renders");
const OUTPUT_DIR = path.join(WORKSPACE, "defense-presentation", "output");
const FINAL_PPTX = path.join(OUTPUT_DIR, "InquiSpace_答辩汇报_含讲稿_v1.pptx");
const CANDIDATE = path.join(BUILD_DIR, "candidate.pptx");

const W = 1280;
const H = 720;
const C = {
  paper: "#F7F8F4",
  paper2: "#EEF1E8",
  ink: "#253129",
  muted: "#667068",
  green: "#245A48",
  green2: "#6F8B68",
  green3: "#DCE7D3",
  ochre: "#9A6A35",
  ochreSoft: "#EEE2CF",
  line: "#D7DDD1",
  white: "#FFFFFF",
  red: "#9B4D42",
};
const BODY_FONT = "Arial Unicode MS";
const TITLE_FONT = "Songti SC";

const imagePaths = [
  path.join(WORKSPACE, "opendesign-prototype/review/ai-teacher-editor.jpg"),
  path.join(WORKSPACE, "opendesign-prototype/review/simple-preview-desktop.jpg"),
  path.join(WORKSPACE, "opendesign-prototype/review/ai-mobile-chat.jpg"),
  path.join(WORKSPACE, "opendesign-prototype/review/simple-student-desktop.jpg"),
  path.join(WORKSPACE, "opendesign-prototype/review/simple-teacher-desktop.jpg"),
];
const imageBytes = new Map();
for (const imagePath of imagePaths) {
  const bytes = await fs.readFile(imagePath);
  imageBytes.set(imagePath, new Uint8Array(bytes));
}

const presentation = Presentation.create({ slideSize: { width: W, height: H } });

function addShape(slide, x, y, w, h, fill = "none", line = "none", radius = 0) {
  return slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: line, width: line === "none" ? 0 : 1 },
    ...(radius ? { borderRadius: radius } : {}),
  });
}

function addText(slide, text, x, y, w, h, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: options.fill ?? "none",
    line: { style: "solid", fill: options.line ?? "none", width: options.line && options.line !== "none" ? 1 : 0 },
    ...(options.radius ? { borderRadius: options.radius } : {}),
  });
  shape.text = text;
  shape.text.style = {
    fontFamily: options.fontFamily ?? BODY_FONT,
    fontSize: options.fontSize ?? 20,
    color: options.color ?? C.ink,
    bold: options.bold ?? false,
    italic: options.italic ?? false,
    alignment: options.align ?? "left",
    verticalAlignment: options.valign ?? "top",
  };
  shape.text.insets = options.insets ?? 0;
  return shape;
}

function addLine(slide, x, y, w, h, color = C.line, width = 2) {
  return slide.shapes.add({
    geometry: "line",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: "solid", fill: color, width },
  });
}

function addImage(slide, imagePath, x, y, w, h, alt, options = {}) {
  return slide.images.add({
    blob: imageBytes.get(imagePath),
    contentType: "image/jpeg",
    alt,
    fit: options.fit ?? "cover",
    position: { left: x, top: y, width: w, height: h },
    ...(options.crop ? { crop: options.crop } : {}),
    geometry: options.geometry ?? "rect",
    ...(options.radius ? { borderRadius: options.radius } : {}),
  });
}

function addHeader(slide, section, page) {
  addShape(slide, 0, 0, W, H, C.paper, "none");
  addShape(slide, 68, 40, 28, 28, C.green, "none", 6);
  addText(slide, "知", 68, 42, 28, 24, { fontFamily: TITLE_FONT, fontSize: 15, color: C.white, bold: true, align: "center", valign: "middle" });
  addText(slide, "InquiSpace", 106, 42, 160, 24, { fontSize: 15, color: C.green, bold: true });
  addText(slide, section, 1010, 44, 190, 22, { fontSize: 13, color: C.muted, align: "right" });
  addText(slide, String(page).padStart(2, "0") + " / 14", 1170, 684, 70, 18, { fontSize: 11, color: C.muted, align: "right" });
}

function addTitle(slide, title, subtitle = "") {
  addText(slide, title, 68, 92, 1120, 60, { fontFamily: TITLE_FONT, fontSize: 36, color: C.ink, bold: true });
  if (subtitle) addText(slide, subtitle, 70, 154, 1110, 32, { fontSize: 17, color: C.muted });
}

function setNotes(slide, text) {
  slide.speakerNotes.text = text;
  slide.speakerNotes.setVisible(true);
}

function addBullet(slide, marker, title, body, x, y, w) {
  addText(slide, marker, x, y, 42, 42, { fontFamily: "Georgia", fontSize: 22, color: C.ochre, bold: true });
  addText(slide, title, x + 54, y, w - 54, 26, { fontSize: 20, color: C.ink, bold: true });
  addText(slide, body, x + 54, y + 30, w - 54, 50, { fontSize: 15, color: C.muted });
  addLine(slide, x + 54, y + 78, w - 54, 0, C.line, 1);
}

// 1. Cover
{
  const slide = presentation.slides.add();
  slide.background.fill = C.green;
  addShape(slide, 0, 0, 720, H, C.green, "none");
  addImage(slide, path.join(WORKSPACE, "opendesign-prototype/review/ai-teacher-editor.jpg"), 720, 0, 560, H, "InquiSpace 教师任务设计界面", { crop: { left: 0.1, top: 0, right: 0.23, bottom: 0 } });
  addShape(slide, 720, 0, 560, H, "#245A481C", "none");
  addText(slide, "INQUISPACE · 知境", 78, 96, 380, 28, { fontSize: 16, color: "#DCE7DF", bold: true });
  addText(slide, "从模糊需求到\n可验收方案", 78, 176, 590, 180, { fontFamily: TITLE_FONT, fontSize: 50, color: C.white, bold: true });
  addText(slide, "InquiSpace 的产品设计、技术决策与 AI 协作实践", 80, 388, 570, 82, { fontSize: 22, color: "#E5ECE7" });
  addText(slide, "单角色沉浸式探究学习系统 · 项目答辩", 80, 612, 520, 28, { fontSize: 14, color: "#CDDBD2" });
  setNotes(slide, `大家好，我今天汇报的项目是 InquiSpace，中文名是“知境”。这次我不会把重点放在功能罗列上，而是想讲清楚，我怎样把一份范围较大、存在歧义的需求，逐步转化为一个边界明确、可以验证的阶段一方案。汇报中我会重点介绍四件事：我如何分析需求，做了哪些产品和技术取舍，我如何与 AI 协作，以及我怎样通过原型、测试和数据约束验证这些决策。`);
}

// 2. Background
{
  const slide = presentation.slides.add();
  addHeader(slide, "项目背景", 2);
  addTitle(slide, "项目背景与目标");
  addBullet(slide, "01", "教师准备成本高", "角色、问题、资料和课堂安排需要反复配置。", 80, 205, 520);
  addBullet(slide, "02", "普通对话缺少边界", "角色可能漂移，回答也可能脱离资料依据。", 80, 315, 520);
  addBullet(slide, "03", "学习过程难以回看", "学生的判断和修正散落在对话中。", 80, 425, 520);
  addShape(slide, 690, 205, 500, 244, C.ochreSoft, "none");
  addShape(slide, 690, 205, 7, 244, C.ochre, "none");
  addText(slide, "项目目标", 728, 237, 200, 30, { fontSize: 18, color: C.ochre, bold: true });
  addText(slide, "让教师创建一个有明确身份和资料边界的角色，引导学生持续探究，并留下可核对的学习过程。", 728, 286, 410, 130, { fontFamily: TITLE_FONT, fontSize: 25, color: "#4F3A25", bold: true });
  const labels = ["教师创建与发布", "学生角色对话", "自动学习报告", "教师查看学情"];
  addLine(slide, 110, 588, 1030, 0, C.green, 2);
  labels.forEach((label, i) => {
    const x = 100 + i * 280;
    addShape(slide, x, 579, 18, 18, C.green, C.paper, 9);
    addText(slide, label, x, 610, 220, 25, { fontSize: 16, color: C.green, bold: true });
  });
  setNotes(slide, `这个项目面向的是主题探究学习。最初我看到三个核心问题。第一，教师需要准备角色、问题和资料，备课成本比较高。第二，普通大模型虽然能对话，但很容易出现身份漂移、超出时代认知或者没有资料依据。第三，学生的思考过程散落在聊天记录里，教师很难快速看出学生提出过什么判断、是否查过资料、有没有修正观点。因此，项目目标不是简单做一个历史角色聊天机器人，而是形成一个完整闭环：教师创建并发布任务，学生与单一角色持续探究，系统整理学习过程，教师再回看学情和原话依据。`);
}

// 3. Requirement correction
{
  const slide = presentation.slides.add();
  addHeader(slide, "需求分析", 3);
  addTitle(slide, "一次需求纠错与两项边界澄清");
  const steps = [
    ["AI 初步判断", "资料能力属于阶段二", "阶段一可以暂不实现资料解析、来源位置和点击原文定位。"],
    ["我的核对", "通用要求仍然生效", "原文第六节已将资料与来源列为核心功能，分阶段验收不能覆盖通用约束。"],
    ["最终修正", "阶段一保留证据链路", "保留 PDF/TXT、证据检索、来源位置和原文定位。资料不足时明确无法确认。"],
  ];
  steps.forEach((s, i) => {
    const x = 78 + i * 378;
    const fill = i === 2 ? C.green : C.white;
    const color = i === 2 ? C.white : C.ink;
    addShape(slide, x, 192, 350, 230, fill, i === 2 ? C.green : C.line);
    addText(slide, s[0], x + 26, 218, 285, 24, { fontSize: 14, color: i === 2 ? "#E8D5BB" : C.ochre, bold: true });
    addText(slide, s[1], x + 26, 262, 295, 50, { fontSize: 21, color, bold: true });
    addText(slide, s[2], x + 26, 326, 295, 70, { fontSize: 16, color: i === 2 ? "#E5ECE7" : C.muted });
  });
  addShape(slide, 78, 464, 535, 128, C.ochreSoft, "none");
  addText(slide, "必填信息不等于逐项填写", 104, 488, 470, 27, { fontSize: 19, color: C.ochre, bold: true });
  addText(slide, "教师给出一句教学设想，其余信息由 AI、默认值和必要追问补齐。", 104, 528, 470, 46, { fontSize: 15, color: "#5F4A32" });
  addShape(slide, 645, 464, 535, 128, C.ochreSoft, "none");
  addText(slide, "最终成果不等于长成果表", 671, 488, 470, 27, { fontSize: 19, color: C.ochre, bold: true });
  addText(slide, "AI 整理学生已经表达的内容，但不替学生补出结论或观点变化。", 671, 528, 470, 46, { fontSize: 15, color: "#5F4A32" });
  setNotes(slide, `需求分析中最重要的一次纠错，发生在“资料与来源”上。AI 最初根据阶段二的“资料增强”判断，阶段一可以先不做资料解析和原文定位。这个方案看起来符合最小实现，但我对照原始任务后发现，第六节已经把资料与来源列为通用核心要求。因此我继续追问，区分了“阶段一基础证据能力”和“阶段二进一步增强”。最终，阶段一仍然保留 PDF 和 TXT、证据检索、来源位置和原文定位。这里还有两项边界澄清。必填信息不代表教师必须逐项填写，最终成果也不代表学生必须再填一张长表。这个案例让我确认，AI 可以帮助裁剪需求，但我必须回到原文核对它有没有遗漏上位约束。`);
}

// 4. Scope decision
{
  const slide = presentation.slides.add();
  addHeader(slide, "范围决策", 4);
  addTitle(slide, "阶段一范围与核心取舍");
  const items = [
    ["方案 A", "只做单角色聊天", "实现较轻，但无法核验回答依据，也无法完成原文回查。"],
    ["方案 B", "首版覆盖多角色", "功能丰富，但角色切换、记忆隔离和发言调度会放大不确定性。"],
    ["最终选择", "单角色加证据链路", "保留资料解析、证据检索、原文定位、角色边界和教师确认。"],
  ];
  items.forEach((item, i) => {
    const x = 78 + i * 378;
    const selected = i === 2;
    addShape(slide, x, 205, 350, 315, selected ? C.green : C.white, selected ? C.green : C.line);
    addText(slide, item[0], x + 28, 235, 280, 24, { fontSize: 15, color: selected ? "#E8D5BB" : C.ochre, bold: true });
    addText(slide, item[1], x + 28, 308, 290, 58, { fontFamily: TITLE_FONT, fontSize: 24, color: selected ? C.white : C.ink, bold: true });
    addText(slide, item[2], x + 28, 392, 290, 86, { fontSize: 16, color: selected ? "#DCE7DF" : C.muted });
  });
  addText(slide, "最小实现的目标是缩小验证范围，同时保留决定教学可信度的能力。", 88, 570, 1080, 44, { fontFamily: TITLE_FONT, fontSize: 25, color: C.green, bold: true, align: "center" });
  setNotes(slide, `需求切分中最重要的取舍，是缩小角色和协作范围，同时保留资料与证据能力。我比较了三条路径。第一条只做单角色聊天，开发最轻，但学生无法核对回答依据。第二条一开始就做多角色、多格式资料和复杂评测，覆盖面大，但首版范围会迅速失控。我最终选择第三条：只做单角色，但完成必要的资料解析、检索、引用和原文定位。单角色已经足够验证最关键的问题，包括身份和时代边界、连续对话稳定性、基于资料回答，以及能否追问学生的理由。多角色切换、圆桌调度、OCR、联网搜索和向量数据库都明确延期。`);
}

// 5. Method
{
  const slide = presentation.slides.add();
  addHeader(slide, "项目方法", 5);
  addTitle(slide, "从需求到验收的实施路径");
  const phases = [
    ["需求分析", "识别歧义和通用约束"], ["边界确定", "锁定阶段一范围"], ["技术方案", "确定最小闭环"],
    ["工程设计", "接口、状态与数据结构"], ["交互原型", "实际操作修正流程"], ["开发测试", "验证规则与异常"], ["验收", "按用例保留证据"],
  ];
  addLine(slide, 100, 305, 1060, 0, C.green, 3);
  phases.forEach((p, i) => {
    const x = 88 + i * 165;
    addShape(slide, x, 292, 26, 26, i >= 4 && i <= 5 ? C.ochre : C.green, C.paper, 13);
    addText(slide, p[0], x - 2, 350, 145, 30, { fontSize: 18, color: C.ink, bold: true });
    addText(slide, p[1], x - 2, 394, 145, 62, { fontSize: 14, color: C.muted });
  });
  addShape(slide, 460, 515, 460, 90, C.ochreSoft, "none");
  addShape(slide, 460, 515, 5, 90, C.ochre, "none");
  addText(slide, "原型暴露的问题会回到接口和数据库设计中修订，文档、交互与实现保持一致。", 490, 539, 400, 46, { fontSize: 16, color: "#5F4A32", bold: true, align: "center" });
  setNotes(slide, `我的实施过程并不是让 AI 一次性生成整个项目，而是按七个阶段推进。首先分析需求，确定阶段一边界，然后设计技术架构和最小实现方案。在此基础上，我先生成详细设计、接口文档和数据库设计，再制作交互原型。原型不是最后的美化步骤，而是验证需求和工程设计的工具。例如，一句话生成方案、自动报告和报告更正，都反过来影响了接口状态和数据库表。之后才进入代码开发、规则测试和验收。整个过程存在回路，而不是一条单向流水线。我要求需求、接口、数据模型和实际交互保持一致。`);
}

// 6. Architecture and alternatives
{
  const slide = presentation.slides.add();
  addHeader(slide, "技术设计", 6);
  addTitle(slide, "技术架构与最小实现方案", "当前选择基于阶段一的小规模验收目标，尚未进行多套技术栈的性能实测");
  const boxes = [
    ["React 前端", "教师、学生与报告界面", C.green, C.white],
    ["FastAPI 后端", "接口校验与业务服务", C.white, C.ink],
    ["显式工作流", "生成、检索、核验与保存", C.white, C.ink],
  ];
  boxes.forEach((b, i) => {
    const y = 220 + i * 115;
    addShape(slide, 70, y, 235, 86, b[2], i === 0 ? C.green : C.line);
    addText(slide, b[0], 88, y + 17, 195, 24, { fontSize: 19, color: b[3], bold: true });
    addText(slide, b[1], 88, y + 50, 195, 20, { fontSize: 13, color: i === 0 ? "#DCE7DF" : C.muted });
  });
  addLine(slide, 318, 343, 45, 0, C.green, 3);
  const rightBoxes = [
    ["模型适配层", "统一调用与输出校验", C.ochreSoft],
    ["BM25 检索", "受控资料容易核对", C.white],
    ["SQLite 与本地文件", "版本、引用与原始资料", C.white],
  ];
  rightBoxes.forEach((b, i) => {
    const y = 220 + i * 115;
    addShape(slide, 375, y, 235, 86, b[2], C.line);
    addText(slide, b[0], 393, y + 17, 195, 24, { fontSize: 18, color: C.ink, bold: true });
    addText(slide, b[1], 393, y + 50, 195, 20, { fontSize: 13, color: C.muted });
  });
  const values = [
    ["比较项", "当前选择", "暂不选择", "升级条件"],
    ["数据库", "SQLite", "PostgreSQL", "多实例部署或并发写入明显增加"],
    ["资料检索", "BM25", "向量检索", "真实问法持续漏检"],
    ["流程编排", "显式 Python 流程", "LangGraph 等框架", "分支、并行和恢复逻辑复杂"],
    ["模型能力", "模型 API", "自建推理", "成本、延迟或安全要求无法满足"],
    ["后台任务", "单进程状态", "Redis / Celery", "需要跨进程队列或水平扩展"],
  ];
  const table = slide.tables.add({ rows: 6, columns: 4, left: 650, top: 205, width: 560, height: 405, columnWidths: [90, 120, 130, 220], values });
  table.borders.assign({ style: "solid", fill: C.line, width: 1 });
  table.cells.block({ row: 0, column: 0, rowCount: 6, columnCount: 4 }).assign({ textStyle: { fontFamily: BODY_FONT, fontSize: 12, color: C.ink }, margins: { left: 8, right: 8, top: 6, bottom: 6 }, verticalAlignment: "middle" });
  table.cells.block({ row: 0, column: 0, rowCount: 1, columnCount: 4 }).assign({ fill: C.green, textStyle: { fontFamily: BODY_FONT, fontSize: 12, color: C.white, bold: true } });
  table.cells.block({ row: 1, column: 0, rowCount: 5, columnCount: 1 }).assign({ fill: C.paper2, textStyle: { fontFamily: BODY_FONT, fontSize: 12, color: C.green, bold: true } });
  setNotes(slide, `技术选型方面，我没有只记录最终答案，而是明确了备选方案和升级条件。前端选择 React、TypeScript 和 Ant Design，后端使用 FastAPI。数据库在 SQLite 和 PostgreSQL 之间选择了 SQLite，因为当前是单机、小规模验收；当出现多实例和高并发写入时再升级。检索在 BM25 和向量检索之间先选 BM25，因为资料量小，结果容易核对；如果真实问法持续漏检，再引入查询改写或向量检索。流程方面，我没有直接使用 LangGraph，而是选择显式 Python 流程，因为当前步骤已经清晰，权限、确认、停止和重试更容易控制。模型先通过 API 接入，后台任务也暂时保持单进程。这里的判断依据是当前阶段，而不是认为这些更复杂的技术永远不需要。`);
}

// 7. API and data
{
  const slide = presentation.slides.add();
  addHeader(slide, "工程设计", 7);
  addTitle(slide, "接口与数据设计", "界面越简洁，后台越需要明确状态、事务和数据来源");
  const states = ["教学意图与草稿", "生成方案与人工修改", "发布版本与会话快照", "学习报告与独立更正"];
  states.forEach((state, i) => {
    const x = 75 + i * 292;
    addShape(slide, x, 205, 260, 62, C.white, C.line);
    addShape(slide, x, 205, 260, 5, C.green, "none");
    addText(slide, state, x + 16, 227, 228, 24, { fontSize: 17, color: C.green, bold: true, align: "center" });
    if (i < 3) addLine(slide, x + 260, 236, 32, 0, C.green, 2);
  });
  const values = [
    ["交互调整", "接口和数据设计"],
    ["一句话生成教学方案", "保存生成结果、人工修改保护和撤销记录"],
    ["学生结束后自动生成报告", "区分学习完成与报告生成状态，保存输入快照并支持单独重试"],
    ["学生补充或更正", "保留原始报告和原话，追加独立更正记录"],
  ];
  const table = slide.tables.add({ rows: 4, columns: 2, left: 75, top: 315, width: 850, height: 250, columnWidths: [270, 580], values });
  table.borders.assign({ style: "solid", fill: C.line, width: 1 });
  table.cells.block({ row: 0, column: 0, rowCount: 4, columnCount: 2 }).assign({ textStyle: { fontFamily: BODY_FONT, fontSize: 15, color: C.ink }, margins: { left: 12, right: 12, top: 8, bottom: 8 }, verticalAlignment: "middle" });
  table.cells.block({ row: 0, column: 0, rowCount: 1, columnCount: 2 }).assign({ fill: C.green, textStyle: { fontFamily: BODY_FONT, fontSize: 15, color: C.white, bold: true } });
  const metrics = [["20", "初版数据表"], ["23", "修订后数据表"], ["3", "新增学习事件、报告与更正"]];
  metrics.forEach((m, i) => {
    const y = 315 + i * 96;
    addText(slide, m[0], 980, y, 180, 48, { fontFamily: "Georgia", fontSize: 38, color: C.green, bold: true, align: "center" });
    addText(slide, m[1], 958, y + 50, 225, 32, { fontSize: 13, color: C.muted, align: "center" });
    if (i < 2) addLine(slide, 975, y + 88, 190, 0, C.line, 1);
  });
  setNotes(slide, `在接口和数据库设计上，我采用了先整体设计，再通过原型修订的方式。最重要的认识是，界面越简洁，后台状态反而越需要严格。例如，教师从逐项填写改成一句话生成方案后，系统需要保存生成结果，保护人工修改，并支持撤销。学生取消长成果表、改为自动报告后，我需要区分“学习已经结束”和“报告已经生成”两个状态。即使报告失败，已有对话也必须保存，报告可以单独重试。为了避免 AI 误解学生，我又增加了独立更正记录，保留原话和原报告。数据库由二十张表调整为二十三张表，新增了学习事件、学习报告和报告更正。`);
}

// 8. Prototype iteration
{
  const slide = presentation.slides.add();
  addHeader(slide, "产品设计", 8);
  addTitle(slide, "原型中的失败结果与三次修订");
  const iter = [
    ["1", "字段驱动", "教师逐项填写主题、目标、角色、时间和资料范围。学生对话结束后还要重复填写结论、角色观点和反思。"],
    ["2", "第一次简化", "AI 已能生成方案和报告，但教师仍会看到“AI 发布前检查”等专业名词，报告还直接展示运行轨迹和 JSON。"],
    ["3", "第二次简化", "教师只看角色、探究内容和课堂安排。学生完成对话即可结束，检查和技术记录全部留在系统内部。"],
  ];
  iter.forEach((it, i) => {
    const y = 190 + i * 130;
    addShape(slide, 74, y, 40, 40, C.green, "none", 20);
    addText(slide, it[0], 74, y + 7, 40, 24, { fontFamily: "Georgia", fontSize: 17, color: C.white, bold: true, align: "center" });
    addText(slide, it[1], 134, y, 360, 28, { fontSize: 19, color: C.ink, bold: true });
    addText(slide, it[2], 134, y + 36, 390, 78, { fontSize: 14, color: C.muted });
    if (i < 2) addLine(slide, 134, y + 118, 385, 0, C.line, 1);
  });
  addShape(slide, 70, 585, 470, 66, C.ochreSoft, "none");
  addText(slide, "信息需要完整，但不应全部转化为用户操作。", 94, 606, 420, 26, { fontSize: 17, color: "#5F4A32", bold: true, align: "center" });
  addImage(slide, path.join(WORKSPACE, "opendesign-prototype/review/simple-preview-desktop.jpg"), 590, 185, 610, 455, "简化后的教师预览与发布界面", { crop: { left: 0.05, top: 0.08, right: 0.02, bottom: 0.12 } });
  addShape(slide, 590, 602, 610, 38, "#245A48EB", "none");
  addText(slide, "最终原型：以教学内容为中心，技术检查留在系统内部", 610, 612, 570, 18, { fontSize: 13, color: C.white, align: "center" });
  setNotes(slide, `原型设计里最有价值的不是最终页面，而是前面几个不理想方案暴露了什么。第一版直接把业务字段变成表单，教师需要逐项填写大量配置，学生对话结束后还要重复填写结论、角色观点和反思。第二版已经加入一句话生成和自动报告，但我实际查看后发现，页面仍然出现“AI 发布前检查”、检查卡片、运行轨迹和 JSON。这些内容对开发排查有用，却不是师生的任务。第三次修改后，教师只需要看和谁对话、探究什么、课堂怎么安排；学生完成对话就可以结束。后台检查和技术记录继续存在，但不再要求用户理解。这个过程说明，功能完整不等于把所有系统状态都展示出来。`);
}

// 9. Teacher demo
{
  const slide = presentation.slides.add();
  addHeader(slide, "功能演示 · 教师端", 9);
  addTitle(slide, "教师创建与发布");
  addImage(slide, path.join(WORKSPACE, "opendesign-prototype/review/ai-teacher-editor.jpg"), 70, 180, 750, 455, "教师一句话生成任务方案界面", { crop: { left: 0.07, top: 0.07, right: 0.03, bottom: 0.08 } });
  const steps = [
    ["1", "描述教学设想", "资料和高级设置按需展开"],
    ["2", "生成并修改方案", "AI 补齐角色、问题链和课堂安排"],
    ["3", "自动执行发布检查", "缺少信息时只提示需要补充的内容"],
    ["4", "选择学生并确认发布", "教学内容和发布对象由教师决定"],
  ];
  steps.forEach((s, i) => {
    const y = 188 + i * 108;
    addShape(slide, 880, y, 38, 38, C.green, "none", 19);
    addText(slide, s[0], 880, y + 6, 38, 24, { fontFamily: "Georgia", fontSize: 16, color: C.white, bold: true, align: "center" });
    addText(slide, s[1], 940, y - 1, 255, 25, { fontSize: 18, color: C.ink, bold: true });
    addText(slide, s[2], 940, y + 31, 255, 42, { fontSize: 13, color: C.muted });
    if (i < 3) addLine(slide, 899, y + 38, 0, 70, C.line, 2);
  });
  setNotes(slide, `这里进入教师端功能演示。演示时我会先输入一句教学设想，例如让学生从一个历史人物的视角探究清朝灭亡。系统根据这句话生成角色、探究问题和课堂安排，教师可以修改，也可以先和角色试聊。接下来进入预览发布页，后台会自动检查历史时间、角色边界、资料状态和必要字段。如果信息不足，页面只告诉教师需要补什么，不展示技术检查过程。最后，教师选择发布学生，并确认教学内容适合本次课堂后发布。这里我想强调，人机职责是分开的：AI 负责准备方案，程序负责确定性检查，教师保留教学和发布决策。`);
}

// 10. Student and reports
{
  const slide = presentation.slides.add();
  addHeader(slide, "功能演示 · 学习闭环", 10);
  addTitle(slide, "学生探究与学习报告");
  addShape(slide, 78, 177, 260, 475, "#26322C", "none", 24);
  addImage(slide, path.join(WORKSPACE, "opendesign-prototype/review/ai-mobile-chat.jpg"), 90, 190, 236, 449, "学生单角色对话界面", { crop: { left: 0, top: 0.08, right: 0, bottom: 0.43 }, radius: 16 });
  addText(slide, "学生对话", 88, 604, 240, 24, { fontSize: 14, color: C.white, bold: true, align: "center" });
  addImage(slide, path.join(WORKSPACE, "opendesign-prototype/review/simple-student-desktop.jpg"), 390, 177, 390, 220, "学生自动学习报告", { crop: { left: 0.16, top: 0.16, right: 0.02, bottom: 0.24 } });
  addShape(slide, 390, 177, 85, 28, C.green, "none");
  addText(slide, "学生报告", 400, 184, 65, 14, { fontSize: 11, color: C.white, bold: true, align: "center" });
  addImage(slide, path.join(WORKSPACE, "opendesign-prototype/review/simple-teacher-desktop.jpg"), 820, 177, 390, 220, "教师教学报告", { crop: { left: 0.16, top: 0.2, right: 0.02, bottom: 0.18 } });
  addShape(slide, 820, 177, 85, 28, C.green, "none");
  addText(slide, "教师报告", 830, 184, 65, 14, { fontSize: 11, color: C.white, bold: true, align: "center" });
  const flow = ["自由提问与表达判断", "查看资料来源和原文", "角色追问理由与反例", "结束后自动整理报告"];
  flow.forEach((f, i) => {
    const x = 390 + (i % 2) * 410;
    const y = 455 + Math.floor(i / 2) * 84;
    addShape(slide, x, y, 380, 58, i === 3 ? C.green : C.paper2, i === 3 ? C.green : C.line);
    addText(slide, f, x + 18, y + 18, 344, 22, { fontSize: 15, color: i === 3 ? C.white : C.ink, bold: true, align: "center" });
  });
  addText(slide, "报告只整理学生已经表达的观点，原话与资料来源可以继续回查。", 408, 627, 770, 28, { fontFamily: TITLE_FONT, fontSize: 20, color: C.green, bold: true, align: "center" });
  setNotes(slide, `学生端的核心是把思考放在对话中。学生可以自由提问，也可以直接表达判断。角色不会只给答案，而是会追问“你的依据是什么”“有没有其他解释”。如果回答使用了资料，学生可以打开来源，回到具体原文位置核对。学生结束探究后，不需要再填写一张长成果表。系统根据真实对话整理学习报告，展示学生表达过的判断、查阅来源的行为、反思和下一步建议。教师端再把这些过程汇总为图表，并支持点击图表回查原话。这里有一条重要限制：报告只能归纳学生已经说过的内容，不能把角色观点当成学生观点，也不能替学生编造尚未形成的结论。`);
}

// 11. AI collaboration case
{
  const slide = presentation.slides.add();
  addHeader(slide, "AI 协作", 11);
  addTitle(slide, "一次具体的 AI 协作迭代");
  const turns = [
    ["我的原始提问", "“教师和学生要填写的内容太多了。教师发布任务时应该让 AI 承担更多准备工作。学生的思考体现在对话过程中，不需要再填写大量成果内容。”", C.green],
    ["AI 第一次方案", "一句话生成任务，学生对话后自动形成报告，教师通过图表查看过程。", C.ochre],
    ["我的判断", "页面仍展示检查卡片、运行轨迹和 JSON。功能正确，但真实师生不需要理解这些内部概念。", C.green],
    ["第二轮修改", "教师只确认教学内容。学生直接对话，报告优先展示小结、图表和原话依据。", C.ochre],
  ];
  turns.forEach((t, i) => {
    const x = 70 + i * 295;
    addShape(slide, x, 190, 270, 330, C.white, C.line);
    addShape(slide, x, 190, 270, 6, t[2], "none");
    addText(slide, t[0], x + 20, 220, 230, 24, { fontSize: 14, color: t[2], bold: true });
    addText(slide, t[1], x + 20, 270, 230, 210, { fontFamily: i === 0 ? TITLE_FONT : BODY_FONT, fontSize: i === 0 ? 17 : 16, color: i === 0 ? C.ink : C.muted, bold: i !== 0 });
  });
  addShape(slide, 70, 560, 550, 72, C.paper2, "none");
  addText(slide, "AI 负责", 92, 578, 90, 20, { fontSize: 15, color: C.green, bold: true });
  addText(slide, "提出方案、修改原型、同步详细设计与接口数据文档", 182, 578, 410, 35, { fontSize: 14, color: C.muted });
  addShape(slide, 660, 560, 550, 72, C.ochreSoft, "none");
  addText(slide, "我负责", 682, 578, 80, 20, { fontSize: 15, color: C.ochre, bold: true });
  addText(slide, "判断真实用户是否需要这些操作，并通过页面和测试验证结果", 762, 578, 420, 35, { fontSize: 14, color: "#5F4A32" });
  setNotes(slide, `这一页是我认为最能代表人机协作方式的案例。我的原始反馈是，教师和学生要填写的内容太多，教师准备工作应该更多交给 AI，学生的思考应该体现在对话里。AI 第一轮提出了一句话生成、自动报告和教师图表，我接受了这个方向。但我继续检查原型时发现，页面仍然展示检查卡片、运行轨迹和 JSON。这说明方案在功能上正确，在真实用户体验上仍然不合适。我要求第二轮修改，把技术检查留在后台，只向教师呈现角色、探究内容和课堂安排，只向学生呈现对话与学习报告。这个案例中，AI 负责快速生成方案、修改原型和同步文档，我负责判断、取舍和验证。`);
}

// 12. Difficulty
{
  const slide = presentation.slides.add();
  addHeader(slide, "困难与解决", 12);
  addTitle(slide, "减少操作负担，同时保留真实学习过程");
  addShape(slide, 75, 200, 410, 175, C.white, C.line);
  addShape(slide, 75, 200, 410, 6, C.ochre, "none");
  addText(slide, "大量表单", 105, 232, 340, 32, { fontSize: 22, color: C.ink, bold: true });
  addText(slide, "结构化信息容易收集，但教师和学生需要重复填写，操作脱离教学活动。", 105, 286, 340, 66, { fontSize: 16, color: C.muted });
  addShape(slide, 548, 215, 150, 150, C.paper, C.green, 75);
  addText(slide, "对话作为\n原始记录", 565, 257, 116, 68, { fontFamily: TITLE_FONT, fontSize: 20, color: C.green, bold: true, align: "center", valign: "middle" });
  addShape(slide, 760, 200, 410, 175, C.white, C.line);
  addShape(slide, 760, 200, 410, 6, C.green, "none");
  addText(slide, "全部交给 AI", 790, 232, 340, 32, { fontSize: 22, color: C.ink, bold: true });
  addText(slide, "操作简单，但报告可能出现学生没有表达过的判断和观点变化。", 790, 286, 340, 66, { fontSize: 16, color: C.muted });
  const roles = [
    ["学生", "在对话中表达判断、依据和反思"], ["AI", "生成方案、提出追问、整理已有表达"],
    ["教师", "确认教学内容、发布对象和报告使用"], ["程序", "管理权限、状态、引用和可核对统计"],
  ];
  roles.forEach((r, i) => {
    const x = 75 + i * 284;
    addShape(slide, x, 440, 255, 125, C.paper2, "none");
    addShape(slide, x, 440, 5, 125, C.green, "none");
    addText(slide, r[0], x + 24, 464, 200, 24, { fontSize: 19, color: C.green, bold: true });
    addText(slide, r[1], x + 24, 506, 200, 42, { fontSize: 14, color: C.muted });
  });
  addText(slide, "报告失败可以单独重试，学习过程、原话和原始报告继续保留。", 150, 612, 980, 30, { fontFamily: TITLE_FONT, fontSize: 20, color: C.green, bold: true, align: "center" });
  setNotes(slide, `整个项目中最大的困难，是减少师生操作负担，同时保留真实、可追溯的学习过程。如果要求教师和学生填写大量表单，数据很容易结构化，但使用成本太高。如果全部交给 AI，报告看起来会很完整，却可能出现学生没有表达过的判断。最终我把原始对话作为事实来源，并划分四类职责。学生负责表达自己的判断、依据和反思；AI 负责生成、追问和整理；教师负责确认教学内容与发布对象；程序负责权限、状态、引用和统计。学习完成和报告生成也被设计为不同状态。报告失败可以单独重试，不能要求学生重新学习，原话和旧报告也不能被覆盖。`);
}

// 13. Verification
{
  const slide = presentation.slides.add();
  addHeader(slide, "验证结果", 13);
  addTitle(slide, "测试、验收与当前边界");
  addText(slide, "已经完成的验证", 78, 190, 480, 30, { fontSize: 22, color: C.green, bold: true });
  const metrics = [["47", "原型状态规则测试"], ["23", "数据库设计表"], ["69", "建库、约束与事务检查"]];
  metrics.forEach((m, i) => {
    const x = 78 + i * 190;
    addShape(slide, x, 240, 170, 120, C.white, C.line);
    addShape(slide, x, 240, 170, 5, C.green, "none");
    addText(slide, m[0], x, 264, 170, 48, { fontFamily: "Georgia", fontSize: 38, color: C.green, bold: true, align: "center" });
    addText(slide, m[1], x + 10, 320, 150, 28, { fontSize: 12, color: C.muted, align: "center" });
  });
  addText(slide, "• 教师创建发布、学生探究、报告更正与图表回查\n• 桌面端、移动端布局与图文报告导出", 85, 405, 540, 88, { fontSize: 16, color: C.ink });
  addShape(slide, 660, 190, 530, 365, C.white, C.line);
  addShape(slide, 660, 190, 530, 5, C.ochre, "none");
  addText(slide, "仍需正式系统验收", 690, 220, 460, 30, { fontSize: 22, color: C.ochre, bold: true });
  addText(slide, "• 真实模型连续 10 轮的角色稳定性\n• PDF/TXT 解析、检索、引用和原文定位\n• 未来信息拦截与私人动机不编造\n• 报告是否准确归纳学生真实表达\n• 服务端认证、权限隔离和真实课堂试用", 690, 278, 455, 230, { fontSize: 16, color: C.ink });
  addShape(slide, 78, 590, 1110, 62, C.ochreSoft, "none");
  addText(slide, "当前成果证明交互流程和部分数据约束可行。原型回答仍由本地规则模拟，不能据此宣称真实 AI 已通过教学验收。", 105, 610, 1055, 28, { fontSize: 14, color: "#5F4A32", bold: true, align: "center" });
  setNotes(slide, `当前已经完成的验证包括四十七项原型状态规则测试、二十三张表的数据库设计，以及六十九项建库、约束和事务检查。原型方面，我实际走通了教师创建发布、缺失信息阻止发布、学生结束探究、报告更正和教师图表回查，也检查了桌面与手机布局和图文报告导出。但是我需要明确当前边界：原型中的方案生成、回答和总结主要由本地规则与模板模拟，不能用这些结果证明真实模型已经达到教学要求。正式验收还需要接入真实 PDF 和 TXT，验证连续十轮角色稳定性、未来信息拦截、引用准确性、权限隔离和报告归纳质量。我希望用这种区分保证汇报结论真实可信。`);
}

// 14. Closing
{
  const slide = presentation.slides.add();
  slide.background.fill = C.paper;
  addShape(slide, 0, 0, W, H, C.paper, "none");
  addShape(slide, 68, 42, 28, 28, C.green, "none", 6);
  addText(slide, "知", 68, 44, 28, 24, { fontFamily: TITLE_FONT, fontSize: 15, color: C.white, bold: true, align: "center" });
  addText(slide, "InquiSpace", 106, 44, 160, 24, { fontSize: 15, color: C.green, bold: true });
  addText(slide, "项目总结与个人思考", 68, 110, 620, 60, { fontFamily: TITLE_FONT, fontSize: 40, color: C.ink, bold: true });
  const lines = [
    ["系统设计", "形成教师创建、学生探究和学习报告的完整闭环"],
    ["技术设计", "通过状态、权限、证据和事务保持过程可追溯"],
    ["AI 协作", "让 AI 承担分析与执行，对输出持续核对和验证"],
    ["个人决策", "识别歧义、控制范围、做出取舍，并对结果负责"],
  ];
  lines.forEach((l, i) => {
    const y = 220 + i * 88;
    addText(slide, l[0], 78, y, 120, 30, { fontSize: 20, color: C.green, bold: true });
    addText(slide, l[1], 215, y, 480, 42, { fontSize: 17, color: C.ink });
    addLine(slide, 78, y + 60, 610, 0, C.line, 1);
  });
  addShape(slide, 760, 135, 440, 420, C.green, "none");
  addText(slide, "使用 AI 完成复杂项目的关键，是建立清晰的边界、判断标准和验证机制。", 810, 235, 340, 220, { fontFamily: TITLE_FONT, fontSize: 29, color: C.white, bold: true, align: "center", valign: "middle" });
  addText(slide, "谢谢", 910, 610, 140, 35, { fontFamily: TITLE_FONT, fontSize: 25, color: C.green, bold: true, align: "center" });
  addText(slide, "14 / 14", 1170, 684, 70, 18, { fontSize: 11, color: C.muted, align: "right" });
  setNotes(slide, `最后总结一下。产品层面，我完成了教师创建、学生探究和自动报告的完整闭环设计。技术层面，我用状态、权限、证据和事务来保证过程可追溯。AI 协作层面，我没有把 AI 当成最终决策者，而是让它承担方案生成、文档同步和代码执行，再由我核对需求、判断体验并通过测试验证。对我个人而言，这个项目最大的收获，是学会在使用 AI 提高效率的同时，始终保留对目标、边界和结果的责任。使用 AI 完成复杂项目的关键，不是让它生成更多内容，而是建立清晰的边界、判断标准和验证机制。我的汇报到这里，谢谢各位老师。`);
}

await fs.rm(BUILD_DIR, { recursive: true, force: true });
await fs.mkdir(RENDER_DIR, { recursive: true });
await fs.mkdir(OUTPUT_DIR, { recursive: true });

for (const [index, slide] of presentation.slides.items.entries()) {
  const png = await presentation.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(path.join(RENDER_DIR, `slide-${String(index + 1).padStart(2, "0")}.png`), new Uint8Array(await png.arrayBuffer()));
}
const montage = await presentation.export({ format: "webp", montage: true });
await fs.writeFile(path.join(BUILD_DIR, "montage.webp"), new Uint8Array(await montage.arrayBuffer()));
await (await PresentationFile.exportPptx(presentation)).save(CANDIDATE);

const { finalizePresentation } = await import(pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href);
const requirements = {
  explicitTotalSlideCount: 14,
  requiredNativeTableOwnerSlides: [6, 7],
  requiredNativeChartOwnerSlides: [],
};
const result = await finalizePresentation({
  ...requirements,
  workspaceDir: WORKSPACE,
  candidatePath: CANDIDATE,
  finalPath: FINAL_PPTX,
  pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", "12192000,6858000",
    "--validate-bullet-geometry",
    "--validate-heading-fit",
    "--require-native-table-slide", "6",
    "--require-native-table-slide", "7",
  ],
  requiredNativeTableOwnerSlides: [6, 7],
  fontPolicy: { basis: "design", families: ["Aptos"] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(BUILD_DIR, "validation.json"),
});

console.log(JSON.stringify({ final: FINAL_PPTX, renders: RENDER_DIR, montage: path.join(BUILD_DIR, "montage.webp"), validation: result }, null, 2));
