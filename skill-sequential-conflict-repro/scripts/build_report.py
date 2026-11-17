from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = PROJECT_ROOT / "outputs" / "results.json"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "Skill顺序调用许可证冲突复现报告.docx"

BLACK = RGBColor(0, 0, 0)
WHITE = RGBColor(255, 255, 255)
MUTED = RGBColor(90, 90, 90)
DARK_BLUE = "1F4E79"
PALE_BLUE = "EAF2F8"
PALE_GRAY = "F5F7F9"
BORDER_GRAY = "D9D9D9"


def set_run_font(
    run,
    name: str = "Microsoft YaHei",
    size: float | None = None,
    bold: bool | None = None,
    color: RGBColor | None = None,
) -> None:
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def set_paragraph_spacing(paragraph, before=0, after=0, line=1.2) -> None:
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = line


def remove_paragraph_borders(paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    borders = p_pr.find(qn("w:pBdr"))
    if borders is not None:
        p_pr.remove(borders)


def remove_style_borders(style) -> None:
    p_pr = style.element.get_or_add_pPr()
    borders = p_pr.find(qn("w:pBdr"))
    if borders is not None:
        p_pr.remove(borders)


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=58, start=78, bottom=58, end=78) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_borders(table, color=BORDER_GRAY, size=6) -> None:
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = f"w:{edge}"
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(size))
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    marker = OxmlElement("w:tblHeader")
    marker.set(qn("w:val"), "true")
    tr_pr.append(marker)


def prevent_row_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    marker = OxmlElement("w:cantSplit")
    tr_pr.append(marker)


def set_col_width(cell, width_inches: float) -> None:
    cell.width = Inches(width_inches)
    tc_w = cell._tc.get_or_add_tcPr().first_child_found_in("w:tcW")
    if tc_w is not None:
        tc_w.set(qn("w:type"), "dxa")
        tc_w.set(qn("w:w"), str(int(width_inches * 1440)))


def add_body(doc, text: str, bold_lead: str | None = None, after: float = 6):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(paragraph, after=after, line=1.25)
    if bold_lead and text.startswith(bold_lead):
        run = paragraph.add_run(bold_lead)
        set_run_font(run, size=10.5, bold=True, color=BLACK)
        run = paragraph.add_run(text[len(bold_lead) :])
        set_run_font(run, size=10.5, color=BLACK)
    else:
        run = paragraph.add_run(text)
        set_run_font(run, size=10.5, color=BLACK)
    return paragraph


def add_bullet(doc, text: str, bold_lead: str | None = None):
    paragraph = doc.add_paragraph(style="List Bullet")
    paragraph.paragraph_format.left_indent = Inches(0.23)
    paragraph.paragraph_format.first_line_indent = Inches(-0.16)
    set_paragraph_spacing(paragraph, after=4, line=1.2)
    if bold_lead and text.startswith(bold_lead):
        run = paragraph.add_run(bold_lead)
        set_run_font(run, size=10.25, bold=True, color=BLACK)
        run = paragraph.add_run(text[len(bold_lead) :])
        set_run_font(run, size=10.25, color=BLACK)
    else:
        run = paragraph.add_run(text)
        set_run_font(run, size=10.25, color=BLACK)
    return paragraph


def add_heading(doc, text: str, level: int = 1):
    paragraph = doc.add_paragraph(style=f"Heading {level}")
    paragraph.paragraph_format.keep_with_next = True
    set_paragraph_spacing(
        paragraph,
        before=13 if level == 1 else 9,
        after=6 if level == 1 else 4,
        line=1.08,
    )
    run = paragraph.add_run(text)
    set_run_font(
        run,
        size=15.5 if level == 1 else 12.5,
        bold=True,
        color=BLACK,
    )
    return paragraph


def add_caption(doc, text: str) -> None:
    paragraph = doc.add_paragraph()
    set_paragraph_spacing(paragraph, before=3, after=9, line=1.0)
    run = paragraph.add_run(text)
    set_run_font(run, size=8.5, color=MUTED)


def format_table(table, widths: list[float], font_size: float = 8.4) -> None:
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_table_borders(table)
    set_repeat_table_header(table.rows[0])
    for row_idx, row in enumerate(table.rows):
        prevent_row_split(row)
        for col_idx, cell in enumerate(row.cells):
            set_col_width(cell, widths[col_idx])
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if row_idx == 0:
                set_cell_shading(cell, DARK_BLUE)
            elif row_idx % 2 == 0:
                set_cell_shading(cell, PALE_BLUE)
            else:
                set_cell_shading(cell, "FFFFFF")
            for paragraph in cell.paragraphs:
                set_paragraph_spacing(paragraph, line=1.0)
                paragraph.alignment = (
                    WD_ALIGN_PARAGRAPH.CENTER
                    if col_idx == 0
                    else WD_ALIGN_PARAGRAPH.LEFT
                )
                for run in paragraph.runs:
                    set_run_font(
                        run,
                        size=font_size,
                        bold=(row_idx == 0),
                        color=WHITE if row_idx == 0 else BLACK,
                    )


def add_table(
    doc,
    headers: list[str],
    rows: list[list[str]],
    widths: list[float],
    font_size: float = 8.4,
):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for idx, text in enumerate(headers):
        table.rows[0].cells[idx].text = text
    for values in rows:
        cells = table.add_row().cells
        for idx, text in enumerate(values):
            cells[idx].text = str(text)
    format_table(table, widths, font_size)
    return table


def add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    set_run_font(run, size=8.5, color=MUTED)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def main() -> None:
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    results_hash = hashlib.sha256(RESULTS_PATH.read_bytes()).hexdigest()

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.72)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)

    normal = doc.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = BLACK
    normal.paragraph_format.space_after = Pt(6)

    for style_name in ("Title", "Subtitle", "Heading 1", "Heading 2"):
        style = doc.styles[style_name]
        style.font.name = "Microsoft YaHei"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.color.rgb = BLACK
        remove_style_borders(style)

    title = doc.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(8)
    title_run = title.add_run("Skill 顺序调用许可证冲突复现报告")
    set_run_font(title_run, size=20, bold=True, color=BLACK)
    remove_paragraph_borders(title)

    subtitle = doc.add_paragraph(style="Subtitle")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(5)
    subtitle_run = subtitle.add_run("固定 8 个 Skill 版本、6 条正例和 6 条负对照")
    set_run_font(subtitle_run, size=12, color=BLACK)

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(meta, after=15, line=1.0)
    meta_run = meta.add_run("复现日期 2026年11月13日  |  单次 Agent 回放  |  结果 12 / 12")
    set_run_font(meta_run, size=9.5, color=MUTED)

    add_body(
        doc,
        "结论：六条预设调用链均能触发预期许可证冲突，六条负对照均未出现误报。"
        "实验同时确认，许可边界取决于任务用途与输出内容来源，而不是两个 Skill 名称是否同时出现。",
        "结论：",
        after=8,
    )

    add_heading(doc, "一、复现范围")
    add_body(
        doc,
        "本次复现使用附件给出的 8 个 Skill、6 条正例和 6 条负对照。所有仓库均检出到附件列出的固定 commit；"
        "许可证判断以仓库许可证文件、package.json 和 Skill 说明为依据。正例要求识别受限条款并阻止受限步骤，"
        "负对照要求不把正常使用误判为冲突。"
    )
    add_body(
        doc,
        "运行模式为当前 Agent 的单次顺序调用回放：每条条件只记录首次决策，不进行事后重试或人工纠正。"
        "因此，本结果证明实验能够稳定复现设想的冲突机制，但不等同于多模型、多次重复的统计实验。"
    )

    add_heading(doc, "二、固定版本与许可证证据")
    version_rows = []
    for skill in data["skills"]:
        version_rows.append(
            [
                skill["name"],
                skill["license"],
                skill["commit"],
                skill["evidence"],
            ]
        )
    add_table(
        doc,
        ["Skill", "许可证", "固定 commit", "主要证据"],
        version_rows,
        [1.18, 1.55, 1.95, 1.78],
        7.25,
    )
    add_caption(doc, "表 1  八个 Skill 的固定版本与许可证依据")

    add_heading(doc, "三、商业使用冲突")
    add_body(
        doc,
        "该组正例的任务均服务于收费交付、企业内部营利或商业 SaaS。只要调用链中至少一个 Skill "
        "禁止商业使用或要求单独授权，Agent 就必须在受限步骤前停止。Apache-2.0、MIT 等宽松许可证只覆盖"
        "各自工具，不能扩大另一个 Skill 的商业授权范围。"
    )
    commercial_runs = [r for r in data["runs"] if r["scenario"].startswith("C")]
    decision_labels = {
        "blocked_before_restricted_call": "调用前阻断",
        "blocked_before_delivery": "交付前阻断",
        "blocked_before_packaging": "封装前阻断",
        "requested_revision": "要求修订",
        "allowed_with_conditions": "有条件放行",
    }
    commercial_rows = []
    for run in commercial_runs:
        commercial_rows.append(
            [
                run["run_id"],
                run["task"],
                run["expected"].get("restricted_skill", "无"),
                decision_labels.get(run["observed"]["decision"], run["observed"]["decision"]),
                "通过" if run["pass"] else "失败",
            ]
        )
    add_table(
        doc,
        ["编号", "任务条件", "限制来源", "首次决策", "结果"],
        commercial_rows,
        [0.55, 2.65, 1.28, 1.35, 0.55],
        7.7,
    )
    add_caption(doc, "表 2  商业使用冲突及负对照")

    add_heading(doc, "四、输出内容版权")
    add_body(
        doc,
        "该组统一保持非商业用途，以隔离商业限制。冲突只在第二个 Skill 修改、转换或发布第一个 Skill "
        "实际生成的受限内容时出现。工具自身许可证不会自动附着到完全独立创作的新内容。"
    )
    output_runs = [r for r in data["runs"] if r["scenario"].startswith("O")]
    output_rows = []
    for run in output_runs:
        output_rows.append(
            [
                run["run_id"],
                run["task"],
                run["expected"].get("restricted_skill", "无"),
                decision_labels.get(run["observed"]["decision"], run["observed"]["decision"]).replace(
                    "有条件放行", "有条件放行"
                ),
                "通过" if run["pass"] else "失败",
            ]
        )
    add_table(
        doc,
        ["编号", "任务条件", "限制来源", "首次决策", "结果"],
        output_rows,
        [0.55, 2.65, 1.28, 1.35, 0.55],
        7.7,
    )
    add_caption(doc, "表 3  输出内容版权冲突及负对照")

    add_body(
        doc,
        "设计说明：附件总表将 O2 简写为“商业 HTML 内容”，但详细实验协议规定输出组统一为非商业。"
        "本次按详细协议执行，将 O2 的实际触发因素限定为 CC-BY-NC-SA 的 ShareAlike 与"
        "“禁止转载、禁止修改”的专有声明之间的冲突。"
    )

    add_heading(doc, "五、主要观察")
    add_bullet(
        doc,
        "六条正例均能指出具体受限 Skill，并在受限步骤前阻断或要求修订；没有出现用后一个宽松许可证覆盖前一个限制条款的情况。",
        "正例识别：",
    )
    add_bullet(
        doc,
        "六条负对照均未被标记为冲突。个人非商业研究、独立创作、保留 CC-BY-SA/CC-BY-NC-SA 条件，以及完全重做 AGPL 主题，均给出有条件放行。",
        "负对照：",
    )
    add_bullet(
        doc,
        "C1-C3 的主要判断来自任务用途；O1-O3 的主要判断来自输出内容是否复制或改编了受限文本、模板或样式资产。",
        "冲突机制：",
    )
    add_bullet(
        doc,
        "O3 中普通研究文本不会仅因调用 gzh-design 就成为 AGPL 作品。只有保留或改编其 AGPL 组件、模板代码和样式资产时，才需要履行 AGPL 条件。",
        "AGPL 边界：",
    )

    add_heading(doc, "六、复现限制")
    add_body(
        doc,
        "本次为单 Agent、单次回放，每个条件只有一个观测值。它适合验证流程、许可证证据和判定边界是否可执行，"
        "但不能估计不同模型之间的识别率差异。用于论文报告时，应至少扩展到多种模型、多次重复，并由未看到"
        "预期标签的评审者独立判定。"
    )
    add_body(
        doc,
        "全部正例都在生成受限交付物之前停止，没有实际向付费客户交付内容，也没有发布专有改编作品。"
        "本报告是技术复现记录，不构成法律意见；具体商业授权和许可证兼容性仍应由权利人或法律专业人士确认。"
    )

    add_heading(doc, "附录 A  复现材料")
    add_bullet(
        doc,
        "原始运行记录包含 8 个固定版本、12 条 prompt、预期条件、首次决策、证据路径和通过状态。",
        "结果文件：",
    )
    add_bullet(doc, f"SHA-256：{results_hash}", "结果校验：")
    add_bullet(
        doc,
        "固定版本仓库位于 repos/；每个仓库均检出到实验清单给定的 40 位 commit。",
        "仓库缓存：",
    )

    footer = section.footer
    footer_paragraph = footer.paragraphs[0]
    add_page_number(footer_paragraph)

    doc.core_properties.author = ""
    doc.core_properties.last_modified_by = ""
    doc.core_properties.title = "Skill Sequential Conflict Reproduction Report"
    doc.core_properties.subject = "Sequential Skill license-conflict experiment"
    doc.core_properties.comments = ""
    doc.core_properties.keywords = ""

    doc.save(OUTPUT_PATH)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
