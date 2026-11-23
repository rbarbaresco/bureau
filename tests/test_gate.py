import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# commands name LINK, not ROOT: in a card worktree ROOT holds desk/<card>, which the gate owner-checks
LINK = os.path.join(tempfile.mkdtemp(), "bureau")
os.symlink(ROOT, LINK)
sys.path.insert(0, os.path.join(ROOT, "hooks"))
import rules  # noqa: E402
import sessions  # noqa: E402

GATE = os.path.join(ROOT, "hooks", "gate.py")
APPROVE = os.path.join(ROOT, "hooks", "approve.py")
STEPS = [
    {"id": "plan", "gate": "approve"},
    {"id": "build", "gate": "approve", "writes_code": True},
]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # ancestor/ (AGENTS.md) / clone (CLAUDE.md @imports extra.md) ; worktree under desk
        self.clone = os.path.join(self.tmp, "ancestor", "clone")
        write(os.path.join(self.tmp, "ancestor", "AGENTS.md"), "ancestor rule\n")
        write(os.path.join(self.clone, "CLAUDE.md"), "clone rule\n@extra.md\n")
        write(os.path.join(self.clone, "extra.md"), "imported rule\n")
        self.card = os.path.join(self.tmp, "desk", "ABC-1")
        self.wt = os.path.join(self.card, "worktrees", "clone")
        write(os.path.join(self.wt, "CLAUDE.md"), "clone rule\n@extra.md\n")
        write(os.path.join(self.wt, "extra.md"), "imported rule\n")
        write(os.path.join(self.wt, ".git"), f"gitdir: {self.clone}/.git/worktrees/ABC-1\n")
        self.state({"current": "build", "steps": STEPS})

    def state(self, s):
        write(os.path.join(self.card, "state.json"), json.dumps(s))

    def approve(self, *ids):
        write(os.path.join(self.card, "approvals.json"), json.dumps({i: True for i in ids}))

    def ack(self):
        subprocess.run([sys.executable, os.path.join(ROOT, "hooks", "rules.py"), self.wt],
                       check=True, capture_output=True)

    def run_gate(self, tool, cwd=None, **inp):
        payload = {"tool_name": tool, "tool_input": inp, "cwd": cwd or self.card}
        out = subprocess.run([sys.executable, GATE], input=json.dumps(payload),
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if out else None

    def edit(self):
        return self.run_gate("Edit", file_path=os.path.join(self.wt, "app.py"))

    def test_denied_without_approval(self):
        self.ack()
        self.assertIn("'plan' is not approved", self.edit())

    def test_nested_child_is_gated_on_its_own_card(self):
        self.approve("plan")  # the parent card's approval must not open the child
        kid = os.path.join(self.card, "ABC-1-1")
        wt = os.path.join(kid, "worktrees", "clone")
        write(os.path.join(wt, ".git"), "gitdir: x\n")
        write(os.path.join(kid, "state.json"), json.dumps({"current": "build", "steps": STEPS, "parent": "ABC-1"}))
        out = self.run_gate("Edit", file_path=os.path.join(wt, "app.py"))
        self.assertIn("'plan' is not approved", out)

    def test_denied_without_ack(self):
        self.approve("plan")
        self.assertIn("rules.py", self.edit())

    def test_allowed_when_approved_and_acked(self):
        self.approve("plan")
        self.ack()
        self.assertIsNone(self.edit())
        self.assertIsNone(self.run_gate("Bash", command=f"W={self.wt}; touch $W/x"))  # card is not "W=/…"
        self.assertIsNone(self.run_gate("Bash", command=f"git --git-dir={self.wt}/.git commit"))
        self.assertIn("No worktree", self.run_gate("Bash", command=f"touch {self.wt}}}/x"))  # was a crash, i.e. allowed

    def test_stale_ack_after_rule_change(self):
        self.approve("plan")
        self.ack()
        write(os.path.join(self.wt, "extra.md"), "changed rule\n")
        self.assertIn("changed", self.edit())

    def test_no_state_json_names_workflow_start(self):
        os.remove(os.path.join(self.card, "state.json"))
        self.assertIn("workflow.py start", self.edit())

    def test_unknown_current_step_names_reject(self):
        self.state({"current": "zzz", "steps": STEPS})
        self.assertIn("desk.py reject", self.edit())

    def test_corrupt_state_json_is_not_no_workflow(self):
        write(os.path.join(self.card, "state.json"), "{broken")
        reason = self.edit()
        self.assertNotIn("workflow.py start", reason)
        self.assertIn("unreadable", reason)

    def test_non_build_step_denied(self):
        self.state({"current": "plan", "steps": STEPS})
        self.approve("plan")
        self.ack()
        self.assertIn("does not write code", self.edit())

    def test_declared_test_command_allowed_on_non_build_step(self):
        self.state({"current": "plan", "steps": STEPS})
        repos = os.path.join(self.tmp, "repos.yaml")
        write(repos, "repos:\n  clone:\n    path: x\n    test: python3 -I -m unittest\n  other:\n    path: y\n")
        run = f"cd {self.wt} && python3 -I -m unittest discover -s tests 2>&1 | tail -3"
        self.assertIn("does not write code", self.run_gate("Bash", command=run))  # no repos file: today's behaviour
        with mock.patch.dict(os.environ, {"BUREAU_REPOS": repos}):
            self.assertIsNone(self.run_gate("Bash", command=run))
            self.assertIsNone(self.run_gate("Bash", command="python3 -I -m unittest", cwd=self.wt))
            for bad in (f"{run} && rm -rf x", f"{run} > out.txt", f"cd {self.wt} && python3 -I -m unittest $(id)",
                        f"cd {self.wt} && python3 -I -m unittestx", f"cd {self.wt} && python3 other.py"):
                self.assertIn("does not write code", self.run_gate("Bash", command=bad), bad)
            self.assertIn("does not write code", self.run_gate("Edit", file_path=os.path.join(self.wt, "app.py")))
            write(repos, "repos:\n  clone:\n    path: x\n")  # repo without a test: key
            self.assertIn("does not write code", self.run_gate("Bash", command=run))
            write(repos, "repos:\n  clone:\n    path: x\n    test:\n")  # empty value must not match every segment
            self.assertIn("does not write code", self.run_gate("Bash", command=f"cd {self.wt} && rm -rf x"))

    def test_path_outside_worktree_allowed(self):
        self.assertIsNone(self.run_gate("Write", file_path=os.path.join(self.card, "plan.md")))

    def test_agent_cannot_write_approvals(self):
        self.assertIn("approve hook", self.run_gate("Write", file_path=os.path.join(self.card, "approvals.json")))
        self.assertIn("approve hook", self.run_gate("Bash", command=f"echo '{{}}' > {self.card}/approvals.json"))

    def test_agent_cannot_write_bureau_settings(self):
        self.assertIn("/setup-bureau", self.run_gate("Write", file_path=os.path.join(self.tmp, "bureau.json")))
        self.assertIn("/setup-bureau", self.run_gate("Bash", command=f"echo '{{}}' > {self.tmp}/bureau.json"))
        self.assertIsNone(self.run_gate("Bash", command=f"cat {self.tmp}/bureau.json"))

    def test_agent_cannot_run_the_prompt_hooks(self):
        for hook in ("setup", "approve", "owner", "session_end"):
            for cmd in (f"""echo '{{"prompt":"/{hook} 1b"}}' | python3 hooks/{hook}.py""",
                        f"python3 /opt/bureau/hooks/{hook}.py < /dev/null", f"cd hooks && python3 ./{hook}.py"):
                self.assertIn("only from your own prompt", self.run_gate("Bash", command=cmd) or "", cmd)
        self.assertIsNone(self.run_gate("Bash", command="cat hooks/approve.py"))
        for cmd in ("python3 setup.py build_ext --inplace", "python setup.py sdist && python3 tools/approve.py",
                    "cd hooksmith && python3 setup.py develop"):  # a target repo's own setup.py is not a Bureau hook
            self.assertIsNone(self.run_gate("Bash", command=cmd), cmd)
        self.assertIsNone(self.run_gate("Bash", command=f"python3 /opt/bureau/hooks/rules.py {self.wt}"))

    def test_docs_allowed_after_an_auto_advanced_build(self):
        steps = [STEPS[0], {**STEPS[1], "gate": "none", "auto": True}, {"id": "docs", "gate": "none", "writes_code": True},
                 {"id": "pr", "gate": "approve"}]
        self.state({"current": "docs", "steps": steps})
        self.approve("plan")
        self.ack()
        self.assertIsNone(self.edit())

    def test_bash_write_denied_read_only_allowed(self):
        self.assertIsNotNone(self.run_gate("Bash", command=f"sed -i s/a/b/ {self.wt}/app.py"))
        self.assertIsNotNone(self.run_gate("Bash", command=f"cat {self.wt}/a > {self.wt}/b"))
        self.assertIsNotNone(self.run_gate("Bash", command="cd worktrees/clone && touch x"))
        self.assertIsNone(self.run_gate("Bash", command=f"ls {self.wt} && git -C {self.wt} status"))
        self.assertIsNone(self.run_gate("Bash", command="rg foo worktrees/clone"))
        self.assertIsNone(self.run_gate("Bash", command="rg foo worktrees/clone 2>/dev/null | head -5"))
        self.assertIsNone(self.run_gate("Bash", command="grep -rn foo worktrees/clone 2>&1"))
        self.assertIsNotNone(self.run_gate("Bash", command="cat a >/dev/null; touch worktrees/clone/x"))

    def test_done_card_denies_code_changes(self):
        self.state({"current": "done", "steps": STEPS})
        self.approve("plan", "build")
        self.assertIn("Card is done", self.edit())
        self.assertIn("Card is done", self.run_gate("Bash", command=f"cd {self.wt} && git push origin b"))

    def test_followup_after_pr_edits_until_done(self):
        steps = STEPS + [{"id": "pr", "gate": "approve"}, {"id": "followup", "gate": "approve", "writes_code": True}]
        self.state({"current": "followup", "steps": steps})
        self.approve("plan", "build", "pr")
        self.ack()
        self.assertIsNone(self.edit())
        self.state({"current": "done", "steps": steps})
        self.assertIn("Card is done", self.edit())

    def test_read_only_quoted_text(self):
        self.assertIsNone(self.run_gate("Bash", command=f"rg 'a>b' \"<c>\" {self.wt}"))
        self.assertIsNotNone(self.run_gate("Bash", command=f"echo x > {self.wt}/f"))
        self.assertIsNotNone(self.run_gate("Bash", command=f'echo "$(touch {self.wt}/f)"'))

    def test_git_grep_allowed_on_read_only_step(self):
        self.state({"current": "plan", "steps": STEPS})
        self.assertIsNone(self.run_gate("Bash", command=f"git -C {self.wt} grep foo"))

    READS = [
        'grep -n "def \\|class " app.py', "grep -n 'a|b;c&d' app.py | sort -k2 | uniq -c | cut -c1-5 | tr a b | nl",
        "sed -n 40,80p app.py", "sed -n '/^## fix/,/^## docs/p' plan.md", "sed -n '$p' app.py",
        "find . -name '*.py' -type f", "diff a.py b.py", "jq .x f.json", "cat -n app.py", "uniq -c f",
        "awk '{print $1}' app.py", "awk -F: -v n=2 'NR<n' f",
        "git branch", "git branch -a -vv", "git branch --show-current", "git branch --contains HEAD",
        "git fetch origin", "git fetch origin main", "git merge-base HEAD origin/main", "git blame -L 1,5 app.py",
        "git cat-file -p HEAD", "git worktree list", "gh pr view 1 --json title", "gh pr diff 1", "gh pr checks 1",
        "X=/a/b; sed -n 1,5p $X/app.py", 'X="/a b"; ls "$X"',
        "ls # it's fine; really", 'grep -n "a\\"b|c" app.py', "grep a\\|b app.py", "sed -n 1p ./app.py 'b c.py'",
        "uniq -c in", "git branch --merged origin/main",
        "grep -n '^x$' app.py", "git branch -r --merged", "cat <<< x", 'grep -n "can\'t$" app.py',
        "X=/a; git -C $X log", 'X=/a; sed -n 1p "$X/app.py"', "find ${X}/src -name '*.py'",
        "git diff $BASE...HEAD", "git show $SHA:hooks/gate.py", 'git log "${BASE}..HEAD"', "git log HEAD@{1}",
        "find . -name '{a,b}.py'", "git log $A..$B", 'git log "$BASE".."$HEAD"', "git log --author=$USER -S$X",
        "git diff main...HEAD -- hooks/{gate,rules}.py", 'W=/a; git -C "$W" diff', "git -C ${W} log",
    ]
    WRITES = [
        "sed -i s/a/b/ app.py", "sed -n 1p -i app.py", "sed -ni 1p app.py", "sed --in-place 1p app.py",
        "sed -n 'w out' app.py", "sed -n '1e touch x' app.py", "sed -n 1p -f s.sed app.py", "sed s/a/b/w app.py",
        "find . -exec rm {} ;", "find . -execdir rm {} +", "find . -delete", "find . '-delete'", "find . -fprint out",
        "find . -ok rm {} ;", "awk '{print > \"f\"}' app.py", "awk '{print | \"sh\"}' app.py",
        "awk '{system(\"rm x\")}' app.py", "awk -f prog.awk app.py", "awk -i inplace '{print}' app.py",
        "sort -o out f", "sort -uo out f", "sort --output=out f", "uniq in out",
        "git branch new", "git branch -D main", "git branch -m a b", "git fetch origin main:main",
        "git fetch --upload-pack=x origin", "ls | tee out", "echo x > app.py", "cat $(touch x)", "cat `touch x`",
        "X=1 touch app.py", "X=/a; touch $X",
        # QA review of #112: escapes, $'…' and comments must not hide a separator
        "echo \\'; touch app.py; echo \\'", "ls # it's\ntouch app.py\ngit status # don't",
        "echo $'\\'' ; touch app.py ; echo 'z'", 'echo \\" ; touch app.py ; echo "x"',
        "sed -n 1p app.py '-i'", "sed -n 1p app.py ''-i", "sed -n 1p app.py {-i,}", "sed -n $p wiki.md",
        "uniq -- -in -out", "git branch --contains --set-upstream-to=origin/x", "git branch --contains '--unset-upstream'",
        "git fetch --set-upstream origin", "git fetch --stdin origin", "awk '@include \"inplace\"\n1' app.py",
        "cat <(touch x)",
        # QA round 2: heredoc bodies, options split by quotes or a backslash, $'…' operands
        "cat <<ls\nls '\nls\ntouch app.py\nls '", 'cat <<ls\nls "\ntouch app.py\nls "',
        'find . -de""lete', "find . -\\delete", "find . -exe''c rm {} +", "sort f -\\o x", 'sort f -"o" x',
        "git fetch --\"upload-pack\"='touch P; git-upload-pack' .", 'git fetch -""-set-upstream origin',
        "git fetch -\\u origin", "sed -n 1p app.py $'-i'", "sed -n 1p a $'\\x2di'",
        # QA round 3: --no-list or an option value undoes --list; expansions rebuild an option
        "git branch --list --no-list -D newb", "git branch -l --no-l -M a b", "git branch --format -l -D x",
        "git branch --sort -l newb", "find sub -de$@lete", 'find sub -de$""lete', 'sed -n 1p f $"-i"',
        "find .$IFS-delete", "sed -n 1p f ${X:--i}", "uniq a${IFS:0:1}b",
        # QA round 4: braces spell an option; a variable after literal text
        "find sub -{delete,print}", "sort -{o,s} g g", "find sub -{exec,print} rm {} +",
        'find sub "-de"$X', "find sub '-de'$X", 'find sub -de"$X"', 'sed -n 2p f -"$X"',
        "OLDPWD=-delete; find sub ~-", "PWD=-delete; find sub ~+", "PWD=-delete; find sub ~0",
        "git -C {.,commit,--allow-empty,-m} log", "git -C {.,-c,core.fsmonitor=touch${IFS}P} status",
        'X=" commit -m"; git -C .$X log', "git fetch origin a$X", "git branch -{d,D} x",
    ]

    def test_read_only_table(self):
        """Reads pass on a non-writing step, a done card and an intake card; writes do not (#112)."""
        run = lambda c: self.run_gate("Bash", cwd=self.wt, command=c)
        self.state({"current": "plan", "steps": STEPS})
        for c in self.READS:
            self.assertIsNone(run(c), c)
        for c in self.WRITES:
            self.assertIn("does not write code", run(c) or "", c)
        self.state({"current": "done", "steps": STEPS})
        self.assertIsNone(run(self.READS[0]))
        self.assertIn("Card is done", run(self.WRITES[0]))
        os.remove(os.path.join(self.card, "state.json"))
        self.assertIsNone(run(self.READS[0]))
        self.assertIn("no workflow yet", run(self.WRITES[0]))

    def test_declared_test_command_with_quoted_pipe(self):
        self.state({"current": "plan", "steps": STEPS})
        repos = os.path.join(self.tmp, "repos.yaml")
        write(repos, "repos:\n  clone:\n    path: x\n    test: python3 -I -m unittest\n")
        with mock.patch.dict(os.environ, {"BUREAU_REPOS": repos}):
            self.assertIsNone(self.run_gate("Bash", cwd=self.wt, command='python3 -I -m unittest -k "a|b" | tail -3'))

    def test_desk_state_commands_allowed_from_worktree_cwd(self):
        self.state({"current": "plan", "steps": STEPS})
        desk = f"python3 {LINK}/scripts/desk.py"
        run = lambda c: self.run_gate("Bash", cwd=self.wt, command=c)
        self.assertIsNone(run(f"{desk} finish {self.card}"))
        self.assertIsNone(run(f"{desk} reject {self.card} plan 'redo'"))
        self.assertIsNotNone(run(f"{desk} finish {self.card}; touch {self.wt}/x"))
        self.assertIsNotNone(run(f"{desk} finish {self.card} > {self.wt}/x"))
        self.assertIsNotNone(run(f"{desk} init {self.wt}/sub '[]'"))  # argument points into a worktree
        self.assertIsNone(run(f"{desk} reject {self.card} plan 'redo; see worktrees/x & more'"))  # free text
        self.assertIsNotNone(run(f"{desk} init . '[]'"))  # "." is the worktree
        self.assertIsNotNone(run(f"{desk} finish $PWD"))
        self.assertIsNotNone(run(f"{desk} finish {self.card}\ntouch {self.wt}/x"))  # newline = second command
        self.assertIsNotNone(run(f"{desk} finish c# ; touch {self.wt}/x"))  # mid-word # is not a comment
        self.assertIsNotNone(run(f"{desk} init {{{self.wt}/x,y}} '[]'"))  # brace expansion
        self.assertIsNotNone(run(f"{desk} finish {self.card[:-1]}?"))  # glob
        self.assertIsNone(self.run_gate("Bash", cwd=ROOT, command=f"python3 scripts/desk.py finish {self.card}"))
        self.assertIsNotNone(run(f'{desk} reject {self.card} plan "$(touch {self.wt}/x)"'))
        self.assertIsNotNone(run(f"{desk} revise {self.card} `touch {self.wt}/x`"))
        self.assertIsNotNone(run(f"{desk} $UNSET init {self.wt}/sub '[]'"))  # shifts the card argument
        self.assertIsNone(run(f"{desk} revise {self.card} 'line1\nline2'"))  # newline inside quotes is inert
        self.assertIsNotNone(run(f"{desk} list /c #'\ntouch {self.wt}/x #'"))  # comment hides a quote pair
        self.assertIsNotNone(run(f"python3 -Wx/../scripts/desk.py list {self.card}"))  # python option, not the script
        other = os.path.join(self.tmp, "other", "scripts", "desk.py")  # unrelated project's desk.py
        write(other, "")
        self.assertIsNotNone(run(f"python3 {other} finish {self.card}"))

    def test_rules_loader_runs_before_ack(self):
        cmd = f"python3 {LINK}/hooks/rules.py {self.wt}"
        self.assertIsNone(self.run_gate("Bash", command=cmd))

    def test_subagent_call_gated_too(self):
        payload = {"tool_name": "Edit", "agent_id": "a1", "cwd": self.card,
                   "tool_input": {"file_path": os.path.join(self.wt, "app.py")}}
        out = subprocess.run([sys.executable, GATE], input=json.dumps(payload),
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("deny", out)

    def test_resolver_collects_ancestors_and_imports(self):
        names = [os.path.relpath(p, self.tmp) for p in rules.collect(self.wt) if p.startswith(self.tmp)]
        self.assertIn("ancestor/AGENTS.md", names)
        self.assertTrue(any(n.endswith("clone/extra.md") for n in names))

    def test_resolver_includes_bureau_base_rules(self):
        self.assertIn(os.path.join(ROOT, "AGENTS.md"), rules.collect(self.wt))

    def test_approve_hook_records_awaiting_step(self):
        desk = os.path.join(self.tmp, "desk")  # setUp's ABC-1 is not awaiting, so only TEST-APPROVE matches
        card = os.path.join(desk, "TEST-APPROVE")
        write(os.path.join(card, "state.json"), json.dumps({"awaiting": "plan", "steps": STEPS}))
        env = {**os.environ, "BUREAU_DESK": desk}
        sessions.append(card, "claim", "s1", os.getpid())  # bare /approve needs the caller to own the card
        run = lambda prompt: subprocess.run([sys.executable, APPROVE], input=json.dumps({"prompt": prompt, "session_id": "s1"}),
                                            capture_output=True, text=True, env=env).stdout
        self.assertEqual(run("hello"), "")
        for prompt in ("/approve TEST-APPROVE", "/approve"):
            out = run(prompt)
            self.assertIn("approved step 'plan'", out)
            self.assertIn("card=TEST-APPROVE", out.split())
        with open(os.path.join(card, "approvals.json")) as f:
            self.assertEqual(json.load(f), {"plan": True})
        # `done` on a non-looping step is ignored: a plain approval
        for prompt in ("/approve done", "/approve TEST-APPROVE done"):
            self.assertIn("approved step 'plan'", run(prompt))
            with open(os.path.join(card, "approvals.json")) as f:
                self.assertEqual(json.load(f), {"plan": True})
        # on a looping step: bare /approve approves a round, `done` ends the loop
        write(os.path.join(card, "state.json"), json.dumps(
            {"awaiting": "rounds", "steps": [{"id": "rounds", "gate": "approve", "loop": True}]}))
        for prompt, value, says in (("/approve", True, "round"), ("/approve done", "done", "loop ended"),
                                    ("/approve TEST-APPROVE done", "done", "loop ended"),
                                    ("/approve done TEST-APPROVE", "done", "loop ended"),
                                    ("/approve done done", "done", "loop ended"),
                                    ("/approve done\nthanks", "done", "loop ended"),  # only the /approve line counts
                                    ("/approve\ndone", True, "round")):
            out = run(prompt)
            self.assertIn(says, out, prompt)
            self.assertIn("card=TEST-APPROVE", out.split())
            with open(os.path.join(card, "approvals.json")) as f:
                self.assertEqual(json.load(f)["rounds"], value, prompt)

    def test_ungated_docs_step_edits_only_after_build_approved(self):
        steps = STEPS + [{"id": "docs", "gate": "none", "writes_code": True}]
        self.state({"current": "docs", "steps": steps})
        self.approve("plan")
        self.ack()
        self.assertIn("'build' is not approved", self.edit())
        self.approve("plan", "build")
        self.assertIsNone(self.edit())

    def test_later_code_step_allowed_after_loop_done(self):
        self.state({"current": "build", "steps": [{"id": "plan", "gate": "approve", "loop": True}, STEPS[1]]})
        write(os.path.join(self.card, "approvals.json"), json.dumps({"plan": "done"}))
        self.ack()
        self.assertIsNone(self.edit())

    def test_later_code_step_denied_while_loop_only_has_a_round_approved(self):
        self.state({"current": "build", "steps": [{"id": "plan", "gate": "approve", "loop": True}, STEPS[1]]})
        self.approve("plan")  # a round approval (true), not the end of the loop
        self.ack()
        self.assertIn("/approve done", self.edit())


if __name__ == "__main__":
    unittest.main()
