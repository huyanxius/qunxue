"""Deterministic, evidence-limited aggregation of curated frontier records.

This module does not infer publication dates from discovery dates or source-page
publication dates, and it does not perform clustering, embeddings, or novelty
assessment. Counts describe this supplied corpus, never the research field.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from unicodedata import normalize

_METHOD = "curated_topic_dictionary_v1"
# Membership is an editorial choice based only on explicit topic tags. A study
# may belong to several topics; totals across topics must not be added together.
_TOPIC_DICTIONARY = (
    (
        "care-family",
        "照护与家庭责任",
        (
            "老龄化",
            "家庭社会学",
            "养老服务",
            "空间社会学",
            "社会政策",
            "社会投资",
            "社会保障",
            "人力资本",
            "母职",
            "农村社会变迁",
            "照护",
            "家庭责任",
            "困境群体",
            "家校社协同",
            "社会政策与保障",
            "家庭与生育",
            "老龄化与照护",
            "健康与医疗",
            "安宁疗护",
            "数字化照护",
        ),
    ),
    (
        "youth",
        "青年成长与生活选择",
        (
            "青年成长",
            "农村教育",
            "留守青少年",
            "污名化",
            "同伴文化",
            "青年就业",
            "婚姻",
            "性别观念",
            "学校社会工作",
            "青少年心理支持",
            "家校社协同",
            "分层服务",
            "青年",
            "青年生育",
            "青年债务",
            "校园支持",
            "儿童与青少年",
            "教育与社会分层",
        ),
    ),
    (
        "work-trust",
        "劳动与社会信任",
        (
            "劳动过程",
            "社会流动",
            "社会信任",
            "劳动市场",
            "城市研究",
            "青年就业",
            "非正规就业",
            "社会保障",
            "劳动",
            "就业",
            "劳动与就业",
            "贫困与不平等",
        ),
    ),
    (
        "organization",
        "组织与专业协作",
        (
            "组织社会学",
            "医疗组织",
            "制度逻辑",
            "社区治理",
            "专业社工与志愿服务",
            "资源联动",
            "学校社会工作",
            "家校社协同",
            "农村社会工作",
            "民族地区服务",
            "本土人才培养",
            "专业赋能",
            "跨组织协作",
            "社会工作",
            "社会组织与慈善",
            "治理不可能三角",
            "行政发包制",
            "理性科层制",
            "现代公司治理",
            "不确定性管理",
        ),
    ),
    (
        "social-theory",
        "理论与知识建构",
        (
            "社会理论",
            "社会互动",
            "物质性",
            "身份认同",
            "中国社会学史",
            "知识社会学",
            "自主知识体系",
            "理论建构",
            "社会理论与方法",
        ),
    ),
    (
        "digital-society",
        "数字技术与社会生活",
        ("数字社会与技术", "数字社会", "平台劳动", "人工智能"),
    ),
    (
        "urban-rural",
        "城乡转型与基层治理",
        ("乡村与城乡", "社会治理", "社区治理", "乡村振兴", "乡村建设", "社区参与"),
    ),
    ("uncategorized", "待归类的研究线索", ()),
)


def _label(value: str) -> str:
    return " ".join(normalize("NFKC", value).split()).casefold()


def _tags(record: dict) -> set[str]:
    topics = record.get("topics", ())
    if not isinstance(topics, (list, tuple)):
        return set()
    return {_label(value) for value in topics if isinstance(value, str) and value.strip()}


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _publication_day(record: dict) -> date | None:
    """A day-shaped string is insufficient unless its precision is verified."""
    if record.get("published_at_precision") != "day":
        return None
    value = record.get("published_at")
    if type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _stream(record: dict) -> str:
    explicit = record.get("stream")
    if explicit in {"research", "practice"}:
        return explicit
    return "practice" if record.get("material_type") == "official_practice" else "research"


def _source_id(record: dict) -> str | None:
    return _text(record.get("source_id")) or _text(record.get("source_name"))


def _studies(records: Sequence[dict], as_of: date) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        record_id = _text(record.get("id"))
        if record_id is None:
            raise ValueError("Every frontier record must have a non-empty string id")
        canonical = _text(record.get("canonical_study_id")) or record_id
        grouped[(_stream(record), canonical)].append(record)

    studies = []
    for (stream, canonical), variants in sorted(grouped.items()):
        variants = sorted(variants, key=lambda row: (row["id"], _source_id(row) or ""))
        dates = {day for row in variants if (day := _publication_day(row)) is not None}
        # Conflicting dates cannot be cherry-picked to make a study look recent.
        day = next(iter(dates)) if len(dates) == 1 else None
        status = "undated" if day is None else "future" if day > as_of else "dated"
        sources = sorted({source for row in variants if (source := _source_id(row))})
        studies.append(
            {
                "canonical_study_id": canonical,
                "stream": stream,
                "records": variants,
                "tags": set().union(*(_tags(row) for row in variants)),
                "date": day,
                "date_status": status,
                "date_conflict": len(dates) > 1,
                "age": (as_of - day).days if status == "dated" else None,
                "source_ids": sources,
            }
        )
    return studies


def _window(studies: list[dict], start_age: int, end_age: int) -> list[dict]:
    return [
        study
        for study in studies
        if study["age"] is not None and start_age <= study["age"] < end_age
    ]


def _attributable_sources(studies: list[dict]) -> set[str]:
    # A duplicate's extra source must not manufacture cross-source support. If
    # origin metadata disagree, retain all provenance but omit it from the gate.
    return {study["source_ids"][0] for study in studies if len(study["source_ids"]) == 1}


def _date_window(as_of: date, start_age: int, end_age: int) -> dict:
    return {
        "start": (as_of - timedelta(days=end_age - 1)).isoformat(),
        "end": (as_of - timedelta(days=start_age)).isoformat(),
    }


def _summary(studies: list[dict], title: str, matched_tags: list[str]) -> str:
    """Short, attributed editorial synthesis, without generating conclusions."""
    questions: list[str] = []
    findings: list[str] = []
    for study in studies:
        for row in study["records"]:
            if (question := _text(row.get("research_question"))) and question not in questions:
                questions.append(question)
            reported = row.get("findings", ())
            if isinstance(reported, (list, tuple)):
                for finding in reported:
                    if isinstance(finding, str) and finding.strip() and finding not in findings:
                        findings.append(finding)
    text = f"编辑归纳：以“{title}”组织条目，标签涉及{'、'.join(matched_tags[:4])}。"
    if questions:
        text += "原条目提出的问题包括：" + " ".join(questions[:2])
        if not text.endswith(("。", "？", "！", "?", "!")):
            text += "。"
    elif findings:
        text += "原条目报告：" + "；".join(findings[:2])
        if not text.endswith(("。", "？", "！")):
            text += "。"
    return text + "仅反映所收录线索，不代表一致结论、因果验证或领域总体变化。"


def aggregate_topics(
    records: Sequence[dict],
    as_of: date,
    coverage_start: date | None = None,
) -> list[dict]:
    """Aggregate recognized topic tags, separating research and practice.

    Windows are inclusive calendar dates: 30 days means [as_of - 29, as_of].
    The growth baseline is the preceding 90 days (ages 30..119), divided by
    three; persistence compares ages 0..89 with ages 90..179. A coverage start
    is an explicit caller assertion of a continuously observed corpus, not an
    inferred minimum record date. Missing or zero growth baselines never imply
    an infinite growth rate. Historical semantic novelty is always unassessed.

    ``total`` counts unique canonical studies per topic and stream, including
    undated and future-dated entries retained for inspection. ``dated`` excludes
    future dates. ``total == dated + undated + future_dated``. Evidence and
    record_ids retain the underlying records after counting deduplication.
    Unrecognized labels are not assigned to an invented topic.
    """
    if type(as_of) is not date or (coverage_start is not None and type(coverage_start) is not date):
        raise TypeError("as_of and coverage_start must be calendar dates")
    studies = _studies(records, as_of)
    growth_covered = coverage_start is not None and coverage_start <= as_of - timedelta(days=119)
    persistence_covered = coverage_start is not None and coverage_start <= as_of - timedelta(
        days=179
    )
    results = []
    for topic_key, title, aliases in _TOPIC_DICTIONARY:
        topic_tags = {_label(alias) for alias in aliases}
        for stream in ("research", "practice"):
            known_tags = {_label(alias) for _, _, values in _TOPIC_DICTIONARY for alias in values}
            members = [
                study
                for study in studies
                if study["stream"] == stream
                and (
                    not study["tags"] & known_tags
                    if topic_key == "uncategorized"
                    else bool(study["tags"] & topic_tags)
                )
            ]
            if not members:
                continue
            recent_30 = _window(members, 0, 30)
            recent_90 = _window(members, 0, 90)
            recent_180 = _window(members, 0, 180)
            growth_prior = _window(members, 30, 120)
            persistence_prior = _window(members, 90, 180)
            baseline = len(growth_prior) / 3 if growth_covered else None
            weeks = {study["date"].isocalendar()[:2] for study in recent_90}
            reasons = []
            growth_reasons = []
            persistence_reasons = []
            if not growth_covered:
                growth_reasons.append("未确认完整覆盖最近30天及此前90天，增长基线不可用")
            elif baseline == 0:
                growth_reasons.append("此前90天未收录可计时条目，零基线不能支持倍数增长")
            if len(recent_30) < 4:
                growth_reasons.append("最近30天不足4项独立条目")
            if len(_attributable_sources(recent_30)) < 2:
                growth_reasons.append("最近30天缺少至少2个可明确归属的来源")
            if baseline is not None and baseline > 0 and len(recent_30) < 2 * baseline:
                growth_reasons.append("最近30天数量未达到此前90天月均数量的2倍")
            if not persistence_covered:
                persistence_reasons.append("未确认完整覆盖180天，不能比较连续两个90天窗口")
            if len(recent_90) < 4:
                persistence_reasons.append("最近90天不足4项独立条目")
            if len(_attributable_sources(recent_90)) < 2:
                persistence_reasons.append("最近90天缺少至少2个可明确归属的来源")
            if len(weeks) < 3:
                persistence_reasons.append("最近90天条目未分布于至少3个日历周")
            if len(recent_90) <= len(persistence_prior):
                persistence_reasons.append("最近90天数量未高于此前90天")
            signals = []
            if not growth_reasons:
                signals.append("rapid_growth")
            if not persistence_reasons:
                signals.append("sustained_activity")
            if topic_key == "uncategorized":
                signals = []
                reasons.append("待归类集合不是研究议题，不据此提出趋势")
            reasons.extend(growth_reasons)
            reasons.extend(persistence_reasons)
            undated = sum(study["date_status"] == "undated" for study in members)
            future = sum(study["date_status"] == "future" for study in members)
            if undated:
                reasons.append("缺少可核验的日精度出版日期的条目未参与时间窗口计算")
            if future:
                reasons.append("晚于统计截止日的出版日期未参与时间窗口计算")
            if any(study["date_conflict"] for study in members):
                reasons.append("同一研究的出版日期存在冲突，已从时间窗口排除")
            if any(len(study["source_ids"]) > 1 for study in members):
                reasons.append("同一研究的来源归属存在多值，仅保留出处，不增加多来源门槛计数")
            reasons.append("未执行历史语义或embedding比较，新议题状态为not_assessed")
            source_distribution = Counter(
                source for study in members for source in study["source_ids"]
            )
            evidence = []
            seen_evidence = set()
            for study in members:
                for row in study["records"]:
                    evidence_key = (row["id"], _source_id(row))
                    if evidence_key in seen_evidence:
                        continue
                    seen_evidence.add(evidence_key)
                    evidence.append(
                        {
                            "record_id": row["id"],
                            "canonical_study_id": study["canonical_study_id"],
                            "source_id": _source_id(row),
                            "published_at": row.get("published_at"),
                            "published_at_precision": row.get("published_at_precision"),
                            "counted_published_at": (
                                study["date"].isoformat()
                                if study["date_status"] == "dated"
                                else None
                            ),
                            "date_status": study["date_status"],
                            "url": row.get("url"),
                        }
                    )
            matched_tags = sorted(set().union(*(study["tags"] & topic_tags for study in members)))
            results.append(
                {
                    "id": f"{topic_key}-{stream}",
                    "topic_key": topic_key,
                    "title": title,
                    "stream": stream,
                    "record_ids": sorted(
                        {row["id"] for study in members for row in study["records"]}
                    ),
                    "source_ids": sorted(source_distribution),
                    "source_distribution": dict(sorted(source_distribution.items())),
                    "summary": _summary(members, title, matched_tags),
                    "summary_method": "editorial_synthesis",
                    "method": _METHOD,
                    "counts": {
                        "total": len(members),
                        "dated": len(members) - undated - future,
                        "undated": undated,
                        "future_dated": future,
                        "days_30": len(recent_30),
                        "days_90": len(recent_90),
                        "days_180": len(recent_180),
                        "previous_90": len(persistence_prior),
                        "prior_90_for_growth": len(growth_prior),
                        "prior_90_for_persistence": len(persistence_prior),
                    },
                    "trend_status": "supported" if signals else "insufficient_evidence",
                    "trend_signals": signals,
                    "growth_baseline": baseline,
                    "reasons": reasons,
                    "evidence": sorted(
                        evidence, key=lambda row: (row["record_id"], row["source_id"] or "")
                    ),
                    "novelty_status": "not_assessed",
                    "time_windows": {
                        "days_30": _date_window(as_of, 0, 30),
                        "days_90": _date_window(as_of, 0, 90),
                        "days_180": _date_window(as_of, 0, 180),
                        "prior_90_for_growth": _date_window(as_of, 30, 120),
                        "prior_90_for_persistence": _date_window(as_of, 90, 180),
                    },
                }
            )
    return results
