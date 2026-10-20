#!/usr/bin/env python3
"""Workflow files: parse, list, start a run.

Usage: workflow.py list
       workflow.py show <name|file>
       workflow.py start <name|file> <card-dir>

File format (workflows/<name>.md):
    ---
    name: bugfix
    use_when: one line the matcher reads
    ---
    ## step-id
    persona: staff-engineer
    gate: none | approve | approve+check
    writes_code: true            (optional)

    Free-text instructions for the step.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desk

BUREAU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYS = ("persona", "gate", "writes_code", "reads", "writes")


def parse(path):
    text = open(path).read()
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing frontmatter")
    head, _, body = text[4:].partition("\n---\n")
    meta = dict(l.split(":", 1) for l in head.splitlines() if ":" in l)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    for k in ("name", "use_when"):
        if not meta.get(k):
            raise ValueError(f"{path}: frontmatter needs '{k}'")
    steps = []
    for section in ("\n" + body).split("\n## ")[1:]:
        sid, _, rest = section.partition("\n")
        step, lines = {"id": sid.strip()}, rest.split("\n")
        while lines and ":" in lines[0] and lines[0].split(":", 1)[0].strip() in KEYS:
            k, v = lines.pop(0).split(":", 1)
            step[k.strip()] = v.strip()
        step["writes_code"] = step.get("writes_code") == "true"
        step.setdefault("gate", "none")
        step["instructions"] = "\n".join(lines).strip()
        steps.append(step)
    desk.validate_steps(steps)
    return {**meta, "steps": steps}


def resolve(name_or_file):
    if os.path.isfile(name_or_file):
        return name_or_file
    return os.path.join(BUREAU, "workflows", name_or_file + ".md")


def start(name_or_file, card_dir):
    path = resolve(name_or_file)
    wf = parse(path)
    steps = [{k: v for k, v in s.items() if k != "instructions"} for s in wf["steps"]]
    desk.init(card_dir, steps, wf["name"])
    dest = os.path.join(card_dir, "workflow.md")  # the run keeps its own copy
    if os.path.abspath(path) != os.path.abspath(dest):
        shutil.copy(path, dest)


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["list"]:
            d = os.path.join(BUREAU, "workflows")
            for f in sorted(os.listdir(d)):
                if f.endswith(".md"):
                    w = parse(os.path.join(d, f))
                    print(f"{w['name']}: {w['use_when']}")
        elif a[:1] == ["show"] and len(a) == 2:
            for s in parse(resolve(a[1]))["steps"]:
                print(s["id"], s["gate"], s.get("persona", "-"), "writes_code" if s["writes_code"] else "")
        elif a[:1] == ["start"] and len(a) == 3:
            start(a[1], a[2])
        else:
            sys.exit(__doc__)
    except (ValueError, FileExistsError) as e:
        sys.exit(f"error: {e}")
