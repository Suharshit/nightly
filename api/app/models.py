"""Loads the embedder once at startup. The reranker joins it on Fri."""

import os

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
