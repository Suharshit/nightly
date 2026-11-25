"""Loads the embedder and the reranker once at startup."""

import os

from api.app.search.rerank import MAX_TOKENS

# bge v1.5: queries get this instruction; documents (embed.py) don't.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    def __init__(self, name: str | None = None):
        from sentence_transformers import SentenceTransformer  # heavy: import only when used
        self.model = SentenceTransformer(
            name or os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5"), device="cpu")

    def query(self, text: str) -> list[float]:
        return self.model.encode(QUERY_PREFIX + text, normalize_embeddings=True,
                                 show_progress_bar=False).tolist()


class Reranker:
    """Cross-encoder over (query, job text) pairs. Returns raw logits; see search/rerank.py."""

    def __init__(self, name: str | None = None):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(
            name or os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
            device="cpu", max_length=MAX_TOKENS)

    def score(self, query: str, texts: list[str]) -> list[float]:
        return self.model.predict([(query, t) for t in texts], batch_size=32,
                                  show_progress_bar=False).tolist()
