import unittest
from unittest.mock import patch

from ai_agent.tools.rag.ingestion import retrieval


class EmbeddingModelCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        retrieval.get_embeddings.cache_clear()

    def tearDown(self) -> None:
        retrieval.get_embeddings.cache_clear()

    def test_embedding_model_is_initialized_once_and_reused(self) -> None:
        model = object()
        with patch.object(
            retrieval,
            "HuggingFaceEmbeddings",
            return_value=model,
        ) as constructor:
            first = retrieval.get_embeddings()
            second = retrieval.get_embeddings()

        self.assertIs(first, model)
        self.assertIs(second, model)
        constructor.assert_called_once_with(
            model_name=retrieval.EMBEDDING_MODEL,
        )
