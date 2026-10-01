"""Offline counts of the visible corpus, not estimates of the research field.

Methods and data are classified only from their explicitly supplied text fields.
The small, versioned dictionaries allow overlapping categories and make no
inferences from titles, conclusions, topic tags, or a different field. Missing or
negated descriptions remain unknown; positive text without a match is unclassified.
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from unicodedata import normalize

CLASSIFICATION_METHOD = "explicit_field_dictionary_v1"

_METHODS = (
    (
        "case_study",
        "案例与个案研究",
        ("案例研究", "案例分析", "个案研究", "个案分析", "案例比较", "历史个案"),
    ),
    ("interview_observation", "访谈与观察", ("访谈", "观察")),
    (
        "fieldwork_ethnography",
        "田野与民族志",
        ("田野", "民族志", "实地调查", "实地调研", "跟踪调研"),
    ),
    (
        "quantitative_analysis",
        "统计与量化分析",
        (
            "回归",
            "结构方程",
            "线性模型",
            "线性混合模型",
            "条件分解",
            "因素分解",
            "中介分析",
            "中介模型",
            "随机效应模型",
            "倾向值匹配",
            "倾向得分匹配",
            "定量",
            "量化分析",
            "统计分析",
            "序列分析",
            "潜变量建模",
        ),
    ),
    (
        "historical_analysis",
        "历史与思想史分析",
        (
            "历史分析",
            "历史解释",
            "历史阐释",
            "比较历史",
            "历史个案",
            "思想史",
            "历史文献",
            "制度史",
            "社会学史",
            "学科史",
            "发展史",
            "口述历史",
        ),
    ),
    (
        "theory_concept",
        "理论与概念分析",
        (
            "理论分析",
            "理论讨论",
            "理论阐释",
            "理论比较",
            "理论梳理",
            "理论建构",
            "理论框架",
            "理论重构",
            "概念阐释",
            "概念分析",
            "概念比较",
            "概念建构",
            "概念与理论",
            "类型学建构",
            "框架建构",
        ),
    ),
    (
        "text_analysis",
        "文本与内容分析",
        (
            "文本分析",
            "文本阐释",
            "文本比较",
            "文本叙事",
            "政策文本",
            "制度文本",
            "内容分析",
            "经文解释",
        ),
    ),
    (
        "literature_review",
        "文献综述",
        ("系统综述", "范围综述", "研究综述", "文献综述", "文献梳理"),
    ),
    (
        "comparative_analysis",
        "比较研究",
        (
            "比较分析",
            "比较研究",
            "比较历史",
            "案例比较",
            "分期比较",
            "理论比较",
            "概念比较",
            "模型比较",
            "类型比较",
            "方法比较",
            "比较案例",
        ),
    ),
    (
        "network_computational",
        "网络与计算方法",
        ("社会网络分析", "整体网分析", "指数随机图模型", "计算模拟", "贝叶斯", "CiteSpace", "GIS"),
    ),
    (
        "qualitative_comparative",
        "定性比较分析",
        ("定性比较分析", "模糊集定性", "fsQCA", "QCA"),
    ),
    ("action_research", "行动与实践研究", ("行动研究", "实践研究")),
    ("qualitative_research", "质性研究", ("质性研究", "定性研究", "扎根分析", "扎根理论")),
)

_DATA = (
    (
        "survey",
        "调查与问卷数据",
        (
            "调查数据",
            "问卷",
            "追踪调查",
            "综合社会调查",
            "社会状况综合调查",
            "生活状况调查",
            "社会工作动态调查",
            "健康与营养调查",
            "CFPS",
            "CGSS",
            "CHARLS",
            "CEPS",
            "CHNS",
            "CLASS",
            "CSWLS",
            "WVS",
        ),
    ),
    ("panel", "追踪与面板数据", ("追踪调查", "面板数据", "纵向数据")),
    ("census", "人口普查数据", ("人口普查", "普查微观")),
    (
        "interview_fieldwork",
        "访谈、观察与田野材料",
        ("访谈", "观察", "田野", "实地材料", "实地调查"),
    ),
    ("policy_documents", "政策与制度文本", ("政策文本", "制度文本", "条例", "法规")),
    ("historical_archives", "历史与档案资料", ("历史", "档案", "日记", "卷宗")),
    ("literature", "研究文献", ("文献", "研究论文")),
    ("practice_cases", "实践案例资料", ("案例",)),
    (
        "digital_traces",
        "平台与数字踪迹",
        ("平台数据", "网络文本", "社交媒体", "帖子", "数字踪迹"),
    ),
    (
        "administrative",
        "行政与机构数据",
        ("行政记录", "行政数据", "机构数据", "登记数据", "起诉书", "卷宗"),
    ),
)

_CLAUSE_BOUNDARY = re.compile(r"[，,。；;！!？?\n]+")
# Omit a whole negated clause rather than treating its method/data names as
# positive evidence. This intentionally favors abstention over guessing.
_NEGATED = re.compile(
    r"未(?:报告|提及|说明|披露|提供|交代|明确|呈现|展示|给出|使用|采用|开展|进行|收集|涉及|见|发现)"
    r"|没有|未能|无法|不能确定|不(?:使用|采用|涉及|包含|详|明|适用)|未知|未详|尚不清楚"
    r"|(?:^|\s)无|无(?:可核实|可验证|相关|具体|明确|访谈|观察|数据|方法|报告|证据)"
    r"|\b(?:not\s+(?:reported|mentioned|specified|provided|available|used)|unknown|n/?a)\b"
)


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _stream(record: dict) -> str:
    # Material type is the same authority used by browse/search. An inconsistent
    # optional stream label must never turn an official practice into research.
    return "practice" if record.get("material_type") == "official_practice" else "research"


def _is_visible(record: dict) -> bool:
    flags = record.get("eligibility")
    return (
        record.get("is_current") is not False
        and not record.get("withdrawn")
        and not record.get("withdrawn_at")
        and record.get("verification_status") not in {"review_queue", "withdrawn"}
        and (
            "eligibility" not in record or (isinstance(flags, dict) and flags.get("browse") is True)
        )
    )


def _identity(record: dict) -> tuple[str, str]:
    record_id = _text(record.get("id"))
    if record_id is None:
        raise ValueError("Every frontier record must have a non-empty string id")
    return _stream(record), _text(record.get("canonical_study_id")) or record_id


def visible_corpus_records(records: Sequence[dict]) -> list[dict]:
    """Return current browse representatives, preserving separate material streams.

    Representatives use the unfiltered lexical browse order: source-page date
    descending, then record ID descending. The page date controls only this
    deterministic selection; it never supplies a research publication year.
    The input records are neither modified nor reclassified.
    """
    visible = [record for record in records if _is_visible(record)]
    for record in visible:
        _identity(record)
    visible.sort(
        key=lambda row: (_text(row.get("source_published_at")) or "", row["id"]),
        reverse=True,
    )
    seen = set()
    result = []
    for record in visible:
        identity = _identity(record)
        if identity not in seen:
            seen.add(identity)
            result.append(record)
    return result


def _positive_clauses(value: object) -> list[str]:
    values = value if isinstance(value, (list, tuple)) else [value]
    clauses = []
    for item in values:
        if not (text := _text(item)):
            continue
        for clause in _CLAUSE_BOUNDARY.split(normalize("NFKC", text).casefold()):
            clause = clause.strip()
            if clause and not _NEGATED.search(clause):
                clauses.append(clause)
    return clauses


def _contains(clause: str, keyword: str) -> bool:
    keyword = normalize("NFKC", keyword).casefold()
    if keyword.isascii():
        return bool(re.search(r"(?<![a-z])" + re.escape(keyword) + r"(?![a-z])", clause))
    return keyword in clause


def _classify(value: object, dictionary: tuple) -> list[tuple[str, str]]:
    clauses = _positive_clauses(value)
    if not clauses:
        return [("unknown", "未报告或信息不足")]
    matched = [
        (key, label)
        for key, label, keywords in dictionary
        if any(_contains(clause, keyword) for clause in clauses for keyword in keywords)
    ]
    return matched or [("unclassified", "已报告但未归类")]


def _publication_year(record: dict) -> str:
    value = record.get("publication_year")
    if type(value) is int and 1000 <= value <= 9999:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"[1-9]\d{3}", value.strip()):
        return value.strip()
    # A calendar publication date is explicit publication metadata, unlike the
    # source-page or discovery dates, which are deliberately never consulted.
    published = record.get("published_at")
    if isinstance(published, str):
        try:
            return str(date.fromisoformat(published).year)
        except ValueError:
            pass
    return "unknown"


def _distribution(groups: dict, labels: dict) -> list[dict]:
    return [
        {"key": key, "label": labels[key], "count": len(ids), "record_ids": sorted(ids)}
        for key, ids in sorted(
            groups.items(),
            key=lambda pair: (pair[0] in {"unknown", "unclassified"}, -len(pair[1]), pair[0]),
        )
        if ids
    ]


def corpus_statistics(records: Sequence[dict], topics: Sequence[dict]) -> dict:
    """Describe deduplicated browse records using explicit, auditable metadata.

    All five distributions count research only. ``practice_count`` is separate.
    Topic membership comes exclusively from the passed research aggregates;
    duplicate aliases are mapped to the visible canonical representative. Any
    research absent from those aggregates gets an explicit unknown topic bucket.
    ``record_ids`` always reference visible representatives, and each is counted
    once per category. Category totals may exceed the research denominator.
    """
    visible = visible_corpus_records(records)
    research = [record for record in visible if _stream(record) == "research"]
    groups = {name: defaultdict(set) for name in ("source", "year", "topic", "method", "data")}
    labels = {name: {} for name in groups}

    def add(name: str, key: str, label: str, record_id: str) -> None:
        groups[name][key].add(record_id)
        # Conflicting display names must not make the output input-order dependent.
        labels[name][key] = min(labels[name].get(key, label), label)

    for record in research:
        record_id = record["id"]
        source_name = _text(record.get("source_name"))
        source = _text(record.get("source_id")) or source_name or "unknown"
        add(
            "source",
            source,
            source_name or (source if source != "unknown" else "来源未注明"),
            record_id,
        )
        year = _publication_year(record)
        add("year", year, year if year != "unknown" else "出版年份未注明", record_id)
        for name, field, dictionary in (("method", "methods", _METHODS), ("data", "data", _DATA)):
            for key, label in _classify(record.get(field), dictionary):
                add(name, key, label, record_id)

    representatives = {_identity(record): record["id"] for record in research}
    aliases = {
        record["id"]: representatives[_identity(record)]
        for record in records
        if _is_visible(record) and _identity(record) in representatives
    }
    assigned = set()
    for topic in topics:
        if topic.get("stream") != "research":
            continue
        key = _text(topic.get("topic_key")) or _text(topic.get("id"))
        if key is None:
            continue
        label = _text(topic.get("title")) or key
        members = topic.get("record_ids", [])
        if not isinstance(members, (list, tuple)):
            continue
        for alias in members:
            if isinstance(alias, str) and (record_id := aliases.get(alias)):
                assigned.add(record_id)
                add("topic", key, label, record_id)
    for record in research:
        if record["id"] not in assigned:
            add("topic", "unknown", "缺少主题归类", record["id"])

    return {
        "research_count": len(research),
        "practice_count": len(visible) - len(research),
        **{f"{name}_distribution": _distribution(groups[name], labels[name]) for name in groups},
        "classification_method": CLASSIFICATION_METHOD,
        "overlapping_categories": True,
    }
