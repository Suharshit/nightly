"""The agent's final answer. The model must return exactly this JSON; the server validates it."""

from pydantic import BaseModel, Field

MAX_JOBS = 5


class AgentReply(BaseModel):
    reply: str = Field(min_length=1, max_length=1200)
    job_ids: list[int] = Field(default_factory=list)
    reasons: dict[int, str] = Field(default_factory=dict)
    follow_up_chips: list[str] = Field(default_factory=list)


def guard(reply: AgentReply, seen: dict[int, dict]) -> tuple[AgentReply, list[int]]:
    """Drop every job id no tool returned in this turn, keep at most 5, and give each kept
    job a reason: the model's wording if it has one, else the data-built reason from the
    tool. Returns the cleaned reply and the ids that were dropped (for the logs)."""
    kept, dropped = [], []
    for jid in dict.fromkeys(reply.job_ids):        # de-duplicate, keep order
        (kept if jid in seen and len(kept) < MAX_JOBS else dropped).append(jid)
    reasons = {j: (reply.reasons.get(j) or seen[j].get("reason") or "").strip() for j in kept}
    chips = [c.strip()[:40] for c in reply.follow_up_chips if c.strip()][:3]
    return reply.model_copy(update={"job_ids": kept, "reasons": reasons,
                                    "follow_up_chips": chips}), dropped
