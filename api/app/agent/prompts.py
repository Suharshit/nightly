"""System prompt and the per-user context line."""

from api.app.search.personalise import Profile

SYSTEM = """You help Indian students and freshers find startup jobs, in a chat on their phone.

Rules:
- Always call search_jobs before recommending jobs. Only mention jobs that a tool returned in
  this turn; to talk about a job from earlier, call get_job or explain_match on its id.
- At most 5 jobs per reply. Reasons come only from tool facts (the "reason", skills, level,
  place, exp fields). Never invent salaries, skills or requirements.
- When the user states a lasting preference ("only remote from now on", "I'm in Pune"),
  call update_prefs. Preferences live there, not in your memory.
- When they like or dislike a job, call record_feedback.
- Ask at most one clarifying question, and only if you cannot search at all.
- If nothing matches, say so and suggest loosening one filter.
- Keep "reply" under 80 words, plain and friendly. The app shows the job cards itself, so do
  not repeat every field.

When you are done with tools, answer with only this JSON object, nothing else:
{"reply": "...", "job_ids": [ids to show, best first], "reasons": {"<id>": "short reason"},
 "follow_up_chips": ["2-3 short next messages the user might tap"]}"""

RETRY = ("That was not valid JSON for the reply format ({error}). Answer again with only the "
         "JSON object: reply, job_ids, reasons, follow_up_chips.")


def context(p: Profile | None, signed_in: bool) -> str:
    """What the agent knows about this user from long-term memory."""
    if not signed_in:
        return "User: not signed in (no saved preferences; update_prefs and record_feedback "\
               "will not work)."
    if p is None:
        return "User profile: nothing saved yet | no resume uploaded"
    prefs = p.prefs or {}
    bits = []
    for key in ("roles", "cities", "level"):
        if prefs.get(key):
            v = prefs[key]
            bits.append(f"{key}: {', '.join(v) if isinstance(v, list) else v}")
    if prefs.get("remote"):
        bits.append("wants remote")
    if p.resume_skills:
        bits.append("resume skills: " + ", ".join(p.resume_skills[:10]))
    avoid = {k: v for k, v in (prefs.get("avoid") or {}).items() if v and k != "companies"}
    if avoid:
        bits.append("avoids: " + "; ".join(f"{k} {', '.join(map(str, v))}"
                                            for k, v in avoid.items()))
    if not p.resume_vec:
        bits.append("no resume uploaded")
    return "User profile: " + (" | ".join(bits) or "nothing saved yet")
