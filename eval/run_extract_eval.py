"""Score extraction against the owner's labels and write the table into eval/results.md.

Usage: python -m eval.run_extract_eval     (no database or API calls: sample + labels only)
"""

import sys

from eval.extract_common import FIELDS, LABELS, ROOT, SAMPLE, load_labels, load_sample, score
from eval.extract_common import norm as ec_norm

RESULTS = ROOT / "results.md"
START, END = "<!-- extract-eval:start -->", "<!-- extract-eval:end -->"
GROUPS = ("all", "rules only", "rules + LLM")


def pct(a: int, b: int) -> str:
    return "-" if not b else f"{100 * a / b:.0f}%"


def guessed(sample: list[dict], labels: dict, field: str) -> tuple[int, int]:
    """(jobs where the extractor gave a value but the owner found it not stated, jobs missed)."""
    lab = [(r, labels[r["job_id"]]) for r in sample if r["job_id"] in labels]
    missed = [(r, lb) for r, lb in lab if ec_norm(field, r["pred"][field])
              != ec_norm(field, lb["fields"][field])]
    return sum(lb["fields"][field] is None for _, lb in missed), len(missed)


def caveat(sample: list[dict], labels: dict) -> str:
    emp_g, emp_m = guessed(sample, labels, "employment_type")
    wm_g, wm_m = guessed(sample, labels, "work_mode")
    return ("Caveat on work_mode and employment_type: the labeller showed the title, location and "
            "description, but not the boards' structured fields (Lever and Ashby send a workplace "
            "type and a commitment; Greenhouse sends a remote flag), which the extractor uses. "
            "The rules also default employment_type to full_time when nothing else is found. "
            f"Of the employment_type misses, {emp_g} of {emp_m} are jobs the owner marked \"not "
            f"stated\"; for work_mode it is {wm_g} of {wm_m}. So those two rows mostly measure "
            "board metadata and the default against the description, not misread postings.")


def table(scores: dict, n_sample: int) -> str:
    groups = [g for g in GROUPS if g in scores]
    jobs = sum(scores[g]["jobs"] for g in groups if g != "all")
    lines = [f"{jobs} of {n_sample} sampled jobs labelled by the owner "
             f"({SAMPLE.name}, {LABELS.name}). A field is correct when the extracted value "
             "equals the label, including both being \"not stated\".", "",
             "| Field | " + " | ".join(f"{g} (n={scores[g]['jobs']})" for g in groups) + " |",
             "|---|" + "---|" * len(groups)]
    for f in FIELDS:
        cells = [pct(*scores[g]["fields"][f]) for g in groups]
        lines.append(f"| {f} | " + " | ".join(cells) + " |")
    prec, rec = [], []
    for g in groups:
        s = scores[g]["skills"]
        right = s["extracted"] - s["wrong"]
        prec.append(pct(right, s["extracted"]))
        rec.append(pct(right, right + s["missing"]))
    lines.append("| skills precision | " + " | ".join(prec) + " |")
    lines.append("| skills recall (owner-noticed misses) | " + " | ".join(rec) + " |")
    lines += ["", "Skills were judged, not labelled blind: the owner saw the extracted list, "
              "marked wrong ones and added missing ones, so recall counts only the misses the "
              "owner noticed."]
    return "\n".join(lines)


def write(section: str) -> None:
    body = f"{START}\n## Extraction\n\n{section}\n{END}"
    text = RESULTS.read_text(encoding="utf-8") if RESULTS.exists() else "# Eval results\n\n"
    if START in text and END in text:
        text = text[:text.index(START)] + body + text[text.index(END) + len(END):]
    else:
        text = text.rstrip() + "\n\n" + body + "\n"
    RESULTS.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sample, labels = load_sample(), load_labels()
    scores = score(sample, labels)
    if not scores:
        sys.exit("No labelled jobs yet: run python -m eval.label_extract")
    section = table(scores, len(sample)) + "\n\n" + caveat(sample, labels)
    print(section)
    write(section)
    print(f"\nWrote the Extraction section of {RESULTS.name}.")


if __name__ == "__main__":
    main()
