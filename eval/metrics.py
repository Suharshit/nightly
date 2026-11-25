"""Graded-relevance metrics. Grades: 2 great, 1 ok, 0 no. Unlabelled results count as 0."""

import math


def dcg(grades: list[int]) -> float:
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades))


def ndcg_at(ranked: list[int], labels: dict[int, int], k: int = 10) -> float:
    """DCG of the top k over the DCG of the best possible top k from all labelled jobs."""
    ideal = dcg(sorted(labels.values(), reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return dcg([labels.get(d, 0) for d in ranked[:k]]) / ideal


def recall_at(ranked: list[int], labels: dict[int, int], k: int) -> float:
    """Share of all jobs labelled relevant (grade >= 1) that appear in the top k."""
    relevant = {d for d, g in labels.items() if g >= 1}
    if not relevant:
        return 0.0
    return len(relevant & set(ranked[:k])) / len(relevant)


def mrr(ranked: list[int], labels: dict[int, int], k: int) -> float:
    """1 / rank of the first relevant job in the top k (0 if none)."""
    for i, d in enumerate(ranked[:k], 1):
        if labels.get(d, 0) >= 1:
            return 1.0 / i
    return 0.0


def judged_at(ranked: list[int], labels: dict[int, int], k: int = 10) -> float:
    """How much of the top k has a label at all. Low values mean the numbers are unreliable."""
    top = ranked[:k]
    return sum(d in labels for d in top) / len(top) if top else 1.0
