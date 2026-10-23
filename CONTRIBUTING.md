# Contributing

Issues and pull requests are welcome. Bureau is early work and maintained by one person, so replies are best-effort.

- **Branch, don't commit to `main`.** Branch off `main` and open a draft PR. Merging is the maintainer's. Bureau's own runs open their PRs with `scripts/pr.py`; you can open yours by hand.
- **Run the tests** before you push: `python3 -I -m unittest discover -s tests` (no network, a few seconds). `tests/e2e_canary.sh` makes real `claude -p` calls and is only needed after changing a hook.
- **Match the style of recent merged PRs**: a short title, a summary rather than the full case, evidence in a PR comment.
- **`STEPS.md` is the build log.** If your change finishes or adds a step, update its row and say how it was verified.
- **Filing an issue:** see [Contributing and support](README.md#contributing-and-support). Report security problems privately, see [SECURITY.md](SECURITY.md).
