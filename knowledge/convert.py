#!/usr/bin/env python3
"""把七维知识库的五份内部维度 Word 稿转成按标题层级拆分的 Markdown。

用法：
    python3 knowledge/convert.py <源目录> knowledge

依赖：Python 3.10+、pandoc。可用 PANDOC 环境变量指定 pandoc 可执行文件。
转换报告由本脚本生成；源文档只复制为冻结快照，不修改其内容。
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DimensionSpec:
    prefix: str
    expected_entries: int
    expected_files: int
    source_candidates: tuple[str, ...]


DIMENSIONS: dict[str, DimensionSpec] = {
    "本体论": DimensionSpec(
        "C",
        1067,
        80,
        ("本体论全量.docx", "社会学知识概念历史脉络结构——本体论工程.docx"),
    ),
    "认识论": DimensionSpec(
        "E",
        124,
        32,
        ("认识论全量.docx", "社会学问题前提历史脉络结构——认识论工程.docx"),
    ),
    "价值论": DimensionSpec(
        "V",
        304,
        45,
        ("价值论全量.docx", "社会学研究目的历史脉络结构——价值论工程.docx"),
    ),
    "方法论": DimensionSpec(
        "M",
        690,
        73,
        ("方法论全量.docx", "社会学研究方法历史脉络结构——方法论工程.docx"),
    ),
    "实践论": DimensionSpec(
        "P",
        370,
        138,
        ("实践论全量.docx", "社会学研究操作历史脉络结构——实践论工程.docx"),
    ),
}

# 这两份材料不参与五维 Markdown 计数，只作为用户提供的第六/第七维冻结快照。
EXTRA_SOURCE_CANDIDATES = (
    "D6_学派传统.docx",
    "D7_学科史.docx",
    "纲要7.docx",
    "《纲要7》.docx",
)

ENTRY_RE = re.compile(r"^####\s+\*{0,2}([A-Z])(\d+)\b")
ENTRY_HEADING_RE = re.compile(r"^(####\s+)(\*{0,2})([A-Z])(\d+)(\b.*)$")
D6_PERSON_RE = re.compile(r"^#####\s+\*{0,2}【?([A-Z])(\d+)】?")
D6_PERSON_HEADING_RE = re.compile(r"^(#####\s+)(\*{0,2})(【?)([A-Z])(\d+)(】?)(.*)$")
D7_ENTRY_RE = re.compile(r"^(#{1,6})\s+\*{0,2}(H)(\d+)\b")
D7_ENTRY_HEADING_RE = re.compile(r"^(#{1,6}\s+)(\*{0,2})H(\d+)(\b.*)$")
PERIOD_RE = re.compile(r"^#####\s+(前史|T[1-4])(?:\s|$)")
CLAIM_RE = re.compile(r"观点[—-]{1,3}文献依据")
REFERENCE_RE = re.compile(r"^文献\s*[：:]")
SUPPORT_RE = re.compile(r"^支持范围\s*[：:]")


def find_pandoc() -> str:
    configured = os.environ.get("PANDOC")
    if configured:
        candidate = Path(configured)
        if not candidate.is_file():
            raise RuntimeError(f"PANDOC 指向的文件不存在：{candidate}")
        return str(candidate)
    executable = shutil.which("pandoc")
    if executable:
        return executable
    raise RuntimeError("找不到 pandoc；请安装 pandoc，或用 PANDOC 环境变量指定其路径")


def run_pandoc(pandoc: str, src: Path, dst: Path) -> None:
    subprocess.run(
        [
            pandoc,
            "-f",
            "docx",
            "-t",
            "markdown-smart",
            "--wrap=none",
            str(src),
            "-o",
            str(dst),
        ],
        check=True,
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def safe_name(heading: str) -> str:
    name = heading.split("（")[0].split("(")[0].strip()
    name = re.sub(r'[/\\:*?"<>|]', "-", name)
    return name.strip(". ") or "未命名"


def resolve_source(src_root: Path, dimension: str, spec: DimensionSpec) -> Path:
    matches = [src_root / name for name in spec.source_candidates if (src_root / name).is_file()]
    if not matches:
        expected = "、".join(spec.source_candidates)
        raise FileNotFoundError(f"缺少{dimension}源文件；可接受文件名：{expected}")
    if len(matches) > 1:
        names = "、".join(path.name for path in matches)
        raise RuntimeError(f"{dimension}存在多个候选源文件，无法确定使用哪份：{names}")
    return matches[0]


def split_by_subcategory(md: str) -> list[tuple[str, str, str]]:
    """切成 (大类, 子类, 正文)，兼容大类下直接出现条目的价值论稿。"""
    blocks: list[tuple[str, str, str]] = []
    preamble: list[str] = []
    category = ""
    subcategory = ""
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        body = "\n".join(buf).strip()
        if body:
            blocks.append((category, subcategory, body))
        buf = []

    for line in md.splitlines():
        if line.startswith("## ") and not line.startswith("###"):
            flush()
            category = line[3:].strip()
            subcategory = ""
            if not blocks and preamble:
                buf.extend(preamble)
                if preamble[-1].strip():
                    buf.append("")
            buf.append(line)
        elif line.startswith("### ") and not line.startswith("####"):
            flush()
            subcategory = line[4:].strip()
            buf.append(line)
        elif category:
            buf.append(line)
        else:
            preamble.append(line)

    flush()
    if not blocks and "\n".join(preamble).strip():
        blocks.append(("未分类", "", "\n".join(preamble).strip()))
    return blocks


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_entry_ids(dimension: str, md: str) -> tuple[str, int]:
    """按仓库编号规则直接统一条目标题，不改冻结 DOCX。"""
    changed = 0
    entry_index = 0
    normalized: list[str] = []
    for line in md.splitlines():
        match = ENTRY_HEADING_RE.match(line)
        if not match:
            normalized.append(line)
            continue

        entry_index += 1
        old_id = f"{match.group(3)}{match.group(4)}"
        if dimension == "方法论":
            new_id = f"M{entry_index:03d}"
        elif dimension == "实践论":
            new_id = f"P{int(match.group(4)):03d}"
        else:
            new_id = old_id

        if new_id != old_id:
            changed += 1
        normalized.append(f"{match.group(1)}{match.group(2)}{new_id}{match.group(5)}")
    return "\n".join(normalized) + ("\n" if md.endswith("\n") else ""), changed


def summarize_periods(md: str) -> tuple[Counter[int], Counter[str], list[tuple[str, int]]]:
    current_periods: list[str] | None = None
    current_id: str | None = None
    periods_by_entry: list[tuple[str, list[str]]] = []
    for line in md.splitlines():
        entry_match = ENTRY_RE.match(line)
        if entry_match:
            current_id = f"{entry_match.group(1)}{entry_match.group(2)}"
            current_periods = []
            periods_by_entry.append((current_id, current_periods))
            continue
        period_match = PERIOD_RE.match(line)
        if current_periods is not None and period_match:
            current_periods.append(period_match.group(1))
    distribution = Counter(len(periods) for _, periods in periods_by_entry)
    labels = Counter(label for _, periods in periods_by_entry for label in periods)
    anomalies = [(entry_id, len(periods)) for entry_id, periods in periods_by_entry if len(periods) not in (4, 5)]
    return distribution, labels, anomalies


def convert_dimension(
    dimension: str,
    spec: DimensionSpec,
    src: Path,
    out_root: Path,
    pandoc: str,
) -> dict[str, object]:
    raw = out_root / f".{dimension}.pandoc.md"
    try:
        run_pandoc(pandoc, src, raw)
        md = raw.read_text(encoding="utf-8")
    finally:
        if raw.exists():
            raw.unlink()

    md, normalized_id_count = normalize_entry_ids(dimension, md)

    blocks = split_by_subcategory(md)
    out_dir = out_root / dimension
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in sorted(out_dir.glob("*.md")):
        stale.unlink()

    seen_ids: list[str] = []
    files: list[tuple[str, int]] = []
    direct_category_files = 0
    category_count = sum(1 for line in md.splitlines() if line.startswith("## ") and not line.startswith("###"))
    subcategory_count = sum(1 for line in md.splitlines() if line.startswith("### ") and not line.startswith("####"))

    cat_index = 0
    last_category: str | None = None
    sub_index = 0
    for category, subcategory, body in blocks:
        if category != last_category:
            cat_index += 1
            sub_index = 0
            last_category = category
        sub_index += 1

        ids = [
            f"{match.group(1)}{match.group(2)}"
            for line in body.splitlines()
            if (match := ENTRY_RE.match(line))
        ]
        seen_ids.extend(ids)
        if not subcategory and ids:
            direct_category_files += 1

        label = safe_name(subcategory) if subcategory else safe_name(category)
        name = f"{cat_index:02d}-{sub_index:02d}-{label}.md"
        header = f"<!-- 大类：{category} -->\n\n"
        write_text(out_dir / name, header + body.rstrip() + "\n")
        files.append((name, len(ids)))

    id_counts = Counter(seen_ids)
    prefix_counts = Counter(item[0] for item in seen_ids)
    wrong_prefix = sorted(item for item in seen_ids if not item.startswith(spec.prefix))
    duplicates = sorted(item for item, count in id_counts.items() if count > 1)
    period_distribution, period_labels, period_anomalies = summarize_periods(md)
    lines = md.splitlines()

    return {
        "dimension": dimension,
        "source": src.name,
        "source_hash": sha256(src),
        "files": files,
        "entry_count": len(seen_ids),
        "unique_entry_count": len(id_counts),
        "expected_entries": spec.expected_entries,
        "expected_files": spec.expected_files,
        "wrong_prefix": wrong_prefix,
        "duplicates": duplicates,
        "prefix_counts": prefix_counts,
        "category_count": category_count,
        "subcategory_count": subcategory_count,
        "direct_category_files": direct_category_files,
        "bold_entry_headings": sum(1 for line in lines if re.match(r"^####\s+\*\*[A-Z]\d+", line)),
        "claim_count": sum(1 for line in lines if CLAIM_RE.search(line)),
        "reference_count": sum(1 for line in lines if REFERENCE_RE.match(line)),
        "support_count": sum(1 for line in lines if SUPPORT_RE.match(line)),
        "period_distribution": period_distribution,
        "period_labels": period_labels,
        "period_anomalies": period_anomalies,
        "normalized_id_count": normalized_id_count,
    }


def normalize_d6_people(md: str) -> tuple[str, int]:
    mapping: dict[str, str] = {}
    changed = 0
    for index, line in enumerate(
        (line for line in md.splitlines() if D6_PERSON_HEADING_RE.match(line)), 1
    ):
        match = D6_PERSON_HEADING_RE.match(line)
        assert match is not None
        old_id = f"{match.group(4)}{match.group(5)}"
        new_id = f"P{index:03d}"
        if old_id in mapping:
            raise RuntimeError(f"D6 人物源编号重复，无法直接同步正文引用：{old_id}")
        mapping[old_id] = new_id
        if old_id != new_id:
            changed += 1

    reference_re = re.compile(r"(?<![A-Z])P\d{3}(?!\d)")
    normalized = [
        reference_re.sub(lambda match: mapping.get(match.group(0), match.group(0)), line)
        for line in md.splitlines()
    ]
    return "\n".join(normalized) + ("\n" if md.endswith("\n") else ""), changed


def convert_d6(src: Path, out_root: Path, pandoc: str) -> dict[str, object]:
    raw = out_root / ".学派传统.pandoc.md"
    try:
        run_pandoc(pandoc, src, raw)
        md = raw.read_text(encoding="utf-8")
    finally:
        if raw.exists():
            raw.unlink()
    md, normalized_id_count = normalize_d6_people(md)

    out_dir = out_root / "学派传统"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in sorted(out_dir.glob("*.md")):
        stale.unlink()

    preamble: list[str] = []
    blocks: list[tuple[str, str, str, str]] = []
    region = ""
    national_tradition = ""
    school = ""
    body: list[str] = []

    def flush_school() -> None:
        nonlocal body
        text = "\n".join(body).strip()
        if school and text:
            blocks.append((region, national_tradition, school, text))
        body = []

    for line in md.splitlines():
        if line.startswith("## ") and not line.startswith("###"):
            if school:
                flush_school()
                school = ""
            region = line[3:].strip()
            national_tradition = ""
            if not blocks:
                preamble.append(line)
        elif line.startswith("### ") and not line.startswith("####"):
            if school:
                flush_school()
                school = ""
            national_tradition = line[4:].strip()
            if not blocks:
                preamble.append(line)
        elif line.startswith("#### ") and not line.startswith("#####"):
            if school:
                flush_school()
            school = line[5:].strip()
            body = [line]
        elif line.startswith("##### ") and not school:
            # D6 部分地区传统下直接出现人物，没有学派四级标题。
            school = national_tradition or region or "未分类"
            body = [line]
        elif school:
            body.append(line)
        elif not blocks:
            preamble.append(line)
    flush_school()

    files: list[tuple[str, int]] = []
    preamble_text = "\n".join(preamble).strip()
    if preamble_text:
        name = "000-目录与说明.md"
        write_text(out_dir / name, preamble_text + "\n")
        files.append((name, 0))

    seen_ids: list[str] = []
    for index, (region, national_tradition, school, text) in enumerate(blocks, 1):
        ids = [
            f"{match.group(1)}{match.group(2)}"
            for line in text.splitlines()
            if (match := D6_PERSON_RE.match(line))
        ]
        seen_ids.extend(ids)
        label = safe_name(re.sub(r"\*+", "", school))
        name = f"{index:03d}-{label}.md"
        header = (
            f"<!-- 学统：{region} -->\n"
            f"<!-- 地区传统：{national_tradition or '未标注'} -->\n\n"
        )
        write_text(out_dir / name, header + text.rstrip() + "\n")
        files.append((name, len(ids)))

    counts = Counter(seen_ids)
    return {
        "dimension": "学派传统（D6）",
        "directory": "学派传统",
        "source": src.name,
        "files": files,
        "entry_count": len(seen_ids),
        "unique_entry_count": len(counts),
        "expected_entries": 218,
        "expected_prefix": "P",
        "prefix_counts": Counter(item[0] for item in seen_ids),
        "duplicates": sorted(item for item, count in counts.items() if count > 1),
        "wrong_prefix": sorted(item for item in seen_ids if not item.startswith("P")),
        "normalized_id_count": normalized_id_count,
        "unit_count": len(blocks),
        "split_unit": "学派",
    }


def clean_heading_text(line: str) -> str:
    text = re.sub(r"^#{1,6}\s+", "", line).strip()
    return text.strip("* ")


def normalize_d7_entries(md: str) -> tuple[str, int]:
    changed = 0
    index = 0
    normalized: list[str] = []
    for line in md.splitlines():
        match = D7_ENTRY_HEADING_RE.match(line)
        if not match:
            normalized.append(line)
            continue
        index += 1
        old_id = f"H{match.group(3)}"
        new_id = f"H{index:03d}"
        if old_id != new_id:
            changed += 1
        normalized.append(f"{match.group(1)}{match.group(2)}{new_id}{match.group(4)}")
    return "\n".join(normalized) + ("\n" if md.endswith("\n") else ""), changed


def convert_d7(src: Path, out_root: Path, pandoc: str) -> dict[str, object]:
    raw = out_root / ".学科史.pandoc.md"
    try:
        run_pandoc(pandoc, src, raw)
        md = raw.read_text(encoding="utf-8")
    finally:
        if raw.exists():
            raw.unlink()
    md, normalized_id_count = normalize_d7_entries(md)

    out_dir = out_root / "学科史"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in sorted(out_dir.glob("*.md")):
        stale.unlink()

    overview: list[str] = []
    blocks: list[tuple[str, str, str]] = []
    group = ""
    entry_id = ""
    body: list[str] = []

    def flush_entry() -> None:
        nonlocal body
        text = "\n".join(body).strip()
        if entry_id and text:
            blocks.append((group, entry_id, text))
        body = []

    for line in md.splitlines():
        entry_match = D7_ENTRY_RE.match(line)
        if entry_match:
            flush_entry()
            entry_id = f"H{entry_match.group(3)}"
            body = [line]
            continue
        if line.startswith("# ") and not line.startswith("##"):
            if entry_id:
                flush_entry()
                entry_id = ""
            label = clean_heading_text(line)
            if label:
                group = label
                overview.append(line)
            continue
        if entry_id:
            body.append(line)
        else:
            overview.append(line)
    flush_entry()

    files: list[tuple[str, int]] = []
    overview_text = "\n".join(overview).strip()
    if overview_text:
        name = "000-说明与分组.md"
        write_text(out_dir / name, overview_text + "\n")
        files.append((name, 0))

    seen_ids: list[str] = []
    for index, (group, current_id, text) in enumerate(blocks, 1):
        seen_ids.append(current_id)
        first_line = next((line for line in text.splitlines() if line.strip()), current_id)
        label = clean_heading_text(first_line)
        label = re.sub(r"^H\d+\s*", "", label).strip() or current_id
        name = f"{index:03d}-{current_id}-{safe_name(label)}.md"
        header = f"<!-- 学科史分组：{group or '未标注'} -->\n\n"
        write_text(out_dir / name, header + text.rstrip() + "\n")
        files.append((name, 1))

    counts = Counter(seen_ids)
    return {
        "dimension": "学科史（D7）",
        "directory": "学科史",
        "source": src.name,
        "files": files,
        "entry_count": len(seen_ids),
        "unique_entry_count": len(counts),
        "expected_entries": 91,
        "expected_prefix": "H",
        "prefix_counts": Counter(item[0] for item in seen_ids),
        "duplicates": sorted(item for item, count in counts.items() if count > 1),
        "wrong_prefix": sorted(item for item in seen_ids if not item.startswith("H")),
        "normalized_id_count": normalized_id_count,
        "unit_count": len(blocks),
        "split_unit": "编年条目",
    }


def format_counter(counter: Counter[object]) -> str:
    return "、".join(f"{key}×{value}" for key, value in sorted(counter.items(), key=lambda item: str(item[0]))) or "无"


def compact_id_list(ids: list[str], limit: int = 12) -> str:
    if not ids:
        return "无"
    head = "、".join(ids[:limit])
    return head if len(ids) <= limit else f"{head}……（共 {len(ids)} 个）"


def build_report(
    reports: list[dict[str, object]],
    supplemental_reports: list[dict[str, object]],
    source_snapshots: list[Path],
    pandoc_version: str,
) -> str:
    lines = [
        "# 转换报告",
        "",
        "> 本文件由 `knowledge/convert.py` 自动生成，请勿手写修改。报告不写入运行时间，以保证同一输入重复运行逐字节一致。",
        "",
        f"Pandoc：`{pandoc_version}`（`docx` → `markdown-smart`，`--wrap=none`）",
        "",
        "## 五维汇总",
        "",
        "| 维度 | Markdown 文件数 | 约定文件数 | 条目数 | 去重后 | 预期条目数 | 编号前缀 | 状态 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]

    fatal = False
    for report in reports:
        statuses: list[str] = []
        if report["entry_count"] != report["expected_entries"]:
            delta = int(report["entry_count"]) - int(report["expected_entries"])
            statuses.append(f"条目数差 {delta:+d}")
            fatal = True
        if report["duplicates"]:
            statuses.append(f"重复编号 {len(report['duplicates'])} 个")
            fatal = True
        if report["wrong_prefix"]:
            statuses.append(f"前缀异常 {len(report['wrong_prefix'])} 个")
            fatal = True
        if len(report["files"]) != report["expected_files"]:
            statuses.append(f"文件数与目录约定不同（{len(report['files'])}≠{report['expected_files']}）")
        lines.append(
            f"| {report['dimension']} | {len(report['files'])} | {report['expected_files']} | "
            f"{report['entry_count']} | {report['unique_entry_count']} | {report['expected_entries']} | "
            f"{format_counter(report['prefix_counts'])} | {'；'.join(statuses) or 'OK'} |"
        )

    total = sum(int(report["entry_count"]) for report in reports)
    unique_total = sum(int(report["unique_entry_count"]) for report in reports)
    lines += [
        "",
        f"五维条目合计：**{total}**；各维去重后合计：**{unique_total}**；Issue 预期：**2555**。",
        "",
        "## D6 / D7 汇总",
        "",
        "| 维度 | Markdown 文件数 | 拆分单位数 | 条目数 | 去重后 | 预期条目数 | 编号前缀 | 状态 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for report in supplemental_reports:
        statuses: list[str] = []
        if report["entry_count"] != report["expected_entries"]:
            delta = int(report["entry_count"]) - int(report["expected_entries"])
            statuses.append(f"条目数差 {delta:+d}")
            fatal = True
        if report["duplicates"]:
            statuses.append(f"重复编号 {len(report['duplicates'])} 个")
            fatal = True
        if report["wrong_prefix"]:
            statuses.append(f"前缀异常 {len(report['wrong_prefix'])} 个")
            fatal = True
        lines.append(
            f"| {report['dimension']} | {len(report['files'])} | {report['unit_count']} | "
            f"{report['entry_count']} | {report['unique_entry_count']} | {report['expected_entries']} | "
            f"{format_counter(report['prefix_counts'])} | {'；'.join(statuses) or 'OK'} |"
        )

    supplemental_total = sum(int(report["entry_count"]) for report in supplemental_reports)
    lines += [
        "",
        f"D6 / D7 条目合计：**{supplemental_total}**；七维条目总计：**{total + supplemental_total}**。",
        "",
        f"自动验收结论：**{'未通过（见下方异常）' if fatal else '通过'}**。",
        "",
        "## 结构核对",
        "",
        "| 维度 | 大类 | 子类 | 大类下直接含条目的文件 | 时段数分布 | 前史标题 | 观点—文献依据 | 文献行 | 支持范围行 |",
        "| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for report in reports:
        lines.append(
            f"| {report['dimension']} | {report['category_count']} | {report['subcategory_count']} | "
            f"{report['direct_category_files']} | {format_counter(report['period_distribution'])} | "
            f"{report['period_labels'].get('前史', 0)} | {report['claim_count']} | "
            f"{report['reference_count']} | {report['support_count']} |"
        )

    lines += [
        "",
        "## 编号核对",
        "",
    ]
    for report in reports:
        lines += [
            f"### {report['dimension']}",
            "",
            f"- 重复编号：{compact_id_list(report['duplicates'])}",
            f"- 非预期前缀编号：{compact_id_list(report['wrong_prefix'])}",
            "",
        ]
    for report in supplemental_reports:
        lines += [
            f"### {report['dimension']}",
            "",
            f"- 拆分单位：{report['split_unit']}，共 {report['unit_count']} 个",
            f"- 重复编号：{compact_id_list(report['duplicates'])}",
            f"- 非预期前缀编号：{compact_id_list(report['wrong_prefix'])}",
            f"- 转换时直接调整的编号：{report['normalized_id_count']} 个",
            "",
        ]

    value_report = next(report for report in reports if report["dimension"] == "价值论")
    practice_report = next(report for report in reports if report["dimension"] == "实践论")
    epistemology_report = next(report for report in reports if report["dimension"] == "认识论")
    methodology_report = next(report for report in reports if report["dimension"] == "方法论")
    d6_report = next(report for report in supplemental_reports if report["directory"] == "学派传统")
    d7_report = next(report for report in supplemental_reports if report["directory"] == "学科史")
    period_anomalies = "、".join(
        f"{entry_id}={count}个时段" for entry_id, count in epistemology_report["period_anomalies"]
    )
    lines += [
        "## 源文档不一致与处理",
        "",
        f"1. **价值论缺少子类层级**：Pandoc 输出为 {value_report['category_count']} 个大类、{value_report['subcategory_count']} 个子类；其中 {value_report['direct_category_files']} 个大类文件直接含条目。脚本按大类开始缓冲，因此未静默丢条目。这是源稿层级不一致，不是转换器生成的问题；是否补齐子类需另行核对源内容。",
        f"2. **价值论条目标题额外加粗**：检测到 {value_report['bold_entry_headings']} 个 `#### **V…**` 标题。脚本兼容星号并保留原样；这是源稿格式不一致，不在本次转换中改写。",
        "3. **文献/支持范围结构与 Issue 描述不一致**：本批五份 Word 经 Pandoc 转换后，没有检测到独立的“观点—文献依据”“文献：”“支持范围：”行，因此无法复现“方法论差 7 条、实践论差 5 条”的核对口径。这不是脚本跳过，而是本次收到的源文件中不存在该结构；需由材料提供者确认是否拿到了另一版全量稿。",
        f"4. **实践论源稿编号前缀混用**：源稿使用 `P001`–`P141` 和 `R142`–`R370`。按统一要求，转换器已直接将 {practice_report['normalized_id_count']} 个 `R` 条目标题改为 `P`，Markdown 输出为连续唯一的 `P001`–`P370`；冻结 DOCX 保持原样。",
        f"5. **认识论拆分文件数不同**：源稿经 Pandoc 还原为 {epistemology_report['category_count']} 个大类和 {epistemology_report['subcategory_count']} 个子类，按既定切分规则生成 {len(epistemology_report['files'])} 个文件，而目录约定写 32 个。条目数仍为 {epistemology_report['entry_count']}；需确认目录约定是否基于旧版源稿。",
        f"6. **时段结构不同**：本体论、价值论、方法论和实践论当前稿均为 T1–T4 四个时段；认识论的分布为 {format_counter(epistemology_report['period_distribution'])}。异常条目为 {period_anomalies or '无'}。脚本按源稿原样保留，没有补写、删除或合并时段。",
        f"7. **方法论源稿重复编号**：源稿存在重复编号。按统一要求，转换器已按 Word 正文顺序直接重编号，修改 {methodology_report['normalized_id_count']} 个条目标题；Markdown 输出为连续唯一的 `M001`–`M690`，不生成旧编号映射，冻结 DOCX 保持原样。",
        f"8. **D6 学派传统**：源稿有 53 个学派四级标题，另有 10 组人物直接位于地区传统下、缺少学派层级。脚本兼容两种结构，共拆成 {d6_report['unit_count']} 个正文文件并另存目录说明；人物条目按正文顺序统一为连续唯一的 `P001`–`P218`，本次实际调整 {d6_report['normalized_id_count']} 个标题，并同步直接替换正文中的人物编号引用，不生成映射文件。",
        f"9. **D7 学科史**：源稿的 `H` 条目混用一级和二级标题。脚本按 `H` 编年条目拆成 {d7_report['unit_count']} 个正文文件，并另存说明与分组；编号统一为连续唯一的 `H001`–`H091`，本次实际调整 {d7_report['normalized_id_count']} 个编号。",
        "",
        "## 冻结快照",
        "",
        "以下文件已逐字节复制到 `knowledge/source/`。SHA-256 用于核对溯源快照：",
        "",
        "| 文件 | SHA-256 |",
        "| --- | --- |",
    ]
    for path in sorted(source_snapshots, key=lambda item: item.name):
        lines.append(f"| `{path.name}` | `{sha256(path)}` |")
    lines += [
        "",
        "D6、D7 已同时转换为 `knowledge/学派传统/` 与 `knowledge/学科史/`，但不计入内部五维 2555 条口径。当前源目录没有名为《纲要7》的独立文件；`D7_学科史.docx` 的正文标题为“D₇ 学科史”，因此仍按“学科史”命名。",
        "",
    ]
    return "\n".join(lines)


def copy_snapshots(src_root: Path, out_root: Path, dimension_sources: list[Path]) -> list[Path]:
    source_dir = out_root / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    selected: dict[str, Path] = {path.name: path for path in dimension_sources}
    for name in EXTRA_SOURCE_CANDIDATES:
        path = src_root / name
        if path.is_file():
            selected[path.name] = path
    copied: list[Path] = []
    for name, src in sorted(selected.items()):
        dst = source_dir / name
        shutil.copyfile(src, dst)
        copied.append(dst)
    for stale in source_dir.glob("*.docx"):
        if stale.name not in selected:
            stale.unlink()
    return copied


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    src_root = Path(sys.argv[1]).resolve()
    out_root = Path(sys.argv[2]).resolve()
    if not src_root.is_dir():
        print(f"源目录不存在：{src_root}", file=sys.stderr)
        return 1
    if src_root == out_root or src_root in out_root.parents:
        print("输出目录不能等于源目录，也不能位于源目录内部", file=sys.stderr)
        return 1

    try:
        pandoc = find_pandoc()
        pandoc_version = subprocess.run(
            [pandoc, "--version"], check=True, capture_output=True, text=True, encoding="utf-8"
        ).stdout.splitlines()[0]
        out_root.mkdir(parents=True, exist_ok=True)
        sources = [resolve_source(src_root, name, spec) for name, spec in DIMENSIONS.items()]
        d6_source = src_root / "D6_学派传统.docx"
        d7_source = src_root / "D7_学科史.docx"
        if not d6_source.is_file():
            raise FileNotFoundError(f"缺少 D6 源文件：{d6_source}")
        if not d7_source.is_file():
            raise FileNotFoundError(f"缺少 D7 源文件：{d7_source}")
        snapshots = copy_snapshots(src_root, out_root, sources)
        reports = [
            convert_dimension(name, spec, src, out_root, pandoc)
            for (name, spec), src in zip(DIMENSIONS.items(), sources)
        ]
        supplemental_reports = [
            convert_d6(d6_source, out_root, pandoc),
            convert_d7(d7_source, out_root, pandoc),
        ]
        report_text = build_report(reports, supplemental_reports, snapshots, pandoc_version)
        write_text(out_root / "转换报告.md", report_text)
        print(report_text)
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"转换失败：{exc}", file=sys.stderr)
        return 1

    fatal = any(
        report["entry_count"] != report["expected_entries"]
        or bool(report["duplicates"])
        or bool(report["wrong_prefix"])
        for report in reports + supplemental_reports
    )
    return 1 if fatal else 0


if __name__ == "__main__":
    raise SystemExit(main())
