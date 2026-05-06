from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


OUT_DIR = Path(__file__).resolve().parent
DOCX_PATH = OUT_DIR / "吴文博_AI后端_RAG实习_简历_优化版.docx"

ACCENT = "2F66D0"
ACCENT_DARK = "1F4FA8"
ACCENT_LIGHT = "EEF4FF"
TEXT = "20242A"
MUTED = "6B7280"
BORDER = "D8E2F3"
FILL = "F8FAFD"


def set_font(run, size: float = 9.2, bold: bool = False, color: str = TEXT) -> None:
    """Apply resume typography to one run."""
    run.font.name = "Arial"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def add_run(paragraph, text: str, size: float = 9.2, bold: bool = False, color: str = TEXT):
    """Append one formatted run to a paragraph."""
    run = paragraph.add_run(text)
    set_font(run, size=size, bold=bold, color=color)
    return run


def shade_cell(cell, fill: str) -> None:
    """Set cell background color."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_borders(cell, color: str = BORDER, size: str = "6") -> None:
    """Apply quiet grid borders to a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right"):
        tag = borders.find(qn(f"w:{edge}"))
        if tag is None:
            tag = OxmlElement(f"w:{edge}")
            borders.append(tag)
        tag.set(qn("w:val"), "single")
        tag.set(qn("w:sz"), size)
        tag.set(qn("w:color"), color)


def set_cell_margins(cell, top: int = 80, start: int = 110, bottom: int = 80, end: int = 110) -> None:
    """Set Word cell margins in DXA."""
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for key, value in {"top": top, "start": start, "bottom": bottom, "end": end}.items():
        node = tc_mar.find(qn(f"w:{key}"))
        if node is None:
            node = OxmlElement(f"w:{key}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_width(table, widths_cm: Sequence[float]) -> None:
    """Set fixed table and column widths."""
    table.autofit = False
    table.allow_autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    total_dxa = int(sum(widths_cm) * 567)
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total_dxa))
    tbl_w.set(qn("w:type"), "dxa")

    tbl_grid = table._tbl.tblGrid
    for child in list(tbl_grid):
        tbl_grid.remove(child)
    for width in widths_cm:
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(int(width * 567)))
        tbl_grid.append(grid_col)

    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            cell.width = Cm(widths_cm[idx])
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(int(widths_cm[idx] * 567)))
            tc_w.set(qn("w:type"), "dxa")
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)


def configure_document(doc: Document) -> None:
    """Configure page geometry and base styles."""
    section = doc.sections[0]
    section.start_type = WD_SECTION_START.NEW_PAGE
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.15)
    section.bottom_margin = Cm(1.05)
    section.left_margin = Cm(1.35)
    section.right_margin = Cm(1.35)

    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    normal.font.size = Pt(9.2)
    normal.paragraph_format.line_spacing = 1.03
    normal.paragraph_format.space_after = Pt(2.2)


def add_section_heading(doc: Document, title: str) -> None:
    """Add a compact colored section heading."""
    table = doc.add_table(rows=1, cols=2)
    set_table_width(table, [0.22, 18.08])
    for cell in table.rows[0].cells:
        set_cell_borders(cell, color="FFFFFF", size="0")
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    shade_cell(table.cell(0, 0), ACCENT)
    shade_cell(table.cell(0, 1), ACCENT_LIGHT)
    p = table.cell(0, 1).paragraphs[0]
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    add_run(p, title, size=11.3, bold=True, color=ACCENT_DARK)


def add_key_value_line(doc: Document, left: str, right: str = "", url: str = "") -> None:
    """Add one resume item title line."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(1)
    add_run(p, left, size=9.9, bold=True)
    if right:
        add_run(p, f"    {right}", size=8.8, color=MUTED)
    if url:
        add_run(p, f"    {url}", size=8.6, color=ACCENT)


def add_rich_paragraph(doc: Document, parts: Iterable[tuple[str, bool, str]], size: float = 8.95) -> None:
    """Add a paragraph composed of highlighted and normal text runs."""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.42)
    p.paragraph_format.first_line_indent = Cm(-0.22)
    p.paragraph_format.space_after = Pt(1.8)
    p.paragraph_format.line_spacing = 1.02
    add_run(p, "• ", size=size, color=ACCENT, bold=True)
    for text, bold, color in parts:
        add_run(p, text, size=size, bold=bold, color=color)


def add_label_paragraph(doc: Document, label: str, text: str) -> None:
    """Add a STAR label paragraph."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.keep_with_next = True
    add_run(p, label, size=8.9, bold=True, color=ACCENT_DARK)
    add_run(p, "  ", size=8.9)
    add_run(p, text, size=8.85, color=TEXT)


def add_action(doc: Document, title: str, parts: Iterable[tuple[str, bool, str]]) -> None:
    """Add one layered Action bullet under STAR."""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.58)
    p.paragraph_format.first_line_indent = Cm(-0.26)
    p.paragraph_format.space_after = Pt(1.5)
    p.paragraph_format.line_spacing = 1.02
    add_run(p, "• ", size=8.75, bold=True, color=ACCENT)
    add_run(p, f"{title}：", size=8.75, bold=True, color=ACCENT_DARK)
    for text, bold, color in parts:
        add_run(p, text, size=8.75, bold=bold, color=color)


def add_skill_table(doc: Document) -> None:
    """Add a structured skill table."""
    rows = [
        (
            "语言与后端工程",
            "精通",
            "Python（asyncio / async-generator）、FastAPI 分层架构、Pydantic v2 数据建模、SSE 实时流式推送",
        ),
        (
            "RAG / Agent",
            "精通",
            "RAG 全链路设计（Chunking -> Embedding -> Hybrid Search -> Rerank）、LangChain / LangGraph（State Machine、Checkpointer、Send API）",
        ),
        (
            "向量检索与模型服务",
            "熟悉",
            "Qdrant（payload 过滤、MMR 多样性检索）、DashScope Embedding、向量数据库性能调优（HNSW 参数）、Prompt Engineering",
        ),
        (
            "数据与工程化",
            "熟悉",
            "MySQL / Redis、Docker Compose 多服务编排、Vue3 + Vite 前端协作",
        ),
        (
            "拓展技术",
            "了解",
            "C++、Java、Cursor / Claude Code AI 辅助工程",
        ),
    ]
    table = doc.add_table(rows=1, cols=3)
    set_table_width(table, [3.25, 2.0, 13.05])
    headers = ["技能类别", "熟练程度", "具体技术栈"]
    for idx, text in enumerate(headers):
        cell = table.cell(0, idx)
        shade_cell(cell, ACCENT_LIGHT)
        set_cell_borders(cell)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if idx < 2 else WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_after = Pt(0)
        add_run(p, text, size=8.65, bold=True, color=ACCENT_DARK)
    for row in rows:
        cells = table.add_row().cells
        for idx, text in enumerate(row):
            cell = cells[idx]
            shade_cell(cell, "FFFFFF" if idx != 1 else FILL)
            set_cell_borders(cell)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if idx < 2 else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_after = Pt(0)
            add_run(p, text, size=8.35, bold=(idx < 2), color=TEXT if idx != 1 else ACCENT_DARK)
    set_table_width(table, [3.25, 2.0, 13.05])
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def add_impact_callout(doc: Document) -> None:
    """Add a visual callout for technical influence."""
    table = doc.add_table(rows=1, cols=2)
    set_table_width(table, [3.2, 15.1])
    for cell in table.rows[0].cells:
        shade_cell(cell, FILL)
        set_cell_borders(cell, color=BORDER, size="6")
        set_cell_margins(cell, top=90, bottom=90, start=130, end=130)
    left = table.cell(0, 0).paragraphs[0]
    left.alignment = WD_ALIGN_PARAGRAPH.CENTER
    left.paragraph_format.space_after = Pt(0)
    add_run(left, "5.5w+", size=16, bold=True, color=ACCENT_DARK)
    left.add_run().add_break(WD_BREAK.LINE)
    add_run(left, "累计阅读", size=8.4, bold=True, color=MUTED)
    right = table.cell(0, 1).paragraphs[0]
    right.paragraph_format.space_after = Pt(0)
    add_run(right, "技术影响力：", size=9.2, bold=True, color=ACCENT_DARK)
    add_run(right, "持续输出 AI 工程与 RAG 技术博客；RAG chunk 切分、Embedding、检索系列文章阅读量 ", size=8.9)
    add_run(right, "3.1w+", size=8.9, bold=True, color=ACCENT_DARK)
    add_run(right, "，曾获知乎首页推荐。", size=8.9)


def build_docx() -> None:
    """Build the optimized AI backend / RAG intern resume."""
    doc = Document()
    configure_document(doc)

    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(0)
    add_run(title, "吴文博", size=22, bold=True, color=TEXT)

    sub = doc.add_paragraph()
    sub.paragraph_format.space_after = Pt(1)
    add_run(sub, "AI 后端 / RAG / Agent 工程实习", size=10.2, bold=True, color=ACCENT_DARK)

    contact = doc.add_paragraph()
    contact.paragraph_format.space_after = Pt(3)
    add_run(contact, "电话：19500206093  |  邮箱：369546137@qq.com  |  知乎 / 公众号 ", size=8.8, color=TEXT)
    add_run(contact, "5.5w+ 阅读", size=8.8, bold=True, color=ACCENT_DARK)

    add_section_heading(doc, "教育经历")
    add_key_value_line(doc, "江西理工大学 · 软件工程 · 本科", "2024.09 - 2028.06（预计）")
    add_rich_paragraph(doc, [("GPA 3.3/4.0，专业前 14%；两次三等奖学金；英语六级。", False, TEXT)], size=8.8)
    add_rich_paragraph(doc, [("竞赛：华教杯数学竞赛省级三等奖；蓝桥杯省级三等奖。", False, TEXT)], size=8.8)

    add_section_heading(doc, "专业技能")
    add_skill_table(doc)

    add_section_heading(doc, "项目经历")
    add_key_value_line(doc, "AutoMedia · 多智能体 RAG 内容创作平台", "2026.04 - 至今")
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    add_run(p, "独立设计并实现 · 核心开发者", size=8.55, color=MUTED)
    add_run(p, "    FastAPI  LangGraph  Qdrant  DashScope  Redis  SSE  Docker Compose", size=8.35, color=ACCENT_DARK)

    add_label_paragraph(
        doc,
        "Situation",
        "长文章自动生成场景中，多步骤 Agent 链路（RAG 检索->大纲->正文->配图->合成）耗时长、状态不透明，用户无法感知进度，出错后无法定位节点。",
    )
    add_label_paragraph(doc, "Task", "设计一套可观测、可恢复的多智能体编排框架，并实现端到端 RAG 知识增强写作。")
    add_action(
        doc,
        "RAG",
        [
            ("实现两级 Chunking 策略（Markdown Header 粗切 + 中文递归精切，chunk 均值约 480 token），结合 DashScope Embedding 写入 Qdrant；检索层叠加 ", False, TEXT),
            ("MMR 多样性过滤", True, ACCENT_DARK),
            (" 与 payload 元数据过滤，在本地 100 篇知识库测试中，Top-3 检索准确率达 ", False, TEXT),
            ("87%", True, ACCENT_DARK),
            ("，较单一语义检索提升约 +18%。", False, TEXT),
        ],
    )
    add_action(
        doc,
        "Agent",
        [
            ("基于 FastAPI async-generator + ", False, TEXT),
            ("SSE", True, ACCENT_DARK),
            (" 向前端实时推送 8 个 Agent 节点状态（阶段名、耗时、token 消耗），长任务平均端到端耗时约 38s；并行配图节点（", False, TEXT),
            ("asyncio.gather", True, ACCENT_DARK),
            ("）相对串行", False, TEXT),
            ("缩短 ~45%", True, ACCENT_DARK),
            ("。", False, TEXT),
        ],
    )
    add_action(
        doc,
        "升级规划",
        [
            ("规划 ", False, TEXT),
            ("LangGraph", True, ACCENT_DARK),
            (" 渐进式迁移方案：将共享状态重构为 TypedDict State，引入 Checkpointer 实现断点续跑，通过条件边支持错误路由，Send API 驱动并行配图节点，具备工程落地路径。", False, TEXT),
        ],
    )
    add_label_paragraph(
        doc,
        "Result",
        "本地完整链路联调通过率 100%；入库 Pipeline 支持 dry-run 模式，向量 payload 与 MySQL 元数据强一致；RAG 检索 + SSE 推送架构具备生产部署条件。",
    )

    add_key_value_line(
        doc,
        "MDNote Markdown 笔记编辑工具 · 独立开发",
        "用户 100+",
        "https://www.dali-frt.asia/",
    )
    add_rich_paragraph(doc, [("使用 Cursor 独立完成需求拆解、编辑器功能开发与发布迭代，覆盖 Markdown 编辑、预览与常用笔记工作流。", False, TEXT)], size=8.75)
    add_rich_paragraph(doc, [("产品实际使用人数 ", False, TEXT), ("100+", True, ACCENT_DARK), ("，具备从个人工具到真实用户反馈闭环的完整开发经验。", False, TEXT)], size=8.75)

    add_section_heading(doc, "技术影响力")
    add_impact_callout(doc)

    for paragraph in doc.paragraphs:
        paragraph.paragraph_format.space_before = Pt(0)

    doc.save(DOCX_PATH)


if __name__ == "__main__":
    build_docx()
    print(DOCX_PATH)
