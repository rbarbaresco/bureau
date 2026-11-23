#!/usr/bin/env python3
"""UserPromptSubmit hook: the human's `/setup-bureau [1a 2c 3b]`, the only writer of bureau.json.

No answers: prints the questionnaire built from bureau.template.json, marking the current values.
Answers (<question number><option letter>, any subset): merged into bureau.json, then the questionnaire again.
An unknown or repeated answer blocks the prompt and writes nothing. gate.py denies the agent's own writes to bureau.json.
"""
import json
import os
import re
import string
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import desk  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bureau.template.json")


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def questionnaire(template, current):
    out = []
    for n, q in enumerate(template, 1):
        values = [v for v, _ in q["options"]]
        now = current.get(q["key"], "off" if "off" in values else q["suggest"])  # desk.py reads a missing key the same way
        out.append(f"{n}. {q['title']}\n   {q['does']}")
        for letter, (value, label) in zip(string.ascii_lowercase, q["options"]):
            out.append(f"   {letter}) {value}{': ' + label if label else ''}{'   <- current' if value == now else ''}")
        suggest = string.ascii_lowercase[values.index(q["suggest"])]
        out.append(f"   Suggestion: {suggest}\n")
    example = " ".join(f"{n}{string.ascii_lowercase[[v for v, _ in q['options']].index(q['suggest'])]}"
                       for n, q in enumerate(template, 1))
    out.append(f"Answer with: /setup-bureau {example}   (any subset; unanswered settings stay as they are)")
    return "\n".join(out)


def main():
    ev = json.load(sys.stdin)
    m = re.match(r"\s*/setup-bureau\b(.*)", ev.get("prompt", ""))  # only the command line: a note below is ignored
    if not m:
        return
    try:
        with open(TEMPLATE) as f:
            template = json.load(f)
    except (OSError, ValueError) as e:
        block(f"bureau.template.json is missing or unreadable ({e}); restore it from git. Nothing was saved.")
    current = desk.settings()
    answers = {}
    for word in m[1].split():
        a = re.fullmatch(r"(\d+)([a-z])", word.lower())
        n = int(a[1]) - 1 if a else -1
        if not a or not 0 <= n < len(template) or string.ascii_lowercase.index(a[2]) >= len(template[n]["options"]):
            block(f"'{word}' is not an answer: use a question number and an option letter, e.g. 1a. Nothing was saved.")
        if template[n]["key"] in answers:
            block(f"question {n + 1} is answered twice. Nothing was saved.")
        answers[template[n]["key"]] = template[n]["options"][string.ascii_lowercase.index(a[2])][0]
    if answers:
        current = {**current, **answers}
        with open(desk.SETTINGS, "w") as f:
            json.dump(current, f, indent=2)
        print("Saved to bureau.json. New cards use these settings; running cards keep theirs.\n")
    print(questionnaire(template, current))


if __name__ == "__main__":
    main()
