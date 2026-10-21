import unittest

from chunk_embedding_pipeline import (
    AnnualReportEmbeddingPipeline,
    prepare_chunks,
    split_bounded_text,
)


class ChunkPreparationTests(unittest.TestCase):
    def test_split_is_bounded_and_makes_progress(self):
        text = "alpha " * 1_000
        parts = split_bounded_text(text, max_chars=400, overlap_chars=40)

        self.assertGreater(len(parts), 1)
        self.assertTrue(all(0 < len(part) <= 400 for part in parts))

    def test_ids_are_stable_and_unique_for_parts(self):
        chunks = [
            {
                "chunk_id": 7,
                "source_file": "TATASTEEL_2025.md",
                "symbol": "TATASTEEL",
                "year": "2025",
                "text": "revenue " * 200,
            }
        ]
        first = prepare_chunks(chunks, max_chars=300, overlap_chars=30)
        second = prepare_chunks(chunks, max_chars=300, overlap_chars=30)

        self.assertEqual(
            [item["point_id"] for item in first],
            [item["point_id"] for item in second],
        )
        self.assertEqual(len(first), len({item["point_id"] for item in first}))

    def test_failed_batch_is_divided_and_bad_chunk_isolated(self):
        pipeline = object.__new__(AnnualReportEmbeddingPipeline)

        def fake_embed(texts):
            if "bad" in texts:
                raise RuntimeError("simulated Ollama 500")
            return [[float(len(text))] for text in texts]

        pipeline.embed_texts = fake_embed
        batch = [
            {"text": "good-one", "point_id": "1"},
            {"text": "bad", "point_id": "2"},
            {"text": "good-two", "point_id": "3"},
        ]

        embedded, failed = pipeline._embed_resilient(batch)

        self.assertEqual([item[0]["point_id"] for item in embedded], ["1", "3"])
        self.assertEqual([item[0]["point_id"] for item in failed], ["2"])


if __name__ == "__main__":
    unittest.main()
