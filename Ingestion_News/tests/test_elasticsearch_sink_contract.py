import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


class ElasticsearchSinkContractTests(unittest.TestCase):
    def test_template_covers_mcp_exact_match_fields(self):
        template = load_json("elasticsearch/news-enriched-index-template.json")
        mappings = template["template"]["mappings"]
        properties = mappings["properties"]

        self.assertEqual("strict", mappings["dynamic"])
        for field in ("category", "source", "enrichment_status"):
            self.assertEqual("keyword", properties[field]["fields"]["keyword"]["type"])

        analysis = properties["analysis"]["properties"]
        self.assertEqual("keyword", analysis["overall_tone"]["fields"]["keyword"]["type"])
        symbol = analysis["company_tones"]["properties"]["symbol"]
        self.assertEqual("keyword", symbol["fields"]["keyword"]["type"])

    def test_template_covers_success_and_failure_events(self):
        template = load_json("elasticsearch/news-enriched-index-template.json")
        properties = template["template"]["mappings"]["properties"]

        expected_top_level_fields = {
            "event_type",
            "schema_version",
            "news_id",
            "category",
            "source",
            "title",
            "summary",
            "link",
            "published_at",
            "fetched_at",
            "enrichment_status",
            "analysis",
            "enrichment_error_type",
            "processed_at",
        }
        self.assertTrue(expected_top_level_fields.issubset(properties))

    def test_connector_routes_topics_and_uses_news_id_key(self):
        connector = load_json("kafka-connect/news-elasticsearch-sink.json")["config"]

        self.assertEqual("news_enriched_.*", connector["topics.regex"])
        self.assertEqual("^news_enriched_(.*)$", connector["transforms.routeIndex.regex"])
        self.assertEqual("news-enriched-$1", connector["transforms.routeIndex.replacement"])
        self.assertEqual("false", connector["key.ignore"])
        self.assertEqual("INSERT", connector["write.method"])
        self.assertEqual("true", connector["flush.synchronously"])
        self.assertEqual("warn", connector["behavior.on.malformed.documents"])
        self.assertEqual("news_elasticsearch_sink_dlq", connector["errors.deadletterqueue.topic.name"])


if __name__ == "__main__":
    unittest.main()
