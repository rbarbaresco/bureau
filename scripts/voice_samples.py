#!/usr/bin/env python3
"""Messages the operator typed in past Claude Code sessions, each with the assistant text it answered. /tune-voice reads this.

Usage: voice_samples.py [--sessions N] [--exclude <project-substring>]... [--out <file>]
Reads $CLAUDE_CONFIG_DIR/projects/*/*.jsonl (default ~/.claude), newest N sessions first (default 50), and writes a
markdown extract to --out (default: a new temp file). Prints the path and the sample count. Stays local.
The transcript format is Claude Code's internal one: records it does not recognize are skipped, and zero samples is normal.
"""
import argparse
import glob
import json
import os
import re
import tempfile

BEFORE_CHARS = 1500  # shortcut: keeps the head of a long draft only; raise it if corrections cite its end
NOT_TYPED = ("<", "Another Claude session", "[Request interrupted")  # tags (commands, hooks, bash), relayed and system lines
PASTED = re.compile(r"<pasted_content\b.*?</pasted_content>", re.S)


def _text(content):
    """The plain text of a message's content: a string, or the text blocks of a list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def extract(config_dir, sessions=50, exclude=()):
    files = [f for f in glob.glob(os.path.join(config_dir, "projects", "*", "*.jsonl"))
             if not any(x in os.path.basename(os.path.dirname(f)) for x in exclude)]
    files.sort(key=os.path.getmtime, reverse=True)
    samples = []
    for path in files[:sessions]:
        session = os.path.relpath(path, os.path.join(config_dir, "projects"))[:-len(".jsonl")]
        before = ""
        with open(path, errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    msg = rec.get("message")
                except (ValueError, AttributeError):
                    continue
                if not isinstance(msg, dict):
                    continue
                if rec.get("type") == "assistant":
                    before = _text(msg.get("content")).strip() or before  # a tool-only turn keeps the last text
                elif rec.get("type") == "user" and isinstance(msg.get("content"), str) \
                        and not rec.get("isMeta") and not rec.get("isCompactSummary"):
                    typed = PASTED.sub("[pasted]", msg["content"]).strip()
                    if typed and not typed.startswith(NOT_TYPED):
                        samples.append({"session": session, "before": before[:BEFORE_CHARS], "user": typed})
    return samples


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sessions", type=int, default=50)
    p.add_argument("--exclude", action="append", default=[])
    p.add_argument("--out")
    a = p.parse_args()
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    samples = extract(config, a.sessions, a.exclude)
    out = a.out or tempfile.mkstemp(prefix="voice-samples-", suffix=".md")[1]
    with open(out, "w") as f:
        for s in samples:
            quoted = "\n".join("> " + l for l in s["before"].splitlines()) or "> (none)"
            f.write(f"## {s['session']}\n\nAssistant before:\n{quoted}\n\nOperator:\n{s['user']}\n\n")
    print(f"{out} ({len(samples)} samples)")


if __name__ == "__main__":
    main()
