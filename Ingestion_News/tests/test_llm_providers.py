"""Offline tests: no Kafka broker, Ollama service, or paid API requests."""
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from openai import APIStatusError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import news_enrichment_consumer as news

VALID = json.dumps({
    "summary": "Revenue rose.",
    "overall_tone": "POSITIVE",
    "overall_tone_score": 0.8,
    "company_tones": [],
})


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def analyzer(self, provider):
        os.environ.update({
            "NEWS_LLM_PROVIDER": provider,
            f"{provider.upper()}_API_KEY": "test-only",
            "NEWS_LLM_MAX_ATTEMPTS": "2",
        })
        with patch.object(news, "OpenAI") as cloud, patch.object(news, "Client") as local:
            analyzer = news.NewsAnalyzer()
        return analyzer, cloud, local

    def test_default_is_local_without_keys_or_host(self):
        with patch.object(news, "Client") as local, patch.object(news, "OpenAI") as cloud:
            analyzer = news.NewsAnalyzer()
        self.assertEqual(analyzer.provider, "ollama")
        local.assert_called_once_with(host="http://127.0.0.1:11434", timeout=120)
        cloud.assert_not_called()

    def test_invalid_provider(self):
        for value in ("", "unknown"):
            with self.subTest(value=value), patch.dict(os.environ, {"NEWS_LLM_PROVIDER": value}):
                with self.assertRaisesRegex(ValueError, "NEWS_LLM_PROVIDER"):
                    news.NewsAnalyzer()

    def test_selected_cloud_key_required(self):
        for provider in ("openai", "gemini", "sarvam"):
            with self.subTest(provider=provider), patch.dict(
                os.environ, {"NEWS_LLM_PROVIDER": provider}, clear=True
            ):
                with self.assertRaisesRegex(ValueError, provider.upper() + "_API_KEY"):
                    news.NewsAnalyzer()

    def test_provider_routing_and_output(self):
        urls = {
            "openai": "https://api.openai.com/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "sarvam": "https://api.sarvam.ai/v1",
        }
        for provider in ("ollama", "openai", "gemini", "sarvam"):
            with self.subTest(provider=provider):
                analyzer, cloud, local = self.analyzer(provider)
                analyzer.client.chat.return_value = SimpleNamespace(
                    message=SimpleNamespace(content=VALID))
                analyzer.client.responses.parse.return_value = SimpleNamespace(
                    output_parsed=news.NewsAnalysis.model_validate_json(VALID))
                analyzer.client.chat.completions.create.return_value = SimpleNamespace(
                    choices=[SimpleNamespace(finish_reason="stop",
                        message=SimpleNamespace(content=VALID))])
                self.assertEqual(analyzer.analyze("Title", "Text").summary, "Revenue rose.")
                if provider == "ollama":
                    cloud.assert_not_called()
                    analyzer.client.chat.assert_called_once()
                else:
                    local.assert_not_called()
                    self.assertEqual(cloud.call_args.kwargs["base_url"], urls[provider])
                    self.assertEqual(cloud.call_args.kwargs["api_key"], "test-only")
                    if provider == "openai":
                        analyzer.client.responses.parse.assert_called_once()
                    else:
                        args = analyzer.client.chat.completions.create.call_args.kwargs
                        self.assertEqual(args["response_format"], {"type": "json_object"})
                        self.assertIn("company_tones", args["messages"][0]["content"])
                        analyzer.client.responses.parse.assert_not_called()

    def test_model_override_and_provider_normalization(self):
        os.environ.update(NEWS_LLM_PROVIDER=" GeMiNi ", GEMINI_API_KEY="test-only",
                          GEMINI_MODEL="custom-model")
        with patch.object(news, "OpenAI"):
            analyzer = news.NewsAnalyzer()
        self.assertEqual(analyzer.provider, "gemini")
        self.assertEqual(analyzer.model, "custom-model")

    def test_invalid_and_truncated_cloud_output_retries(self):
        for provider in ("gemini", "sarvam"):
            for content, reason in (("{}", "stop"), (VALID, "length"), ("bad", "stop")):
                with self.subTest(provider=provider, content=content, reason=reason):
                    analyzer, _, _ = self.analyzer(provider)
                    analyzer.client.chat.completions.create.return_value = SimpleNamespace(
                        choices=[SimpleNamespace(finish_reason=reason,
                            message=SimpleNamespace(content=content))])
                    with patch.object(news.time, "sleep"), self.assertRaises(RuntimeError):
                        analyzer.analyze("Title", "Text")
                    self.assertEqual(analyzer.client.chat.completions.create.call_count, 2)

    def test_cloud_auth_pauses_and_rate_limit_retries(self):
        for provider in ("openai", "gemini", "sarvam"):
            for status, code in ((401, "invalid_key"), (403, "forbidden"),
                                 (429, "insufficient_quota"), (429, "rate_limit")):
                with self.subTest(provider=provider, status=status, code=code):
                    analyzer, _, _ = self.analyzer(provider)
                    error = APIStatusError("blocked", response=httpx.Response(
                        status, request=httpx.Request("POST", "https://example.test")),
                        body={"code": code})
                    call = (analyzer.client.responses.parse if provider == "openai"
                            else analyzer.client.chat.completions.create)
                    call.side_effect = error
                    expected = RuntimeError if code == "rate_limit" else news.NewsEnrichmentPausedError
                    with patch.object(news.time, "sleep"), self.assertRaises(expected):
                        analyzer.analyze("Title", "Text")
                    self.assertEqual(call.call_count, 2 if code == "rate_limit" else 1)

    def test_paused_consumer_does_not_publish_or_commit(self):
        consumer = news.NewsEnrichmentConsumer.__new__(news.NewsEnrichmentConsumer)
        consumer.output_prefix = "news_enriched_"
        consumer.analyzer = Mock()
        consumer.analyzer.analyze.side_effect = news.NewsEnrichmentPausedError("blocked")
        consumer.consumer = Mock()
        consumer.publish = Mock()
        message = Mock()
        message.value.return_value = b'{"title":"Title","category":"general"}'
        with self.assertRaises(news.NewsEnrichmentPausedError):
            consumer.process(message)
        consumer.consumer.commit.assert_not_called()
        consumer.publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
