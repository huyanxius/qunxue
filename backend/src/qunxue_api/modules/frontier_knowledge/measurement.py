"""Versioned lexical period measurement, independent of editable browsing tags.

These are phrase occurrences in original titles and attributable publisher
keywords, not semantic topic adjudication. Rules are identical for every year,
source and issue. Journal names, summaries and manual/editorial labels never
enter the measured text. Categories overlap and unmatched studies stay visible.
"""

from unicodedata import normalize

MEASUREMENT_METHOD = "title_publisher_keywords_phrase_dictionary"
MEASUREMENT_VERSION = "frontier_topic_measurement_v2"

# Frozen terms for this version. Changes require a new version and recomputation
# of all compared periods; never adjust terms for one year or desired direction.
TOPIC_TERMS = {
    "care-family": (
        "家庭",
        "生育",
        "婚姻",
        "养老",
        "老龄",
        "照护",
        "母职",
        "父职",
        "亲职",
        "健康",
        "医疗",
        "疾病",
        "残疾",
        "安宁疗护",
        "社会保障",
        "社会政策",
    ),
    "youth": ("青年", "青少年", "儿童", "大学生", "未成年", "同伴文化", "高职学生", "中学生"),
    "work-trust": (
        "劳动",
        "就业",
        "职业",
        "工作时间",
        "劳务",
        "用工",
        "工资",
        "薪酬",
        "社会流动",
        "社会信任",
        "白领",
        "工作场所",
    ),
    "organization": (
        "组织",
        "制度",
        "社会工作",
        "社工",
        "志愿",
        "科层",
        "专业协作",
        "协同",
        "治理",
    ),
    "social-theory": (
        "理论",
        "社会学史",
        "知识体系",
        "知识建构",
        "知识社会学",
        "社会互动",
        "身份认同",
        "物质性",
    ),
    "digital-society": ("数字", "互联网", "网络", "平台", "人工智能", "算法", "社交媒体", "数据化"),
    "urban-rural": ("乡村", "农村", "城乡", "城市", "社区", "县域", "基层", "乡镇"),
}


def publisher_keywords(record: dict) -> tuple[str, ...]:
    if record.get("topics_source") != "publisher_keywords":
        return ()
    values = record.get("keywords")
    if not values and isinstance(record.get("original_source_record"), dict):
        values = record["original_source_record"].get("keywords")
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return ()
    return tuple(v.strip() for v in values if isinstance(v, str) and v.strip())


def measured_topic_keys(record: dict) -> frozenset[str]:
    title = record.get("title")
    fields = [title] if isinstance(title, str) and title.strip() else []
    fields.extend(publisher_keywords(record))
    text = normalize("NFKC", " ".join(fields)).casefold()
    keys = frozenset(
        key for key, phrases in TOPIC_TERMS.items() if any(phrase in text for phrase in phrases)
    )
    return keys or frozenset({"uncategorized"})
