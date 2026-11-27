"""Score extraction against the owner's labels and write the table into eval/results.md.

Usage: python -m eval.run_extract_eval     (no database or API calls: sample + labels only)
"""

import sys

from eval.extract_common import FIELDS, LABELS, ROOT, SAMPLE, load_labels, load_sample, score

RESULTS = ROOT / "results.md"
START, END = "<!-- extract-eval:start -->", "<!-- extract-eval:end -->"
GROUPS = ("all", "rules only", "rules + LLM")


def pct(a: int, b: int) -> str:
    return "-" if not b else f"{100 * a / b:.0f}%"


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
    section = table(scores, len(sample))
    print(section)
    write(section)
    print(f"\nWrote the Extraction section of {RESULTS.name}.")


if __name__ == "__main__":
    main()
