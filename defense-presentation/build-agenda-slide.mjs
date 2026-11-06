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

const BUILD_DIR = path.join(WORKSPACE, ".codex-agenda-build");
const RENDER_DIR = path.join(BUILD_DIR, "renders");
const OUTPUT_DIR = path.join(WORKSPACE, "defense-presentation", "output");
const CANDIDATE = path.join(BUILD_DIR, "candidate.pptx");
const FINAL_PPTX = path.join(OUTPUT_DIR, "InquiSpace_目录页_可插入.pptx");

const W = 1280;
const H = 720;
const C = {
  paper: "#F7F8F4",
  paper2: "#EEF1E8",
  ink: "#253129",
  muted: "#667068",
  green: "#245A48",
  greenSoft: "#DCE7D3",
  ochre: "#9A6A35",
  line: "#D7DDD1",
  white: "#FFFFFF",
};
const BODY_FONT = "Arial Unicode MS";
const TITLE_FONT = "Songti SC";

function addShape(slide, x, y, width, height, fill = "none", line = "none", radius = 0) {
  return slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    position: { left: x, top: y, width, height },
    fill,
    line: { style: "solid", fill: line, width: line === "none" ? 0 : 1 },
    ...(radius ? { borderRadius: radius } : {}),
  });
}

function addText(slide, text, x, y, width, height, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width, height },
    fill: options.fill ?? "none",
    line: { style: "solid", fill: options.line ?? "none", width: options.line && options.line !== "none" ? 1 : 0 },
  });
  shape.text = text;
  shape.text.style = {
    fontFamily: options.fontFamily ?? BODY_FONT,
    fontSize: options.fontSize ?? 20,
    color: options.color ?? C.ink,
    bold: options.bold ?? false,
    alignment: options.align ?? "left",
    verticalAlignment: options.valign ?? "top",
  };
  shape.text.insets = options.insets ?? 0;
  return shape;
}

function addLine(slide, x, y, width, height, color = C.line, lineWidth = 1) {
  return slide.shapes.add({
    geometry: "line",
    position: { left: x, top: y, width, height },
    fill: "none",
    line: { style: "solid", fill: color, width: lineWidth },
  });
}

await fs.rm(BUILD_DIR, { recursive: true, force: true });
await fs.mkdir(RENDER_DIR, { recursive: true });
await fs.mkdir(OUTPUT_DIR, { recursive: true });

const presentation = Presentation.create({ slideSize: { width: W, height: H } });
const slide = presentation.slides.add();
slide.background.fill = C.paper;

addShape(slide, 0, 0, W, H, C.paper, "none");
addShape(slide, 68, 40, 28, 28, C.green, "none", 6);
addText(slide, "知", 68, 42, 28, 24, {
  fontFamily: TITLE_FONT,
  fontSize: 15,
  color: C.white,
  bold: true,
  align: "center",
  valign: "middle",
});
addText(slide, "InquiSpace", 106, 42, 160, 24, { fontSize: 15, color: C.green, bold: true });
addText(slide, "汇报目录", 1010, 44, 190, 22, { fontSize: 13, color: C.muted, align: "right" });

addText(slide, "汇报目录", 68, 92, 1120, 60, {
  fontFamily: TITLE_FONT,
  fontSize: 36,
  color: C.ink,
  bold: true,
});
addText(slide, "围绕需求判断、技术取舍、系统体验和 AI 协作展开", 70, 154, 1110, 30, {
  fontSize: 17,
  color: C.muted,
});

const agenda = [
  ["01", "项目背景与需求决策", "需求歧义、阶段一边界与最小实现目标", "03–06"],
  ["02", "技术架构与产品设计", "技术选型、接口数据设计与原型迭代", "07–09"],
  ["03", "系统功能演示", "教师创建发布、学生探究与学习报告", "10–11"],
  ["04", "AI 协作、困难与验收", "协作案例、核心难题、验证结果与当前边界", "12–15"],
];

const startY = 208;
const rowHeight = 100;
agenda.forEach((item, index) => {
  const y = startY + index * rowHeight;
  const active = index === 0;

  if (active) addShape(slide, 68, y - 7, 1108, 82, C.paper2, "none");
  addShape(slide, 68, y - 7, 5, 82, index === 3 ? C.ochre : C.green, "none");
  addText(slide, item[0], 92, y + 5, 72, 44, {
    fontFamily: "Georgia",
    fontSize: 28,
    color: index === 3 ? C.ochre : C.green,
    bold: true,
  });
  addText(slide, item[1], 190, y, 550, 34, { fontSize: 23, color: C.ink, bold: true });
  addText(slide, item[2], 190, y + 42, 700, 24, { fontSize: 14, color: C.muted });
  addText(slide, item[3], 1040, y + 13, 110, 28, {
    fontFamily: "Georgia",
    fontSize: 18,
    color: index === 3 ? C.ochre : C.green,
    bold: true,
    align: "right",
  });
  if (index < agenda.length - 1) addLine(slide, 190, y + 82, 960, 0, C.line, 1);
});

addShape(slide, 68, 626, 1108, 2, C.green, "none");
addText(slide, "汇报重点：我如何分析问题、做出决策，并用 AI 推进与验证方案", 70, 646, 960, 26, {
  fontSize: 14,
  color: C.green,
  bold: true,
});
addText(slide, "02 / 15", 1170, 684, 70, 18, { fontSize: 11, color: C.muted, align: "right" });

slide.speakerNotes.text = "接下来我会从四个部分展开。首先介绍项目背景，以及我如何分析需求、确定阶段一边界。第二部分说明技术架构、接口数据设计和原型迭代。第三部分演示教师端、学生端和学习报告的完整闭环。最后介绍我与 AI 的具体协作方式、项目中最大的困难，以及目前完成的验证和仍需正式验收的边界。";
slide.speakerNotes.setVisible(true);

const preview = await presentation.export({ slide, format: "png", scale: 1 });
await fs.writeFile(path.join(RENDER_DIR, "agenda-slide.png"), new Uint8Array(await preview.arrayBuffer()));
await (await PresentationFile.exportPptx(presentation)).save(CANDIDATE);

const { finalizePresentation } = await import(pathToFileURL(
  path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs"),
).href);

const result = await finalizePresentation({
  explicitTotalSlideCount: 1,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
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
  ],
  fontPolicy: { basis: "design", families: ["Aptos"] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(BUILD_DIR, "validation.json"),
});

console.log(JSON.stringify({
  final: FINAL_PPTX,
  preview: path.join(RENDER_DIR, "agenda-slide.png"),
  validation: result,
}, null, 2));
