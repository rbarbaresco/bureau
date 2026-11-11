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
ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)  # what the user typed after a slash command


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0  # vanished or a dangling link: sorted last, then skipped on open


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
    files.sort(key=_mtime, reverse=True)
    samples = []
    for path in files[:sessions]:
        try:
            samples += _read(path, os.path.relpath(path, os.path.join(config_dir, "projects"))[:-len(".jsonl")])
        except OSError:
            continue  # unreadable, or deleted since the glob
    return samples


def _typed(rec, msg):
    """The text the operator typed in this user record, or None for anything they did not type."""
    origin = rec.get("origin")
    if not isinstance(msg.get("content"), str) or rec.get("isMeta") or rec.get("isCompactSummary") \
            or str(rec.get("entrypoint") or "").startswith("sdk-") \
            or (isinstance(origin, dict) and origin.get("kind") != "human"):
        return None  # Agent SDK runs (sdk-cli, sdk-ts, ...), and relayed, notification or injected lines
    text = PASTED.sub("[pasted]", msg["content"]).strip()
    args = ARGS.search(text)
    if args:  # a slash command: its arguments, only when typed (built-ins like /model carry no human origin)
        human = isinstance(origin, dict) and origin.get("kind") == "human"
        text = args.group(1).strip() if human else ""
    return text if text and not text.startswith(NOT_TYPED) else None


def _read(path, session):
    out, before = [], ""
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
            elif rec.get("type") == "user":
                typed = _typed(rec, msg)
                if typed:
                    out.append({"session": session, "before": before[:BEFORE_CHARS], "user": typed})
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sessions", type=int, default=50)
    p.add_argument("--exclude", action="append", default=[])
    p.add_argument("--out")
    a = p.parse_args()
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    samples = extract(config, a.sessions, a.exclude)
    out = a.out
    if not out:
        fd, out = tempfile.mkstemp(prefix="voice-samples-", suffix=".md")
        os.close(fd)
    with open(out, "w") as f:
        for s in samples:
            quoted = "\n".join("> " + l for l in s["before"].splitlines()) or "> (none)"
            f.write(f"## {s['session']}\n\nAssistant before:\n{quoted}\n\nOperator:\n{s['user']}\n\n")
    print(f"{out} ({len(samples)} samples)")


if __name__ == "__main__":
    main()
