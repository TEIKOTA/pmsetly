#!/usr/bin/env python3
"""guard-bash.py の ask の絞り込み（#158）の test。

- 一時領域の中の rm -rf は確認なしで通り、ルート・展開・..・外・symlink 越しは確認になる
- `cd <別の checkout> && git push` は、移動先の branch で判定する（移動先が main でなければ確認にならない）

guard を実プロセスで起こし、hook の入力 JSON を stdin へ渡して判定（ask / allow / deny）を見る。
HOME は存在しない dir に差し替え、実際の ~/.trashable・実 repo には触れない。

--mutation は保護を 1 つ外した guard をコピーして作り、対応する --case が red になることを示す。
実装ファイルは変更しない。注入先が 1 か所に決まらなければ exit 3（保護の喪失の red = exit 1 と区別する）。
"""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/hooks/guard-bash.py"
FAKE_HOME = "/nonexistent-guard-home"
OUTSIDE_TEMP = Path("/usr")  # 一時領域の外の実在 dir。相対 path の rm -rf を ask にしたい test の基準（#170）

MUTATIONS = {
    "root": [("path.startswith(root.rstrip(os.sep) + os.sep)", "path.startswith(root.rstrip(os.sep))")],
    "expansion": [('if not target or "\\0" in target or any(char in target for char in EXPANSION_CHARS):', "if not target:")],
    "dotdot": [('".." in path.split("/")', "False")],
    "parentreal": [('if not inside_temp(parent.rstrip("/") + "/x", [real for _, real in rm_temp_roots()]):', "if False:")],
    "trailing": [("return not (trailing and os.path.islink(path))", "return True")],
    "realroot": [("if real == os.sep or home == real or home.startswith(real + os.sep):", "if False:")],
    "longopt": [("            if arg not in RM_LONG_OPTIONS:\n                return None\n", "            pass\n")],
    "shortopt": [("            if not set(arg[1:]) <= RM_SHORT_OPTIONS:\n                return None\n", "            pass\n")],
    "notes": [("base = None if notes else followed", "base = followed")],
    "tilde": [('tilde_ok = "HOME" not in folded', "tilde_ok = True")],
    "quoted": [("tilde_ok and not quoted", "tilde_ok")],
    "hint": [("~/.trashable/<repo>/", "")],
    "cdfollow": [("followed = leading_cwd(command, start_cwd)", "followed = start_cwd")],
    "cdcount": [("followed != total or ", "")],
    "cdisdir": [("followed != total or not cwd or not os.path.isdir(cwd)", "followed != total or not cwd")],
    "cdpipe": [("or has_non_sequential_operator(outer)", "")],
    "cdsubst": [("outer.strip() != text.strip() or ", "")],
    "subst": [("not any(mark in folded for mark in (\"$(\", \"`\", \"<(\", \">(\"))", "True")],
    "lnmv": [(" and not LN_MV_RE.search(folded)", "")],
    "except": [("            except Exception:\n                pass  # 判定できない", "            except ZeroDivisionError:\n                pass  # 判定できない")],
    "fold": [("    text = fold_continuations(mask_heredoc_bodies(text))\n", "    text = mask_heredoc_bodies(text)\n")],
    "foldmain": [("    folded = fold_continuations(command)\n", "    folded = command\n")],
    "foldquote": [('            if not quote and text[index + 1 : index + 2] == "\\n":', '            if text[index + 1 : index + 2] == "\\n":')],
    "ansic": [("            ansi_c = char == \"'\" and folded[-1:] == [\"$\"]\n", "")],
    "pollwatch": [("def has_polling(groups):\n    for group in groups:\n", "def has_polling(groups):\n    if any(\"--watch\" in segment for group in groups for segment in group):\n        return True\n    for group in groups:\n")],
    "pollsleep": [('            if next_name == "gh" and following[1:3] == ["pr", "checks"]:\n                return True\n', '')],
    "pollloop": [('            if in_loop and command_name(tokens) == "sleep":\n                return True\n', '')],
    "gitcwd": [("git_cwd = cwd if notes or not followed or followed == start_cwd else followed", "git_cwd = cwd")],
    # #250: git worktree remove の自動判定と ask の記録
    "wtclean": [("    if status is None or status.strip():\n", "    if status is None:\n")],
    "wtignored": [('"--untracked-files=all", "--ignored")', '"--untracked-files=all")')],
    "wtpushed": [("    for base in bases:\n", "    return True\n    for base in bases:\n")],
    "wtremote": [('    if upstream and upstream.strip().startswith("refs/remotes/"):\n', "    if upstream:\n")],
    "wtoption": [("    args = git_args[1:]\n", '    args = [arg for arg in git_args[1:] if not arg.startswith("-")]\n')],
    "wtsingle": [("        single = len(primary_segments) == 1\n", "        single = True\n")],
    "wtsubst": [('    if not single or any(mark in folded for mark in ("$(", "`", "<(", ">(")):\n', "    if not single:\n")],
    "wtmain": [("        return False  # main worktree", "        pass  # main worktree")],
    "asklog": [('            handle.write("\\t".join(fields) + "\\n")\n', "            pass\n")],
    "asklogfail": [("    except Exception:\n        pass\n\n\ndef ask(", "    except ZeroDivisionError:\n        pass\n\n\ndef ask(")],
    "wtreflog": [("    if commits:\n", "    if False:\n")],
    "wtreflimit": [("    if len(commits) > WORKTREE_REFLOG_LIMIT:\n", "    if False:\n")],
    "wtworktreeref": [('    extra = run_git(path, "for-each-ref", "--format=%(objectname)", "refs/worktree/", "refs/bisect/")\n', '    extra = ""\n')],
    "wtoldgit": [("    if len(git_dirs) != 2 or not all(os.path.isabs(entry) for entry in git_dirs):\n        return False\n", "")],
    "wtquotedtilde": [(""" or any(char in segment for char in "'\\"\\\\"):\n            return None\n        path = os.path.expanduser""",
                       """:\n            return None\n        path = os.path.expanduser""")],
    "wthome": [('if not path.startswith("~/") or "HOME" in folded or', 'if not path.startswith("~/") or'),
               ('    if shlex_words(segment)[:1] != ["git"] or tokens[:1] != ["git"]:\n', '    if tokens[:1] != ["git"]:\n')],
    "wtexpand": [('    if not path or "\\0" in path or any(char in path for char in EXPANSION_CHARS):\n', '    if not path or "\\0" in path:\n')],
    "wtprefix": [('    if shlex_words(segment)[:1] != ["git"] or tokens[:1] != ["git"]:\n', '    if tokens[:1] != ["git"]:\n')],
    "wtgitenv": [('if not key.startswith("GIT_")}', "if True}")],
    "wtcexpand": [("        if index + 1 >= len(tokens) or any(char in tokens[index + 1] for char in EXPANSION_CHARS):\n            return None", "        if False:\n            return None")],
    "asklogfifo": [("        if os.path.exists(path) and not os.path.isfile(path):\n            return", "        if False:\n            return")],
    "askhint": [("merge 済みの topic branch は scripts/merge-pr.sh が先端と head の SHA の一致で自動で消す（#227）", "対象を確認する")],
}
CASES = {
    "root": "test_rm_root_itself_asks",
    "expansion": "test_rm_expansion_asks",
    "dotdot": "test_rm_dotdot_asks",
    "parentreal": "test_rm_symlinked_parent_asks",
    "trailing": "test_rm_trailing_slash_symlink_asks",
    "realroot": "test_rm_wide_tmpdir_is_not_a_root",
    "longopt": "test_rm_unknown_option_asks",
    "shortopt": "test_rm_unknown_option_asks",
    "notes": "test_rm_relative_with_chdir_wrapper_asks",
    "tilde": "test_rm_tilde_with_home_override_asks",
    "quoted": "test_rm_quoted_tilde_asks",
    "hint": "test_rm_ask_points_to_trashable",
    "cdfollow": "test_push_follows_cd_to_non_main",
    "cdcount": "test_push_unfollowable_cd_falls_back",
    "cdisdir": "test_push_unfollowable_cd_falls_back",
    "cdpipe": "test_push_unfollowable_cd_falls_back",
    "cdsubst": "test_push_cd_target_substitution_falls_back",
    "subst": "test_rm_with_substitution_asks",
    "lnmv": "test_rm_with_ln_or_mv_asks",
    "except": "test_rm_judgement_error_asks",
    "gitcwd": "test_push_follows_cd_to_non_main",
    "pollwatch": "test_ci_watch_at_head_is_allowed",
    "pollsleep": "test_ci_watch_after_sleep_is_denied",
    "pollloop": "test_sleep_loop_is_denied",
    "fold": "test_continuation_is_folded",
    "foldmain": "test_continuation_splitting_ln_or_mv_asks",
    "foldquote": "test_continuation_inside_quotes_is_kept",
    "ansic": "test_continuation_after_ansi_c_quote_is_kept",
    "wtclean": "test_worktree_remove_dirty_asks",
    "wtignored": "test_worktree_remove_with_ignored_file_asks",
    "wtpushed": "test_worktree_remove_unpushed_asks",
    "wtremote": "test_worktree_remove_local_upstream_asks",
    "wtoption": "test_worktree_remove_unjudgeable_form_asks",
    "wtsingle": "test_worktree_remove_unjudgeable_form_asks",
    "wtsubst": "test_worktree_remove_unjudgeable_form_asks",
    "wtmain": "test_worktree_remove_main_worktree_asks",
    "asklog": "test_ask_is_logged_without_command_text",
    "asklogfail": "test_ask_log_failure_keeps_decision",
    "askhint": "test_ask_reason_says_what_can_be_lost",
    "wtreflog": "test_worktree_remove_unpushed_asks",
    "wtreflimit": "test_worktree_remove_reflog_limit_asks",
    "wtworktreeref": "test_worktree_remove_unpushed_asks",
    "wtoldgit": "test_worktree_remove_main_worktree_asks",
    "wtquotedtilde": "test_worktree_remove_tilde",
    "wthome": "test_worktree_remove_tilde",
    "wtexpand": "test_worktree_remove_glob_named_dir_asks",
    "wtprefix": "test_worktree_remove_env_prefix_asks",
    "wtgitenv": "test_worktree_remove_hook_git_env_is_ignored",
    "wtcexpand": "test_worktree_remove_unjudgeable_form_asks",
    "asklogfifo": "test_ask_log_failure_keeps_decision",
}
parser = argparse.ArgumentParser()
parser.add_argument("--mutation", choices=sorted(MUTATIONS))
parser.add_argument("--case", choices=sorted(CASES))
arguments = parser.parse_args()

source = GUARD.read_text()
if arguments.mutation:
    for needle, replacement in MUTATIONS[arguments.mutation]:
        if source.count(needle) != 1:
            print("regression injection target changed: %r" % needle[:60], file=sys.stderr)
            sys.exit(3)
        source = source.replace(needle, replacement)

WORK = Path(tempfile.mkdtemp(prefix="guard-ask-"))
(WORK / "guard-bash.py").write_text(source)
# 判定の関数が例外を出す guard（N3 の確認用。注入済みの source から作る）。注入先が 1 か所でなければ exit 3
_fault_re = re.compile(r"^    if not target", re.M)
if len(_fault_re.findall(source)) != 1:
    print("fault injection target changed", file=sys.stderr)
    sys.exit(3)
(WORK / "guard-fault.py").write_text(_fault_re.sub('    raise ValueError("fault")\n    if not target', source, count=1))
FX = WORK / "fx"
MAIN = WORK / "main-repo"
FEAT = WORK / "feat-repo"
FX.mkdir()
(FX / "link").symlink_to("/usr")
(FX / "plain").mkdir()
for repo, branch in ((MAIN, "main"), (FEAT, "feat/1-x")):
    subprocess.run(["git", "init", "-q", "-b", branch, str(repo)], check=True)


# git worktree remove の自動判定（#250）の fixture。origin（bare）へ main を push し、状態の違う linked worktree を並べる
# 一時領域の worktree を取り消す post-checkout の guard（setup-user-hooks.sh --git）を、この fixture でだけ外す
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid", PROJECT_TEMPLATE_ALLOW_TMP_WORKTREE="1")
ORIGIN = WORK / "origin.git"
REPO = WORK / "wt-repo"
WT = {name: WORK / ("wt-" + name) for name in
      ("merged", "pushed", "unpushed", "localup", "dirty", "modified", "ignored", "detached", "detachedahead",
       "detachedleft", "wtref", "glob[1]")}


def git(*args, cwd=REPO):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, env=GIT_ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(ORIGIN)], check=True)
subprocess.run(["git", "init", "-q", "-b", "main", str(REPO)], check=True)
(REPO / ".gitignore").write_text("*.log\n")
(REPO / "a.txt").write_text("a\n")
git("add", ".")
git("commit", "-q", "-m", "init")
git("remote", "add", "origin", str(ORIGIN))
git("push", "-q", "origin", "main")
git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
for name in ("merged", "pushed", "unpushed", "localup", "dirty", "modified", "ignored", "wtref", "glob[1]"):
    git("worktree", "add", "-q", "-b", re.sub(r"[][]", "", name), str(WT[name]), "main")
for name in ("detached", "detachedahead", "detachedleft"):
    git("worktree", "add", "-q", "--detach", str(WT[name]), "main")
for name in ("pushed", "unpushed", "localup", "detachedahead", "detachedleft", "wtref"):
    git("commit", "-q", "--allow-empty", "-m", name, cwd=WT[name])
git("push", "-q", "-u", "origin", "pushed", cwd=WT["pushed"])
git("branch", "localbase", "localup")
git("branch", "--set-upstream-to=localbase", "localup", cwd=WT["localup"])
# review B1: detached HEAD で作った commit から離れた（reflog にだけ残る）、refs/worktree/* にだけ残る（HEAD の reflog は消す）
git("checkout", "-q", "--detach", "main", cwd=WT["detachedleft"])
git("update-ref", "refs/worktree/keep", "HEAD", cwd=WT["wtref"])
git("reset", "-q", "--hard", "main", cwd=WT["wtref"])
# HEAD が branch wtref を指すと git log -g HEAD は branch の reflog を返すので、branch の reflog も消す（#256）
git("reflog", "expire", "--expire=now", "--expire-unreachable=now", "HEAD", "refs/heads/wtref", cwd=WT["wtref"])
# 前提の固定: reflog は空で、wtref の commit を指すのは refs/worktree/keep だけ（reflog 側の検査で ask にならない）
_wtref_reflog = subprocess.run(["git", "-C", str(WT["wtref"]), "log", "-g", "--format=%H", "HEAD"], check=True, env=GIT_ENV,
                               capture_output=True, text=True).stdout
if _wtref_reflog.strip():
    print("fixture wtref: HEAD の reflog が空にならない: %r" % _wtref_reflog, file=sys.stderr)
    sys.exit(3)
# review N1: --path-format=absolute を知らない旧い git（< 2.31）は未知の option をそのまま echo する。それを模す wrapper
OLD_GIT = WORK / "old-git"
OLD_GIT.mkdir()
(OLD_GIT / "git").write_text(
    "#!%s\nimport os, sys\nargs = sys.argv[1:]\nif '--path-format=absolute' in args:\n"
    "    print('--path-format=absolute', flush=True)\n    args = [arg for arg in args if arg != '--path-format=absolute']\n"
    "os.execv(%r, [%r] + args)\n" % (sys.executable, shutil.which("git"), "git"))
(OLD_GIT / "git").chmod(0o755)
(WT["dirty"] / "new.txt").write_text("x\n")
(WT["modified"] / "a.txt").write_text("changed\n")
(WT["ignored"] / "out.log").write_text("x\n")


def decide(command, cwd=None, env=None, script="guard-bash.py", timeout=None):
    """guard の判定: deny（exit 2）/ ask / allow。理由の文面も返す。"""
    environment = {key: value for key, value in os.environ.items() if key != "TMPDIR"}
    environment.update({"HOME": FAKE_HOME, "PYTHONDONTWRITEBYTECODE": "1"})
    environment.update(env or {})
    payload = {"tool_input": {"command": command}, "cwd": str(cwd or ROOT)}
    done = subprocess.run(
        [sys.executable, str(WORK / script)], input=json.dumps(payload),
        text=True, capture_output=True, env=environment, check=False, timeout=timeout,
    )
    if done.returncode == 2:
        return "deny", done.stderr
    if done.stdout.strip():
        output = json.loads(done.stdout)["hookSpecificOutput"]
        return output["permissionDecision"], output["permissionDecisionReason"]
    return "allow", ""


class Base(unittest.TestCase):
    def allows(self, command, cwd=None, env=None):
        self.assertEqual(decide(command, cwd, env)[0], "allow", command)

    def asks(self, command, cwd=None, env=None):
        self.assertEqual(decide(command, cwd, env)[0], "ask", command)


class RmTemporary(Base):
    def test_rm_inside_temporary_roots_is_allowed(self):
        tmpdir = {"TMPDIR": "/nonexistent-guard-tmp/T"}
        for command in (
            "rm -rf /tmp/x", "rm -rf /private/tmp/x/y", "rm -fr /tmp/x", "rm -r -f /tmp/x", "rm --recursive --force /tmp/x",
            "rm -rfv /tmp/x", "rm -rf -- /tmp/x", "rm -rf /tmp/x /tmp/y", "rm -rf /tmp/x/", "rm -rf ~/.trashable/repo/x",
            "rm -rf ~/.trashable/x", "rm -rf /nonexistent-guard-tmp/T/x", "rm -rf /var/folders/ab/cd/T/x",
            "rm -rf /private/var/folders/ab/cd/T/x/y", "sudo rm -rf /tmp/x", "env FOO=1 rm -rf /tmp/x", "rm /tmp/x -rf",
            "bash -c 'rm -rf /tmp/x'", "ls && rm -rf /tmp/x 2>&1", "rm -rf /tmp/with\\ space/x", f"rm -rf {FX}/link",
        ):
            self.allows(command, env=tmpdir)

    def test_rm_relative_is_judged_by_cwd(self):
        self.allows("rm -rf plain", cwd=FX)
        self.allows(f"cd {FX} && rm -rf plain")
        self.allows(f"cd {FX}; cd plain; rm -rf x")
        # repo が一時領域の下にあっても ask を確かめられるよう、一時領域の外の実在 dir を基準にする（#170）
        self.asks("rm -rf plain", cwd=OUTSIDE_TEMP)

    def test_rm_root_itself_asks(self):
        tmpdir = {"TMPDIR": "/nonexistent-guard-tmp/T"}
        for command in (
            "rm -rf /tmp", "rm -rf /tmp/", "rm -rf /tmp/.", "rm -rf /private/tmp", "rm -rf ~/.trashable", "rm -rf ~/.trashable/",
            # /tmpfoo/x は macOS では /tmp の実体が /private/tmp のため親の実体の判定でも止まる。字面の判定だけを
            # 確かめる /private/tmpfoo/x を併せて置く（どちらの OS でも root の保護を外すと red になる）
            "rm -rf ~", "rm -rf /tmpfoo/x", "rm -rf /private/tmpfoo/x", "rm -rf /nonexistent-guard-tmp/T", "rm -rf /nonexistent-guard-tmp",
            "rm -rf /var/folders/ab/cd/T", "rm -rf /private/var/folders/ab/cd/T/", "rm -rf /var/folders/ab/cd",
        ):
            self.asks(command, env=tmpdir)

    def test_rm_outside_asks(self):
        for command in ("rm -rf /etc/x", "rm -rf /", "rm -rf /home/x", "rm -rf /tmp/x /etc/x", "rm -rf /etc/x /tmp/x",
                        "rm -rf", "bash -c 'rm -rf /etc/x'", "eval 'rm -rf /etc/x'", "rm -Rf /etc/x", "rm -rf /tmp/x; rm -rf /etc/x"):
            self.asks(command)

    def test_rm_expansion_asks(self):
        for command in ("rm -rf /tmp/*", "rm -rf /tmp/x*", "rm -rf /tmp/?", "rm -rf /tmp/[ab]", "rm -rf /tmp/{a,b}",
                        "rm -rf /tmp/$X", "rm -rf $TMPDIR/x", "rm -rf ${TMPDIR}/x", "rm -rf /tmp/$(echo a)", "rm -rf /tmp/`echo a`",
                        "rm -rf ~root/x", "rm -rf ~+/x", "rm -rf ~/.trashable/*"):
            self.asks(command, env={"TMPDIR": "/nonexistent-guard-tmp/T"})

    def test_rm_dotdot_asks(self):
        for command in ("rm -rf /tmp/../tmp/x", "rm -rf /tmp/x/../y", "rm -rf /tmp/x/..", "rm -rf /tmp/../etc", "rm -rf ~/.trashable/../x",
                        "rm -rf ~/../tmp/x"):
            self.asks(command)
        self.asks("rm -rf ../x", cwd=FX / "plain")

    def test_rm_symlinked_parent_asks(self):
        self.asks(f"rm -rf {FX}/link/bin")
        self.asks(f"rm -rf {FX}/link/bin/x")
        self.asks(f"rm -rf {FX}/link/*")
        self.asks(f"cd {FX} && rm -rf link/bin")

    def test_rm_trailing_slash_symlink_asks(self):
        self.asks(f"rm -rf {FX}/link/")
        self.asks(f"rm -rf {FX}/link/.")
        self.allows(f"rm -rf {FX}/plain/")

    def test_rm_wide_tmpdir_is_not_a_root(self):
        # TMPDIR が / や HOME を覆う dir だと、一時領域の外まで通ってしまう
        self.asks("rm -rf /etc/x", env={"TMPDIR": "/"})
        self.asks("rm -rf /nonexistent-guard-home/x", env={"TMPDIR": FAKE_HOME})
        self.asks("rm -rf /nonexistent-guard-home/x", env={"TMPDIR": "/nonexistent-guard-home"})
        self.asks("rm -rf /nonexistent-guard-home/x", env={"TMPDIR": "/"})

    def test_rm_unknown_option_asks(self):
        for command in ("rm -rf --no-preserve-root /tmp/x", "rm -rfi /tmp/x", "rm -rf -P /tmp/x", "rm -rf --interactive /tmp/x",
                        "rm -rf --bogus /tmp/x"):
            self.asks(command)

    def test_rm_relative_with_chdir_wrapper_asks(self):
        self.asks("env -C /etc rm -rf plain", cwd=FX)
        self.asks("sudo -D /etc rm -rf plain", cwd=FX)

    def test_rm_relative_after_unfollowed_cd_asks(self):
        for command in ("echo a; cd /etc; rm -rf plain", "if true; then cd /etc; rm -rf plain; fi", "cd /etc | rm -rf plain",
                        "(cd /etc; rm -rf plain)", "eval 'cd /etc'; rm -rf plain", "cd $X && rm -rf plain", "cd - && rm -rf plain",
                        "cd /nonexistent-guard-dir && rm -rf plain"):
            self.asks(command, cwd=FX)

    def test_rm_tilde_with_home_override_asks(self):
        self.asks("export HOME=/etc; rm -rf ~/.trashable/x")
        self.asks("HOME=/etc rm -rf ~/.trashable/x")

    def test_rm_quoted_tilde_asks(self):
        # 引用符の中の ~ は展開されず、cwd 直下の "~" という名前の dir になる
        self.asks('rm -rf "~/.trashable/x"')
        self.asks("rm -rf '~/.trashable/x'")
        self.asks("rm -rf ~/.trashable/x\\ y")

    def test_rm_with_substitution_asks(self):
        for command in ("rm -rf $(echo /etc) /tmp/x", "rm -rf /tmp/x/$(echo ../../etc)", "rm -rf /tmp/x <(echo /etc)", "rm -rf /tmp/x `pwd`",
                        "rm -rf /tmp/x >(cat)", "bash -c 'rm -rf /tmp/x $(echo /etc)'", "eval 'rm -rf /tmp/x `pwd`'", "rm -rf /tmp/x$(echo)",
                        "echo $(true); rm -rf /tmp/x"):
            self.asks(command)

    def test_rm_with_ln_or_mv_asks(self):
        for command in ("ln -s / /tmp/l && rm -rf /tmp/l/etc", "mv /tmp/a /tmp/b; rm -rf /tmp/b/x", "ln -sfn /etc /tmp/l; rm -rf /tmp/l/x"):
            self.asks(command)

    def test_continuation_is_folded(self):
        # 行末の backslash＋改行（引用の外）は shell が読む前に畳む。path の直後・名前の途中・sudo / bash -c の中でも確認になる（#166）
        for command in ("rm -rf /etc\\\n", "rm -rf /etc/x\\\n", "r\\\nm -rf /etc", "rm\\\n -rf /etc", "rm -rf /e\\\ntc",
                        "sudo rm -rf /etc\\\n", "sudo r\\\nm -rf /etc", "bash -c 'rm -rf /etc\\\n'", "bash -c 'r\\\nm -rf /etc'",
                        "eval 'r\\\nm -rf /etc'", "echo a; r\\\nm -rf /etc", "rm -rf \\\n/etc/x", "rm -rf /tmp/x /etc\\\n"):
            self.asks(command)
        # 継続で割っても一時領域の中は通る。backslash 自身の後の改行は継続でなく、別の command になる
        self.allows("rm -rf /tmp/x\\\n", env={"TMPDIR": "/nonexistent-guard-tmp/T"})
        self.allows("r\\\nm -rf /tmp/x")
        self.asks("echo a\\\\\nrm -rf /etc")

    def test_continuation_splitting_ln_or_mv_asks(self):
        for command in ("l\\\nn -s / /tmp/l && rm -rf /tmp/l/etc", "ln -s / /tmp/l && r\\\nm -rf /tmp/l/etc", "m\\\nv /tmp/a /tmp/b; rm -rf /tmp/b/x",
                        "echo $\\\n(true); rm -rf /tmp/x"):
            self.asks(command)

    def test_continuation_inside_quotes_is_kept(self):
        # 引用の中の backslash＋改行は文字列の一部。畳まない（畳むと path が /tmp/x に変わり確認が消える）
        self.asks("rm -rf '/tm\\\np/x'")
        self.asks("rm -rf \"/tm\\\np/x\"")
        # 引用の中の継続があっても、ほかの判定（secret・worktree・polling・ask）は変わらない
        for command in ("echo 'cat .env\\\n'", "git commit -m 'a\\\nb'", "echo 'while true; do sleep 1; done\\\n'",
                        "echo 'git worktree add /tmp/wt x\\\n'", "echo 'rm -rf /etc\\\n'", "echo \"git push --force\\\n\"",
                        "# note \\\nx"):
            self.allows(command, cwd=FEAT)
        for command in ("cat .env 'a\\\nb'", "git worktree add /tmp/wt 'a\\\nb'", "cat\\\n .env", "while true; do sleep\\\n 1; done"):
            self.assertEqual(decide(command, cwd=FEAT)[0], "deny", command)
        self.asks("git push --force 'a\\\nb'", cwd=FEAT)

    def test_continuation_after_ansi_c_quote_is_kept(self):
        # $'it\\'s' は \\' で閉じない。閉じたと取り違えると後ろの引用の開閉が反転し、引用の中の継続が畳まれて確認が消える（#166 の review B1）
        for command in ("echo $'it\\'s' ; rm -rf '/tm\\\np/x'", "echo $'it\\'s'; rm -rf '/tm\\\np/x'", "echo $'a\\\\'; rm -rf '/tm\\\np/x'",
                        "echo $'x\\\ny'; rm -rf /etc\\\n"):
            self.asks(command)
        self.allows("echo $'a\\\nb' ; echo 'x'", cwd=FEAT)
        self.allows("echo \"$'\" ; rm -rf /tmp/x\\\n")

    def test_rm_judgement_error_asks(self):
        # 判定の関数が例外を出しても落ちずに確認する（静的な規則を外したので、判定できなければ確認、の前提）
        self.assertEqual(decide("rm -rf /tmp/x", script="guard-fault.py")[0], "ask")
        self.assertEqual(decide("rm -rf /tmp/x /etc/x", script="guard-fault.py")[0], "ask")
        self.asks("rm -rf '/tmp/a\x00b'")

    def test_rm_ask_points_to_trashable(self):
        decision, reason = decide("rm -rf /etc/x")
        self.assertEqual(decision, "ask")
        self.assertIn("~/.trashable/<repo>/", reason)
        self.assertIn("確認なしで消せる", reason)

    def test_other_asks_are_kept(self):
        for command in ("git push --force", "git push origin main", "git push origin HEAD:main", "git reset --hard", "git clean -fd",
                        "git checkout -- .", "git branch -D topic", "git worktree remove x", "git worktree prune", "git worktree move a b",
                        "gh pr close 1", "gh repo delete o/r", "ssh host ls"):
            self.asks(command, cwd=FEAT)

    def test_deny_is_unchanged(self):
        for command in ("cat .env", "git worktree add /tmp/wt x", "while true; do sleep 1; done"):
            self.assertEqual(decide(command, cwd=FEAT)[0], "deny", command)


class WorktreeRemove(Base):
    """git worktree remove は clean かつ HEAD の先端が origin/main か upstream に含まれるときだけ確認なしで通す（#250）."""

    def test_worktree_remove_merged_or_pushed_is_allowed(self):
        for name in ("merged", "pushed", "detached"):
            self.allows(f"git worktree remove {WT[name]}", cwd=REPO)
            self.allows(f"git -C {REPO} worktree remove {WT[name]}", cwd=OUTSIDE_TEMP)
        self.allows(f"git worktree remove {WT['merged']} 2>&1", cwd=REPO)
        self.allows(f"git worktree remove {WT['merged']} >/dev/null 2>&1", cwd=REPO)
        self.allows("git worktree remove ../wt-merged", cwd=REPO)
        self.allows(f"git -C {REPO} worktree remove ../wt-pushed", cwd=OUTSIDE_TEMP)

    def test_worktree_remove_dirty_asks(self):
        for name in ("dirty", "modified"):
            self.asks(f"git worktree remove {WT[name]}", cwd=REPO)

    def test_worktree_remove_with_ignored_file_asks(self):
        # remove は ignored のファイルも一緒に消す（git は拒否しない）
        self.asks(f"git worktree remove {WT['ignored']}", cwd=REPO)

    def test_worktree_remove_unpushed_asks(self):
        # detachedleft・wtref は HEAD の先端が origin/main でも、reflog・refs/worktree/keep にしか無い commit を持つ（review B1）
        for name in ("unpushed", "detachedahead", "detachedleft", "wtref"):
            self.asks(f"git worktree remove {WT[name]}", cwd=REPO)

    def test_worktree_remove_reflog_limit_asks(self):
        # reflog と per-worktree の ref の commit が上限を超えたら判定しない。上限は 1000 に固定する
        source = (WORK / "guard-bash.py").read_text()
        self.assertEqual(source.count("WORKTREE_REFLOG_LIMIT = 1000\n"), 1)
        (WORK / "guard-limit.py").write_text(source.replace("WORKTREE_REFLOG_LIMIT = 1000\n", "WORKTREE_REFLOG_LIMIT = 1\n"))
        # pushed の reflog は main と pushed の 2 commit で、どちらも branch に乗る（上限が 1000 なら通る）
        self.allows(f"git worktree remove {WT['pushed']}", cwd=REPO)
        self.assertEqual(decide(f"git worktree remove {WT['pushed']}", cwd=REPO, script="guard-limit.py")[0], "ask")

    def test_worktree_remove_tilde(self):
        # ~/ は引用が無く HOME の上書きも無いときだけ HOME へ展開する。引用した "~/x" は git には cwd の ~ という dir
        home = {"HOME": str(WORK)}
        self.allows("git worktree remove ~/wt-merged", cwd=REPO, env=home)
        for command in ('git worktree remove "~/wt-merged"', "git worktree remove '~/wt-merged'", "git worktree remove \\~/wt-merged",
                        "HOME=/nonexistent-guard-home git worktree remove ~/wt-merged"):
            self.asks(command, cwd=REPO, env=home)

    def test_worktree_remove_glob_named_dir_asks(self):
        # glob の文字を含む実在の dir 名でも、shell が別の dir に展開しうるので判定しない
        self.asks(f"git worktree remove {WT['glob[1]']}", cwd=REPO)

    def test_worktree_remove_env_prefix_asks(self):
        # GIT_DIR=… の前置きは git が見る repo を変える。guard の判定（前置きなし）と実行が食い違う
        self.asks(f"GIT_DIR={REPO}/.git git worktree remove {WT['merged']}", cwd=REPO)
        self.asks(f"FOO=1 git worktree remove {WT['merged']}", cwd=REPO)

    def test_worktree_remove_hook_git_env_is_ignored(self):
        # hook の環境の GIT_DIR が別の worktree を指していても、対象の worktree 自身の状態で判定する
        env = {"GIT_DIR": str(REPO / ".git" / "worktrees" / "wt-merged")}
        self.asks(f"git worktree remove {WT['unpushed']}", cwd=REPO, env=env)
        self.allows(f"git worktree remove {WT['merged']}", cwd=REPO, env=env)

    def test_worktree_remove_local_upstream_asks(self):
        # upstream が手元の branch なら push していない
        self.asks(f"git worktree remove {WT['localup']}", cwd=REPO)

    def test_worktree_remove_main_worktree_asks(self):
        self.asks(f"git worktree remove {REPO}", cwd=REPO)
        # 旧い git は --path-format=absolute を echo する。git-dir の読み違いで main worktree を通さない（review N1）
        old_git = {"PATH": str(OLD_GIT) + os.pathsep + os.environ.get("PATH", "")}
        self.asks(f"git worktree remove {REPO}", cwd=REPO, env=old_git)

    def test_worktree_remove_unjudgeable_form_asks(self):
        merged = WT["merged"]
        for command in (
            f"git worktree remove --force {merged}", f"git worktree remove -f {merged}", f"git worktree remove {merged} --force",
            "git worktree remove $WT", f"git worktree remove {WORK}/wt-merg*", f"git worktree remove {WORK}/wt-{{merged,x}}",
            f"git worktree remove {merged}$(echo)", f"git worktree remove `echo {merged}`", f"git worktree remove {merged} $(true)",
            # 空の置換は別の segment を作らず、置換を外した字面だけが残る
            f"git worktree remove {merged}$()", f"git worktree remove {merged} $( )", f"git worktree remove {merged}``",
            f"git -C {merged} commit -q --allow-empty -m x && git worktree remove {merged}", f"echo a; git worktree remove {merged}",
            f"git worktree remove {merged} | cat", f"bash -c 'git worktree remove {merged}'", f"env -C {REPO} git worktree remove {merged}",
            f"git -c core.x=1 worktree remove {merged}", f"git --git-dir={REPO}/.git worktree remove {merged}",
            "git -C $X worktree remove ../wt-merged", f"git -C $X worktree remove {merged}", f"git -C {REPO}* worktree remove {merged}", f"git worktree remove {merged} {WT['pushed']}", "git worktree remove",
            f"git worktree remove {WORK}/no-such-dir", f"git worktree remove {merged}/..", f"cd {REPO} && git worktree remove ../wt-merged",
            f"git worktree move {merged} {WORK}/moved", "git worktree prune",
        ):
            self.asks(command, cwd=REPO)

    def test_worktree_remove_relative_resolves_from_cwd(self):
        # 相対 path は hook の cwd（と -C）から読む。別の dir から見た ../wt-merged は worktree でない
        self.asks("git worktree remove ../wt-merged", cwd=OUTSIDE_TEMP / "bin")
        self.asks("git worktree remove wt-merged", cwd=REPO)


class AskLog(Base):
    """ask を出すたびに 種別・先頭語・日時 を 1 行で記録する。command の全文は書かない（#250）."""

    def setUp(self):
        self.log = Path(tempfile.mkdtemp(prefix="ask-log-", dir=WORK)) / "guard-ask.log"

    def lines(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_ask_is_logged_without_command_text(self):
        env = {"GUARD_ASK_LOG": str(self.log)}
        self.asks("git branch -D topic-secret-value", cwd=FEAT, env=env)
        self.asks("git push --force origin hunter2-token", cwd=FEAT, env=env)
        self.asks(f"git worktree remove {WT['dirty']}", cwd=REPO, env=env)
        self.allows(f"git worktree remove {WT['merged']}", cwd=REPO, env=env)
        self.assertEqual(decide("cat .env", cwd=FEAT, env=env)[0], "deny")
        lines = self.lines()
        self.assertEqual([line.split("\t")[1:] for line in lines],
                         [["branch-D", "git branch"], ["push-force", "git push"], ["worktree-remove", "git worktree"]])
        self.assertRegex(lines[0].split("\t")[0], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
        text = self.log.read_text()
        for secret in ("topic-secret-value", "hunter2-token", str(WT["dirty"])):
            self.assertNotIn(secret, text)

    def test_ask_log_failure_keeps_decision(self):
        # 置き場が dir（書けない）・置き場の dir が無い ときも、判定は ask のまま
        self.log.parent.joinpath("as-dir").mkdir()
        # 先の無い symlink は存在しない path に見えて open まで進み、open が失敗する（追記の例外を握りつぶす側の検査）
        dangling = self.log.parent / "dangling"
        dangling.symlink_to(WORK / "no-such-dir" / "x.log")
        for target in (self.log.parent / "as-dir", WORK / "no-such-dir" / "guard-ask.log", dangling):
            decision, reason = decide("git branch -D topic", cwd=FEAT, env={"GUARD_ASK_LOG": str(target)})
            self.assertEqual(decision, "ask", target)
            self.assertIn("失いうる", reason)
        self.assertFalse((WORK / "no-such-dir").exists())
        # FIFO は open が reader を待って戻らない。書かずに即座に ask を返す（review N3。hang は timeout で検出する）
        fifo = self.log.parent / "fifo"
        os.mkfifo(str(fifo))
        decision, _ = decide("git branch -D topic", cwd=FEAT, env={"GUARD_ASK_LOG": str(fifo)}, timeout=10)
        self.assertEqual(decision, "ask")

    def test_ask_reason_says_what_can_be_lost(self):
        decision, reason = decide("git branch -D topic", cwd=FEAT)
        self.assertEqual(decision, "ask")
        self.assertIn("失いうる", reason)
        self.assertIn("scripts/merge-pr.sh", reason)
        decision, reason = decide(f"git worktree remove {WT['dirty']}", cwd=REPO)
        self.assertEqual(decision, "ask")
        self.assertIn("失いうる", reason)
        self.assertIn("確認なしで通る", reason)

    def test_stats_counts_by_kind(self):
        env = {"GUARD_ASK_LOG": str(self.log)}
        for command in ("git branch -D a", "git branch -D b", "git reset --hard"):
            self.asks(command, cwd=FEAT, env=env)
        with self.log.open("a") as handle:
            handle.write("broken line\n")
        stats = [sys.executable, str(ROOT / "scripts/guard-ask-stats.py"), "--log", str(self.log)]
        done = subprocess.run(stats, text=True, capture_output=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines(), ["2\tbranch-D", "1\treset-hard", "合計\t3"])
        self.assertIn("読めない行: 1", done.stderr)
        done = subprocess.run(stats + ["--by", "head"], text=True, capture_output=True, check=False)
        self.assertEqual(done.stdout.splitlines(), ["2\tgit branch", "1\tgit reset", "合計\t3"])
        done = subprocess.run(stats + ["--since", "2999-01-01"], text=True, capture_output=True, check=False)
        self.assertEqual(done.stdout.splitlines(), ["合計\t0"])
        done = subprocess.run(stats[:-1] + [str(WORK / "no-such.log")], text=True, capture_output=True, check=False)
        self.assertEqual(done.returncode, 0)
        self.assertIn("記録が無い", done.stdout)


class PushCd(Base):
    def test_push_without_cd_judges_by_cwd(self):
        self.asks("git push", cwd=MAIN)
        self.allows("git push", cwd=FEAT)
        self.allows(f"git -C {FEAT} push", cwd=MAIN)
        self.asks(f"git -C {MAIN} push", cwd=FEAT)

    def test_push_follows_cd_to_non_main(self):
        for command in (f"cd {FEAT} && git push", f"cd {FEAT}; git push origin", f"cd {FEAT} && git add . && git push",
                        f"cd {FEAT} && bash -c 'git push'", f"cd {WORK} && cd feat-repo && git push"):
            self.allows(command, cwd=MAIN)

    def test_push_follows_cd_to_main(self):
        self.asks(f"cd {MAIN} && git push", cwd=FEAT)
        self.asks(f"cd {FEAT} && cd {MAIN} && git push", cwd=FEAT)

    def test_push_after_cd_keeps_other_asks(self):
        self.asks(f"cd {FEAT} && git push origin main", cwd=MAIN)
        self.asks(f"cd {FEAT} && git push --force", cwd=MAIN)
        self.asks(f"cd {FEAT} && git push origin HEAD:refs/heads/main", cwd=MAIN)

    def test_push_unfollowable_cd_falls_back(self):
        # 追い切れない形は旧来どおり hook 入力の cwd（main）で判定し、確認になる
        for command in (
            f"cd {FEAT} | git push", f"(cd {FEAT} && git push)", f"cd {FEAT} & git push", f"echo a; cd {FEAT} && git push",
            f"cd {FEAT} && if true; then cd {MAIN}; fi; git push", f"cd {FEAT} || git push", "cd /nonexistent-guard-dir; git push",
            f"cd {FEAT} && bash -c 'cd {MAIN} && git push'", "cd $X && git push", "cd - && git push", "cd && git push",
        ):
            self.asks(command, cwd=MAIN)

    def test_push_cd_target_substitution_falls_back(self):
        # cd $(…) は置換が消えて引数なしの cd（HOME）に見える。HOME が feat でも、実際の行き先は main
        self.asks(f"cd $(echo {MAIN}) && git push", cwd=MAIN, env={"HOME": str(FEAT)})
        self.asks(f"cd `echo {MAIN}` && git push", cwd=MAIN, env={"HOME": str(FEAT)})

    def test_push_with_chdir_wrapper_uses_hook_cwd(self):
        self.asks(f"cd {FEAT} && env -C {MAIN} git push", cwd=MAIN)


class CiWatch(Base):
    """CI の完了待ち（#228）: gh 自身が待つ形が先頭のときだけ通し、sleep の前置や loop は今どおり deny."""

    def test_ci_watch_at_head_is_allowed(self):
        for command in ("gh pr checks 1 --watch", "gh run watch 123", "scripts/wait-for-pr-checks.sh 1",
                        "scripts/wait-for-pr-checks.sh 1 --timeout 600", "gh pr checks 1 --watch --interval 5",
                        "gh pr checks 1 --watch 2>&1 | tail -n 20"):
            self.allows(command, cwd=FEAT)

    def test_ci_watch_after_sleep_is_denied(self):
        for command in ("sleep 60; gh pr checks 1 --watch", "sleep 60 && gh pr checks 1 --watch",
                        "gh pr checks 1 --watch && sleep 5 && gh pr checks 1"):
            self.assertEqual(decide(command, cwd=FEAT)[0], "deny", command)

    def test_sleep_loop_is_denied(self):
        for command in ("while ! gh pr checks 1; do sleep 10; done", "until gh pr checks 1; do sleep 10; done",
                        "for i in 1 2 3; do gh pr checks 1; sleep 5; done; while true; do sleep 1; done",
                        "while true; do gh pr checks 1 --watch; sleep 5; done"):
            self.assertEqual(decide(command, cwd=FEAT)[0], "deny", command)

    def test_wrapped_watch_keeps_old_verdict(self):
        # 解析できない形（bash -c・eval）は例外にしない。旧版と同じ判定のまま
        for command in ("bash -c 'gh pr checks 1 --watch'", "eval 'gh run watch 1'", "sleep 5; bash -c 'gh pr checks 1 --watch'"):
            self.allows(command, cwd=FEAT)
        self.assertEqual(decide("bash -c 'sleep 5; gh pr checks 1 --watch'", cwd=FEAT)[0], "deny")


if __name__ == "__main__":
    selected = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    if arguments.case:
        name = CASES[arguments.case]
        for cls in (RmTemporary, WorktreeRemove, AskLog, PushCd, CiWatch):
            if hasattr(cls, name):
                selected.addTest(cls(name))
    else:
        selected.addTests(loader.loadTestsFromTestCase(RmTemporary))
        selected.addTests(loader.loadTestsFromTestCase(WorktreeRemove))
        selected.addTests(loader.loadTestsFromTestCase(AskLog))
        selected.addTests(loader.loadTestsFromTestCase(PushCd))
        selected.addTests(loader.loadTestsFromTestCase(CiWatch))
    result = unittest.TextTestRunner(verbosity=0, stream=sys.stderr).run(selected)
    sys.exit(0 if result.wasSuccessful() else 1)
