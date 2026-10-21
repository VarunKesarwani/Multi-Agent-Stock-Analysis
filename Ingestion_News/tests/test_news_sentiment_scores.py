"""Regression tests for news sentiment score validation (no live services)."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError
from news_enrichment_consumer import NewsAnalysis, NewsAnalyzer


def payload(score=0.9):
    return {
        "summary": "Example Ltd reported lower earnings.",
        "overall_tone": "NEGATIVE",
        "overall_tone_score": score,
        "company_tones": [{
            "company": "Example Ltd", "symbol": None, "tone": "NEGATIVE",
            "tone_score": score, "relevance_score": 1.0,
        }],
    }


class SentimentScoreTests(unittest.TestCase):
    def analyzer(self, responses):
        analyzer = NewsAnalyzer.__new__(NewsAnalyzer)
        analyzer.provider = "ollama"
        analyzer.model = "test-model"
        analyzer.max_attempts = 3
        analyzer.retry_delay = 0.01
        analyzer.max_input_chars = 12000
        analyzer.client = Mock()
        analyzer.client.chat.side_effect = [
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(value)))
            for value in responses
        ]
        return analyzer

    def test_negative_tone_accepts_nonnegative_confidence(self):
        for score in (0.0, 0.9, 1.0):
            self.assertEqual(NewsAnalysis.model_validate(payload(score)).overall_tone, "NEGATIVE")

    def test_out_of_range_scores_are_rejected(self):
        for score in (-1, -0.5, 1.1):
            with self.assertRaises(ValidationError):
                NewsAnalysis.model_validate(payload(score))

    @patch("news_enrichment_consumer.time.sleep")
    def test_retry_corrects_negative_scores_with_validation_feedback(self, sleep):
        analyzer = self.analyzer([payload(-0.5), payload(0.9)])
        result = analyzer.analyze("Earnings fall", "Example Ltd reported lower earnings.")
        self.assertEqual(result.overall_tone_score, 0.9)
        self.assertEqual(result.company_tones[0].tone, "NEGATIVE")
        self.assertEqual(analyzer.client.chat.call_count, 2)
        first, second = analyzer.client.chat.call_args_list
        self.assertIn("never -0.9", first.kwargs["messages"][1]["content"])
        feedback = second.kwargs["messages"][0]["content"]
        self.assertIn("overall_tone_score", feedback)
        self.assertIn("company_tones.0.tone_score", feedback)
        self.assertIn("previous response failed validation", feedback)
        schema = first.kwargs["format"]
        self.assertEqual(schema["properties"]["overall_tone_score"]["minimum"], 0.0)

    @patch("news_enrichment_consumer.time.sleep")
    def test_invalid_scores_are_not_clamped_after_retry_exhaustion(self, sleep):
        analyzer = self.analyzer([payload(-0.5)] * 3)
        with self.assertRaisesRegex(RuntimeError, "failed after 3 attempts"):
            analyzer.analyze("Earnings fall", "Example Ltd reported lower earnings.")
        self.assertEqual(analyzer.client.chat.call_count, 3)

    @patch("news_enrichment_consumer.time.sleep")
    def test_transport_failure_does_not_create_validation_feedback(self, sleep):
        analyzer = self.analyzer([payload()])
        analyzer.client.chat.side_effect = [
            TimeoutError("timed out"),
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload()))),
        ]
        analyzer.analyze("Earnings fall", "Example Ltd reported lower earnings.")
        self.assertNotIn(
            "previous response failed validation",
            analyzer.client.chat.call_args.kwargs["messages"][0]["content"],
        )


if __name__ == "__main__":
    unittest.main()
