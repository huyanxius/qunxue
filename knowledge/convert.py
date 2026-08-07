#!/usr/bin/env python3
"""
把七维知识库的 Word 全量稿转成按子类拆分的 Markdown。

用法：python3 knowledge/convert.py <源目录> <输出目录>
源目录里放五份「<维度>全量.docx」（有几份跑几份，缺的跳过）。

转换分两步：先用 pandoc 把 docx 变成 Markdown，再按标题层级切成一个子类一个文件。
标题层级是这批文档唯一可靠的结构信息，切分和后续解析都依赖它：

#     文档标题（社会学认识论）
##    大类（I. 社会实在的本体论基础）
###   子类（1. 实在论与建构论之争）      <- 按这一层切文件
####  条目（E001 自然主义与反自然主义之争）
##### 时段（前史 / T1 / T2 / T3 / T4）

五份稿子出自两套 Word 模板：认识论、实践论、价值论用数字样式，本体论和方法论
用命名样式（Heading1-5）。pandoc 对两套都能正确还原成上面的层级，所以这里不需
要分别处理，但改动本脚本时要拿两类各跑一份验证，别只测一份就以为通了。

`-t markdown-smart` 是必须的：不关掉智能标点，原文的破折号「观点—文献依据」会
被写成「观点---文献依据」，条目正文里的引号也会变体，后续按字符匹配就会错。
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 维度名 -> 条目编号前缀。前缀同时用来核对条目数，防止 pandoc 或模板变化导致
# 静默丢条目。
DIMENSIONS = {
    "本体论": "C",
    "认识论": "E",
    "价值论": "V",
    "方法论": "M",
    "实践论": "P",
}

# 已知的条目数，来自 2026-08-06 对源文档的清点。转换结果与此不符时必须查清楚
# 原因再改这里的数字，不要反过来迁就转换结果。
EXPECTED_ENTRY_COUNT = {
    "本体论": 1067,
    "认识论": 124,
    "价值论": 304,
    "方法论": 690,
    "实践论": 370,
}

# 条目标题的星号来自源文档：价值论从 V108 起把条目标题额外加粗了，pandoc 忠实
# 地输出成 `#### **V108 ...**`。这是原稿的格式不一致，不是转换出的问题，所以在
# 这里兼容而不去改源文件。
ENTRY_RE = re.compile(r"^####\s+\*{0,2}([A-Z])(\d+)\b")


def find_pandoc() -> str:
    """查找 pandoc 可执行文件。pandoc 必须在系统 PATH 中，或安装在常见位置。"""
    p = shutil.which("pandoc")
    if p:
        return p
    candidates = [
        r"C:\Program Files\Pandoc\pandoc.exe",
        os.path.expanduser(r"~\AppData\Local\Pandoc\pandoc.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise RuntimeError("pandoc 未找到，请先安装：https://pandoc.org/installing.html")


def get_pandoc_version() -> str:
    """获取 pandoc 版本号，用于转换报告。"""
    try:
        pandoc = find_pandoc()
        r = subprocess.run([pandoc, "--version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.split("\n")[0].strip()
    except Exception:
        pass
    return "unknown"


def run_pandoc(src: Path, dst: Path) -> None:
    pandoc = find_pandoc()
    subprocess.run(
        [
            pandoc,
            "-f", "docx",
            "-t", "markdown-smart",
            "--wrap=none",
            str(src),
            "-o", str(dst),
        ],
        check=True,
    )


def safe_name(heading: str) -> str:
    """
    把子类标题变成文件名。去掉英文括注只是为了文件名别太长，中文部分保留原样——
    它是人在仓库里找文件唯一的线索，翻译或缩写反而认不出来。
    """
    name = heading.split("（")[0].split("(")[0].strip()
    name = re.sub(r'[/\\:*?"<>|]', "-", name)
    return name.strip(". ") or "未命名"


def split_by_subcategory(md: str) -> tuple[str, list[tuple[str, str, str]]]:
    """
    切成 (preamble, blocks) 二元组。

    preamble 是第一个 ## 之前的全部内容（文档标题 + T1-T4 定义等），
    单独落一个 00-00-文档说明.md，否则仓库里全是「T1 萌发期」却没有
    一个文件解释 T1-T4 是什么。

    blocks 是 (大类, 子类, 正文) 三元组列表。正文包含所属标题本身。

    子类这一层不是每份稿子都有：价值论有 30 个大类但只有 15 个子类，部分大类底
    下直接就是条目。所以进入大类就开始缓冲，遇到子类再另起一块；没有子类的大类
    整块出一个文件，子类名记为空。

    只认子类会静默丢掉那些条目——这正是 2026-08-06 第一版脚本在价值论上丢掉
    197 条的原因。
    """
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
            buf.append(line)
        elif line.startswith("### ") and not line.startswith("####"):
            flush()
            subcategory = line[4:].strip()
            buf.append(line)
        elif category:
            buf.append(line)
        else:
            # 第一个 ## 之前的内容——文档标题与 T1-T4 定义
            preamble.append(line)
    flush()
    return "\n".join(preamble).strip(), blocks


def convert(dimension: str, src: Path, out_root: Path) -> dict:
    raw = out_root / f".{dimension}.pandoc.md"
    try:
        run_pandoc(src, raw)
        md = raw.read_text(encoding="utf-8")
    finally:
        # 确保中间文件被清理，即使 pandoc 挂了
        if raw.exists():
            raw.unlink()

    preamble, blocks = split_by_subcategory(md)

    out_dir = out_root / dimension
    out_dir.mkdir(parents=True, exist_ok=True)

    # 清理旧文件
    for old in out_dir.glob("*.md"):
        old.unlink()

    # 写文档说明（T1-T4 定义等），放在 00-00 确保排在最前
    if preamble:
        (out_dir / "00-00-文档说明.md").write_text(preamble + "\n", encoding="utf-8")

    # 计算源 docx 的 SHA-256 哈希，用于冻结快照事后自证
    sha256 = hashlib.sha256(src.read_bytes()).hexdigest()[:16]

    prefix = DIMENSIONS[dimension]
    seen_ids: list[str] = []
    files = []

    cat_index = 0
    last_category = None
    sub_index = 0

    for category, subcategory, body in blocks:
        if category != last_category:
            cat_index += 1
            sub_index = 0
            last_category = category
        sub_index += 1

        ids = [
            f"{m.group(1)}{m.group(2)}"
            for m in (ENTRY_RE.match(line) for line in body.splitlines())
            if m
        ]
        seen_ids.extend(ids)

        label = safe_name(subcategory) if subcategory else safe_name(category)
        name = f"{cat_index:02d}-{sub_index:02d}-{label}.md"
        header = f"<!-- 大类：{category} -->\n\n"
        (out_dir / name).write_text(header + body + "\n", encoding="utf-8")
        files.append((name, len(ids)))

    wrong_prefix = [i for i in seen_ids if not i.startswith(prefix)]
    duplicates = sorted({i for i in seen_ids if seen_ids.count(i) > 1})
    placeholder_count = sum(1 for _, cnt in files if cnt == 0)

    return {
        "dimension": dimension,
        "files": files,
        "entry_count": len(seen_ids),
        "unique_entry_count": len(set(seen_ids)),
        "expected": EXPECTED_ENTRY_COUNT[dimension],
        "wrong_prefix": wrong_prefix,
        "duplicates": duplicates,
        "placeholder_count": placeholder_count,
        "source_hash": sha256,
        "pandoc_version": get_pandoc_version(),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    src_root = Path(sys.argv[1])
    out_root = Path(sys.argv[2])
    out_root.mkdir(parents=True, exist_ok=True)

    reports = []
    for dimension in DIMENSIONS:
        src = src_root / f"{dimension}全量.docx"
        if not src.exists():
            # 跳过缺失的维度文件（本 Issue 只负责价值论，其余由其他人负责）
            continue
        reports.append(convert(dimension, src, out_root))

    if not reports:
        print("错误：未找到任何维度的源文件")
        return 1

    ok = True
    lines = [
        "# 转换报告",
        "",
        f"pandoc 版本：{reports[0]['pandoc_version']}",
        "",
        "| 维度 | 文件数 | 占位文件 | 条目数 | 去重后 | 预期 | 前缀核对 | 状态 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for r in reports:
        status = []
        if r["entry_count"] != r["expected"]:
            status.append(f"条目数与预期不符（差 {r['entry_count'] - r['expected']:+d}）")
        if r["duplicates"]:
            status.append(f"重复编号 {len(r['duplicates'])} 个：{'、'.join(r['duplicates'][:5])}")
        if r["wrong_prefix"]:
            status.append(f"前缀异常 {len(r['wrong_prefix'])} 个")
        if status:
            ok = False
        prefix_ok = "✅ 无异常" if not r["wrong_prefix"] else f"❌ {len(r['wrong_prefix'])} 个异常"
        lines.append(
            f"| {r['dimension']} | {len(r['files'])} | {r['placeholder_count']} | "
            f"{r['entry_count']} | {r['unique_entry_count']} | {r['expected']} | "
            f"{prefix_ok} | {'；'.join(status) or 'OK'} |"
        )
        lines.append(f"  - 源文件 SHA-256：`{r['source_hash']}`")

    total = sum(r["entry_count"] for r in reports)
    lines += ["", f"条目合计：{total}"]

    (out_root / "转换报告.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
