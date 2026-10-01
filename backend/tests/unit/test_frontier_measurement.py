import unittest

from qunxue_api.modules.frontier_knowledge.analysis import record_topic_keys


class MeasurementTests(unittest.TestCase):
    def test_title_and_original_publisher_keywords_match_fine_grained_youth_terms(self):
        self.assertIn(
            "youth", record_topic_keys({"title": "青年软件工程师的成年转型", "topics": []})
        )
        self.assertIn(
            "youth",
            record_topic_keys(
                {
                    "title": "日常互动",
                    "keywords": ["青少年网络暴力"],
                    "topics_source": "publisher_keywords",
                    "topics": [],
                }
            ),
        )

    def test_journal_name_and_manual_topic_tags_cannot_create_measurement_membership(self):
        row = {
            "title": "资源转换路径",
            "source_name": "青年研究",
            "topics": ["青年"],
            "topics_source": "manualtopic_review",
            "keywords": ["青年"],
        }
        self.assertNotIn("youth", record_topic_keys(row))

    def test_identical_title_and_keywords_use_same_measurement_across_years(self):
        text = {
            "title": "青年软件工程师的平台劳动",
            "keywords": ["人工智能", "青少年"],
            "topics_source": "publisher_keywords",
        }
        old = {**text, "publication_year": 2023, "topics": ["青年"]}
        new = {**text, "publication_year": 2025, "topics": ["青年软件工程师", "劳动过程"]}
        self.assertEqual(
            record_topic_keys(old), frozenset({"youth", "work-trust", "digital-society"})
        )
        self.assertEqual(record_topic_keys(new), record_topic_keys(old))

    def test_unknown_content_is_auditable_instead_of_inferred_from_journal(self):
        self.assertEqual(
            record_topic_keys(
                {"title": "收录说明", "source_name": "青年研究", "topics": ["人工编辑类别"]}
            ),
            frozenset({"uncategorized"}),
        )

    def test_editorial_keyword_field_is_not_publisher_evidence(self):
        self.assertNotIn(
            "youth",
            record_topic_keys(
                {
                    "title": "资源转换路径",
                    "keywords": ["青年"],
                    "topics_source": "assistant_editorial",
                }
            ),
        )
