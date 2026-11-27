"""Say, for each proposed chat turn, what the agent should do. The owner labels; never an LLM.

  python -m eval.label_agent             # label every turn not yet labelled (resumes)
  python -m eval.label_agent --case a17  # (re)label one turn
  python -m eval.label_agent --stats

For each turn: type the tools the agent should call (numbers, e.g. "3,1"; 0 = no tool),
then the key arguments that must be right (Enter skips one). Every answer is appended to
eval/agent_labels.jsonl at once. No database or model is needed.
"""

import argparse
import json
import sys
from collections import Counter

from eval.agent_common import (
    AGENT_LABELS,
    HINTS,
    KEY_ARGS,
    TOOLS,
    load_agent_labels,
    load_cases,
    parse_arg,
)

MENU = "  ".join(f"{i} {t}" for i, t in enumerate(TOOLS, 1)) + "  0 no tool"


def show(case: dict, i: int, n: int) -> None:
    print("\n" + "=" * 78)
    print(f"[{case['id']}  {i}/{n}]")
    if case.get("prefs"):
        print(f"Saved prefs: {json.dumps(case['prefs'])}")
    for m in case.get("history") or []:
        print(f"  {m['role']}: {m['content']}")
        for j in m.get("shown") or []:
            print(f"      - {j}")
    print(f"USER NOW: {case['message']}")
    print("-" * 78)


def ask_tools() -> list[str] | str:
    while True:
        a = input(f"tools? [{MENU}; s skip, q quit]: ").strip().lower()
        if a in ("s", "q"):
            return a
        try:
            nums = [int(x) for x in a.replace(" ", "").split(",") if x]
        except ValueError:
            nums = []
        if nums == [0]:
            return []
        if nums and all(1 <= x <= len(TOOLS) for x in nums):
            return [TOOLS[x - 1] for x in dict.fromkeys(nums)]
        print("Type numbers like 1 or 3,1 (0 = no tool).")


def ask_args(tool: str) -> dict:
    out = {}
    for name, kind, choices in KEY_ARGS[tool]:
        hint = " / ".join(choices) if choices else {"list": "comma list", "int": "number"}.get(
            kind, "")
        if name in HINTS:
            hint = f"{hint}; {HINTS[name]}" if hint else HINTS[name]
        while True:
            raw = input(f"  {tool}.{name} ({hint}) [Enter = don't check]: ")
            if not raw.strip():
                break
            try:
                value = parse_arg(kind, raw)
            except ValueError:
                print("  That is not a number.")
                continue
            if choices and str(value).lower() not in choices:
                print(f"  The agent can only send one of: {', '.join(choices)}")
                continue
            out[name] = value.lower() if choices else value
            break
    return out


def label(only: str | None) -> None:
    cases = [c for c in load_cases() if not only or c["id"] == only]
    done = load_agent_labels()
    todo = [c for c in cases if only or c["id"] not in done]
    if not todo:
        print("Nothing left to label. Next: python -m eval.run_agent_eval")
        return
    print(__doc__.split("\n\n")[2])
    with AGENT_LABELS.open("a", encoding="utf-8") as out:
        for i, case in enumerate(todo, 1):
            show(case, i, len(todo))
            tools = ask_tools()
            if tools == "q":
                print("Saved. Run the same command to carry on.")
                return
            if tools == "s":
                continue
            args = {t: a for t in tools if (a := ask_args(t))}
            out.write(json.dumps({"id": case["id"], "tools": tools, "args": args}) + "\n")
            out.flush()
    print("\nAll turns labelled. Next: python -m eval.run_agent_eval")


def stats() -> None:
    cases, done = load_cases(), load_agent_labels()
    tools = Counter(t for lab in done.values() for t in (lab["tools"] or ["(none)"]))
    print(f"Labelled {sum(c['id'] in done for c in cases)}/{len(cases)} turns. "
          f"Expected tools: {dict(tools)}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--case")
    p.add_argument("--stats", action="store_true")
    a = p.parse_args()
    stats() if a.stats else label(a.case)


if __name__ == "__main__":
    main()
