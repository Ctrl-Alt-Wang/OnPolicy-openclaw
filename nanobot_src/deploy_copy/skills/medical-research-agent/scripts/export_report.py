#!/usr/bin/env python3
"""
Export a medical research markdown report to styled DOCX and/or PDF.

Examples:
    python export_report.py --input report.md --format all
    python export_report.py --input report.md --format docx
    python export_report.py --input report.md --format pdf
"""

from __future__ import annotations

import argparse
import datetime
import html
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


UPLOAD_BASE_URL = "https://share.yifuzhishi.com"


def upload_file(file_path: Path) -> str:
    """Upload a file to the share server and return the download URL."""
    url = f"{UPLOAD_BASE_URL}/{file_path.name}"
    try:
        subprocess.run(
            ["curl", "-T", str(file_path), url],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        detail = f"；stderr: {stderr}" if stderr else ""
        print(f"文件上传失败: {file_path.name}{detail}", file=sys.stderr)
        return ""
    download_url = url
    print(f"文件已上传，下载地址: {download_url}")
    return download_url


SECTION_MAP = {
    "一、": "一、",
    "二、": "二、",
    "三、": "三、",
    "四、": "四、",
    "五、": "五、",
    "六、": "六、",
    "七、": "七、",
    "八、": "八、",
    "九、": "九、",
}

CSS = """
:root {
  --ink: #1d2f45;
  --muted: #5f6f82;
  --brand: #27486d;
  --brand-deep: #234466;
  --line: #bed0e4;
  --line-soft: #dce7f3;
  --panel: #ffffff;
  --panel-alt: #edf3f9;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
  color: var(--ink);
  background: #ffffff;
}
.page {
  width: 1080px;
  margin: 0 auto;
  padding: 54px 84px 72px;
}
.cover-title {
  margin: 34px 0 18px;
  font-size: 38px;
  line-height: 1.35;
  font-weight: 800;
  color: var(--brand);
}
.cover-rule {
  height: 5px;
  width: 100%;
  background: var(--brand);
  margin: 0 0 28px;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  font-size: 19px;
  line-height: 1.9;
  margin-bottom: 26px;
}
.meta strong {
  color: var(--brand);
  font-weight: 800;
}
.separator {
  border-top: 2px solid var(--line-soft);
  margin: 28px 0 34px;
}
h1, h2, h3, h4 {
  margin: 0;
  color: var(--brand);
}
h1 {
  font-size: 31px;
  line-height: 1.35;
  margin-top: 28px;
  margin-bottom: 18px;
}
h2 {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 31px;
  line-height: 1.35;
  margin-top: 40px;
  margin-bottom: 18px;
  font-weight: 800;
}
h2::before {
  content: "";
  width: 7px;
  height: 54px;
  background: var(--brand);
  border-radius: 1px;
}
h3 {
  font-size: 24px;
  line-height: 1.45;
  margin-top: 22px;
  margin-bottom: 10px;
  color: #2f5d8a;
  font-weight: 800;
}
h4 {
  font-size: 20px;
  line-height: 1.45;
  margin-top: 14px;
  margin-bottom: 8px;
  font-weight: 700;
}
p, li, blockquote {
  font-size: 19px;
  line-height: 1.88;
}
p {
  margin: 0 0 16px;
}
strong {
  color: var(--brand);
}
blockquote {
  margin: 0 0 18px;
  padding: 18px 22px;
  background: #f5f8fc;
  border-left: 6px solid var(--brand);
}
ul, ol {
  margin: 6px 0 18px 24px;
  padding: 0;
}
li {
  margin-bottom: 8px;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 18px 0 28px;
  table-layout: fixed;
  background: var(--panel);
}
th, td {
  border: 2px solid var(--line);
  padding: 14px 16px;
  text-align: left;
  vertical-align: top;
  word-break: break-word;
  font-size: 18px;
  line-height: 1.8;
}
thead th {
  background: var(--brand-deep);
  color: #ffffff;
  font-weight: 800;
}
tbody tr:nth-child(even) td {
  background: var(--panel-alt);
}
table.gap-table th,
table.gap-table td {
  font-size: 16px;
  line-height: 1.75;
}
table.gap-table td:first-child,
table.gap-table th:first-child {
  width: 64px;
  text-align: center;
  font-weight: 800;
}
table.gap-table td:nth-child(2) { width: 150px; }
table.gap-table td:nth-child(3) { width: 210px; }
table.gap-table td:nth-child(4) { width: 170px; }
table.gap-table td:nth-child(5) { width: 210px; }
table.gap-table td:nth-child(6) { width: 140px; }
table.gap-table td:nth-child(7) { width: 150px; }
.section-break {
  border-top: 2px solid var(--line-soft);
  margin: 28px 0 34px;
}
.project-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 20px 0 12px;
  color: var(--brand);
  font-size: 23px;
  line-height: 1.5;
  font-weight: 800;
}
.project-title::before {
  content: "";
  width: 12px;
  height: 12px;
  border-radius: 3px;
  background: linear-gradient(135deg, #2f5d8a 0%, #234466 100%);
  box-shadow: 0 0 0 4px #e8f0f8;
}
.page-number {
  position: fixed;
  bottom: 10mm;
  left: 0;
  right: 0;
  text-align: center;
  color: #8b97a6;
  font-size: 12px;
}
@page {
  size: A4;
  margin: 14mm 10mm 18mm;
}
"""


def run(command: list[str]) -> None:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        detail = f"；stderr: {stderr}" if stderr else ""
        raise RuntimeError(f"命令执行失败: {' '.join(command)}{detail}") from exc
    else:
        _ = result  # 非致命 stderr（如 Chromium 的 dbus 告警）默认不向上抛出


def escape_inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_sep(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


def render_table(lines: list[str]) -> str:
    rows = [split_table_row(line) for line in lines if line.strip()]
    header = rows[0]
    body = rows[2:] if len(rows) > 1 and is_sep(lines[1]) else rows[1:]
    classes = []
    class_attr = f' class="{" ".join(classes)}"' if classes else ""
    thead = "".join(f"<th>{escape_inline(cell)}</th>" for cell in header)
    tbody = []
    for row in body:
        if len(row) < len(header):
            row += [""] * (len(header) - len(row))
        tbody.append("<tr>" + "".join(f"<td>{escape_inline(cell)}</td>" for cell in row[:len(header)]) + "</tr>")
    return f"<table{class_attr}><thead><tr>{thead}</tr></thead><tbody>{''.join(tbody)}</tbody></table>"


def extract_title(lines: list[str], fallback: str) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("标题："):
            return stripped.split("标题：", 1)[1].strip() or fallback
        if stripped.startswith("标题:"):
            return stripped.split("标题:", 1)[1].strip() or fallback
    for line in lines:
        if line.startswith("# "):
            candidate = line[2:].strip()
            if candidate and candidate not in {"核心洞察速览", "引言与分析范围", "背景和意义"}:
                return candidate
    return fallback


def extract_meta(title: str) -> str:
    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(beijing_tz)
    time_window = f"{now.year-4}-{now.year}年"
    date_text = f"{now.year}年{now.month}月{now.day}日"
    return (
        '<div class="meta">'
        f'<div><strong>调研主题：</strong>{html.escape(title)}</div>'
        f'<div><strong>时间窗口：</strong>{time_window}</div>'
        '<div><strong>检索数据库：</strong>InfoX-Med 医学文献库</div>'
        f'<div><strong>报告日期：</strong>{date_text}</div>'
        "</div>"
    )


def render_markdown(text: str, title: str) -> str:
    lines = text.splitlines()
    blocks: list[str] = []
    i = 0
    inserted_cover = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if not inserted_cover:
            blocks.append(f'<div class="cover-title">{html.escape(title)}</div>')
            blocks.append('<div class="cover-rule"></div>')
            blocks.append(extract_meta(title))
            blocks.append('<div class="separator"></div>')
            inserted_cover = True
        if stripped == "---":
            blocks.append('<div class="section-break"></div>')
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            table_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            blocks.append(render_table(table_lines))
            continue
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            content = stripped[level:].strip()
            content_html = escape_inline(content)
            if level == 1:
                for prefix in SECTION_MAP:
                    if content.startswith(prefix):
                        blocks.append(f"<h2>{content_html}</h2>")
                        break
                else:
                    blocks.append(f"<h1>{content_html}</h1>")
            elif level == 2:
                blocks.append(f"<h3>{content_html}</h3>")
            else:
                blocks.append(f"<h4>{content_html}</h4>")
            i += 1
            continue
        if stripped.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip()[1:].strip())
                i += 1
            blocks.append("<blockquote>" + "<br>".join(escape_inline(q) for q in quote_lines) + "</blockquote>")
            continue
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            blocks.append("<ul>" + "".join(f"<li>{escape_inline(item)}</li>" for item in items) + "</ul>")
            continue
        if stripped.startswith("```"):
            code_lines = []
            lang = stripped[3:].strip()
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines) and lines[i].strip().startswith("```"):
                i += 1
            code_content = "\n".join(code_lines)
            if lang == "mermaid":
                blocks.append(f'<div class="mermaid" style="display:flex;justify-content:center;margin:20px 0;">{html.escape(code_content)}</div>')
            else:
                blocks.append(f'<pre style="background:#f5f8fc;padding:12px;border-radius:4px;overflow-x:auto;"><code>{html.escape(code_content)}</code></pre>')
            continue
        if re.fullmatch(r"\*\*课题\s*\d+[:：].+?\*\*", stripped):
            blocks.append(f'<div class="project-title">{escape_inline(stripped[2:-2])}</div>')
            i += 1
            continue
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            blocks.append("<ol>" + "".join(f"<li>{escape_inline(item)}</li>" for item in items) + "</ol>")
            continue
        paragraph = [stripped]
        i += 1
        while i < len(lines):
            peek = lines[i].strip()
            if not peek:
                i += 1
                break
            if peek == "---" or peek.startswith("#") or peek.startswith(">") or peek.startswith("|") or peek.startswith("```"):
                break
            if re.match(r"^[-*]\s+", peek) or re.match(r"^\d+\.\s+", peek):
                break
            paragraph.append(peek)
            i += 1
        blocks.append(f"<p>{escape_inline(' '.join(paragraph))}</p>")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>{CSS}</style>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
    mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
  </script>
</head>
<body>
  <main class="page">
    {''.join(blocks)}
  </main>
  <div class="page-number"></div>
</body>
</html>
"""


def find_browser() -> Path | None:
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None


def browser_extra_args() -> list[str]:
    args: list[str] = ["--no-sandbox", "--disable-dev-shm-usage"]
    return args


def split_inline_runs(text: str) -> list[tuple[str, dict[str, bool]]]:
    parts: list[tuple[str, dict[str, bool]]] = []
    pattern = re.compile(r"(\*\*.*?\*\*|`.*?`)")
    pos = 0
    for match in pattern.finditer(text):
        if match.start() > pos:
            parts.append((text[pos:match.start()], {}))
        token = match.group(0)
        if token.startswith("**") and token.endswith("**"):
            parts.append((token[2:-2], {"bold": True}))
        elif token.startswith("`") and token.endswith("`"):
            parts.append((token[1:-1], {"code": True}))
        pos = match.end()
    if pos < len(text):
        parts.append((text[pos:], {}))
    return [(segment, style) for segment, style in parts if segment]


def render_docx_runs(text: str) -> str:
    runs = []
    for segment, style in split_inline_runs(text):
        props = []
        if style.get("bold"):
            props.append("<w:b/>")
        if style.get("code"):
            props.append("<w:rFonts w:ascii=\"Consolas\" w:hAnsi=\"Consolas\" w:eastAsia=\"Consolas\"/>")
            props.append("<w:shd w:val=\"clear\" w:fill=\"EDF3FA\"/>")
        rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
        space = ' xml:space="preserve"' if segment[:1].isspace() or segment[-1:].isspace() else ""
        runs.append(f"<w:r>{rpr}<w:t{space}>{xml_escape(segment)}</w:t></w:r>")
    return "".join(runs) or "<w:r><w:t></w:t></w:r>"


def paragraph_xml(text: str, style: str | None = None) -> str:
    ppr = f"<w:pPr><w:pStyle w:val=\"{style}\"/></w:pPr>" if style else ""
    return f"<w:p>{ppr}{render_docx_runs(text)}</w:p>"


def list_item_xml(text: str, ordered: bool) -> str:
    num_id = "2" if ordered else "1"
    ppr = (
        "<w:pPr>"
        f"<w:numPr><w:ilvl w:val=\"0\"/><w:numId w:val=\"{num_id}\"/></w:numPr>"
        "</w:pPr>"
    )
    return f"<w:p>{ppr}{render_docx_runs(text)}</w:p>"


def table_xml(lines: list[str]) -> str:
    rows = [split_table_row(line) for line in lines if line.strip()]
    header = rows[0]
    body = rows[2:] if len(rows) > 1 and is_sep(lines[1]) else rows[1:]
    all_rows = [header] + body
    cols = len(header)
    cell_width = int(9000 / max(cols, 1))
    tr_list = []
    for row_index, row in enumerate(all_rows):
        cells = []
        for cell in row[:cols]:
            shading = ""
            if row_index == 0:
                shading = '<w:shd w:val="clear" w:fill="234466"/>'
                text_xml = (
                    f"<w:p><w:pPr><w:jc w:val=\"left\"/></w:pPr>"
                    f"<w:r><w:rPr><w:b/><w:color w:val=\"FFFFFF\"/></w:rPr><w:t>{xml_escape(cell)}</w:t></w:r></w:p>"
                )
            else:
                text_xml = paragraph_xml(cell)
            cells.append(
                "<w:tc>"
                f"<w:tcPr><w:tcW w:w=\"{cell_width}\" w:type=\"dxa\"/>{shading}"
                "<w:tcBorders>"
                "<w:top w:val=\"single\" w:sz=\"8\" w:color=\"BED0E4\"/>"
                "<w:left w:val=\"single\" w:sz=\"8\" w:color=\"BED0E4\"/>"
                "<w:bottom w:val=\"single\" w:sz=\"8\" w:color=\"BED0E4\"/>"
                "<w:right w:val=\"single\" w:sz=\"8\" w:color=\"BED0E4\"/>"
                "</w:tcBorders></w:tcPr>"
                f"{text_xml}</w:tc>"
            )
        tr_list.append("<w:tr>" + "".join(cells) + "</w:tr>")
    return (
        "<w:tbl>"
        "<w:tblPr>"
        "<w:tblW w:w=\"9000\" w:type=\"dxa\"/>"
        "<w:tblBorders>"
        "<w:top w:val=\"single\" w:sz=\"8\" w:color=\"BED0E4\"/>"
        "<w:left w:val=\"single\" w:sz=\"8\" w:color=\"BED0E4\"/>"
        "<w:bottom w:val=\"single\" w:sz=\"8\" w:color=\"BED0E4\"/>"
        "<w:right w:val=\"single\" w:sz=\"8\" w:color=\"BED0E4\"/>"
        "<w:insideH w:val=\"single\" w:sz=\"8\" w:color=\"BED0E4\"/>"
        "<w:insideV w:val=\"single\" w:sz=\"8\" w:color=\"BED0E4\"/>"
        "</w:tblBorders>"
        "</w:tblPr>"
        "<w:tblGrid>" + "".join(f"<w:gridCol w:w=\"{cell_width}\"/>" for _ in range(cols)) + "</w:tblGrid>"
        + "".join(tr_list) +
        "</w:tbl>"
    )


def markdown_to_docx_body(text: str) -> str:
    lines = text.splitlines()
    body: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if stripped == "---":
            body.append(paragraph_xml(""))
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            table_lines = [lines[i]]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            body.append(table_xml(table_lines))
            body.append(paragraph_xml(""))
            continue
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text_value = stripped[level:].strip()
            style = "Heading1" if level == 1 else "Heading2" if level == 2 else "Heading3"
            body.append(paragraph_xml(text_value, style))
            i += 1
            continue
        if stripped.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip()[1:].strip())
                i += 1
            body.append(paragraph_xml(" ".join(quote_lines), "Quote"))
            continue
        if re.match(r"^[-*]\s+", stripped):
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                body.append(list_item_xml(re.sub(r"^[-*]\s+", "", lines[i].strip()), ordered=False))
                i += 1
            continue
        if re.fullmatch(r"\*\*课题\s*\d+[:：].+?\*\*", stripped):
            body.append(paragraph_xml(stripped[2:-2], "Heading3"))
            i += 1
            continue
        if re.match(r"^\d+\.\s+", stripped):
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                body.append(list_item_xml(re.sub(r"^\d+\.\s+", "", lines[i].strip()), ordered=True))
                i += 1
            continue
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines) and lines[i].strip().startswith("```"):
                i += 1
            code_content = "\n".join(code_lines)
            body.append(paragraph_xml(code_content, "Quote"))
            continue
        paragraph = [stripped]
        i += 1
        while i < len(lines):
            peek = lines[i].strip()
            if not peek:
                i += 1
                break
            if peek == "---" or peek.startswith("#") or peek.startswith(">") or peek.startswith("|") or peek.startswith("```"):
                break
            if re.match(r"^[-*]\s+", peek) or re.match(r"^\d+\.\s+", peek):
                break
            paragraph.append(peek)
            i += 1
        body.append(paragraph_xml(" ".join(paragraph)))
    return "".join(body)


def fallback_docx_styles() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:hAnsi="Microsoft YaHei" w:eastAsia="Microsoft YaHei"/><w:sz w:val="24"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="360" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:color w:val="27486D"/><w:sz w:val="36"/></w:rPr><w:pPr><w:spacing w:before="320" w:after="220"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="Heading 2"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:color w:val="27486D"/><w:sz w:val="32"/></w:rPr><w:pPr><w:spacing w:before="240" w:after="160"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="Heading 3"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:color w:val="2F5D8A"/><w:sz w:val="28"/></w:rPr><w:pPr><w:spacing w:before="180" w:after="120"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="420"/><w:spacing w:after="180"/></w:pPr><w:rPr><w:color w:val="3C4F65"/></w:rPr></w:style>
</w:styles>"""


def create_fallback_docx(input_path: Path, docx_path: Path) -> Path:
    text = input_path.read_text(encoding="utf-8")
    body_xml = markdown_to_docx_body(text)
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>
    {body_xml}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1134" w:bottom="1440" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""
    package_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""
    document_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""
    core_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Medical Research Report</dc:title>
  <dc:creator>Codex</dc:creator>
</cp:coreProperties>"""
    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
</Properties>"""
    try:
        with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", package_rels)
            zf.writestr("docProps/core.xml", core_xml)
            zf.writestr("docProps/app.xml", app_xml)
            zf.writestr("word/document.xml", document_xml)
            zf.writestr("word/styles.xml", fallback_docx_styles())
            zf.writestr("word/_rels/document.xml.rels", document_rels)
    except OSError as exc:
        raise RuntimeError(f"Word 兜底导出失败，目标目录不可写: {docx_path}") from exc
    return docx_path


def export_docx(input_path: Path, output_dir: Path) -> Path:
    pandoc = shutil.which("pandoc")
    docx_path = output_dir / f"{input_path.stem}.docx"
    if not pandoc:
        create_fallback_docx(input_path, docx_path)
        upload_file(docx_path)
        return docx_path
    try:
        run([pandoc, str(input_path), "-f", "markdown", "-t", "docx", "-o", str(docx_path)])
    except RuntimeError as exc:
        try:
            create_fallback_docx(input_path, docx_path)
        except RuntimeError as fallback_exc:
            raise RuntimeError(
                f"Word 导出失败，pandoc 转换失败且兜底导出也失败: {docx_path}; {fallback_exc}"
            ) from exc
    upload_file(docx_path)
    return docx_path


def export_html(input_path: Path, output_dir: Path) -> Path:
    html_path = output_dir / f"{input_path.stem}.html"
    text = input_path.read_text(encoding="utf-8")
    title = extract_title(text.splitlines(), input_path.stem)
    html_text = render_markdown(text, title)
    try:
        html_path.write_text(html_text, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"HTML 导出失败，目标目录不可写: {html_path}") from exc
    return html_path


def export_pdf_via_weasyprint(html_path: Path, pdf_path: Path) -> Path:
    """Export PDF using weasyprint as a fallback when chromium is unavailable."""
    try:
        from weasyprint import HTML as WeasyHTML
    except ImportError as exc:
        raise RuntimeError("weasyprint 未安装，无法作为 PDF 导出备选方案。") from exc
    try:
        WeasyHTML(filename=str(html_path)).write_pdf(str(pdf_path))
    except Exception as exc:
        raise RuntimeError(f"weasyprint PDF 导出失败: {pdf_path}; {exc}") from exc
    return pdf_path


def export_pdf_from_html(html_path: Path, output_dir: Path) -> Path:
    pdf_path = output_dir / f"{html_path.stem}.pdf"
    browser = find_browser()
    if browser:
        try:
            run(
                [
                    str(browser),
                    "--headless=new",
                    "--disable-gpu",
                    *browser_extra_args(),
                    "--allow-file-access-from-files",
                    "--export-tagged-pdf",
                    "--generate-pdf-document-outline",
                    "--no-pdf-header-footer",
                    "--print-to-pdf-no-header",
                    f"--print-to-pdf={pdf_path}",
                    str(html_path.resolve().as_uri()),
                ]
            )
            upload_file(pdf_path)
            return pdf_path
        except RuntimeError:
            print("chromium PDF 导出失败，尝试 weasyprint 备选方案...", file=sys.stderr)
    else:
        print("未找到可用浏览器，尝试 weasyprint 备选方案...", file=sys.stderr)
    export_pdf_via_weasyprint(html_path, pdf_path)
    upload_file(pdf_path)
    return pdf_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export medical research report files.")
    parser.add_argument("--input", required=True, help="Markdown input path.")
    parser.add_argument("--format", choices=["docx", "pdf", "all"], default="all")
    parser.add_argument("--output-dir", help="Output directory. Defaults to the input markdown directory.")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    output_dir = Path(args.output_dir).resolve() if args.output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []
    errors: list[str] = []

    if args.format in {"docx", "all"}:
        try:
            generated.append(export_docx(input_path, output_dir))
        except Exception as exc:
            errors.append(f"DOCX: {exc}")

    if args.format in {"pdf", "all"}:
        try:
            html_path = export_html(input_path, output_dir)
            generated.append(html_path)
            generated.append(export_pdf_from_html(html_path, output_dir))
        except Exception as exc:
            errors.append(f"PDF: {exc}")

    for item in generated:
        print(item)

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        if generated:
            return 2
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
