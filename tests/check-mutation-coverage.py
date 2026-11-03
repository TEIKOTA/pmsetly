#!/usr/bin/env python3
"""test の退行注入の表（`MUTATIONS`）と `tests/run-tests.sh` の一覧のずれを検出する（#206）。

`MUTATIONS` が list / tuple の `tests/*.py`（自分で全件を回す形）は、`run-tests.sh` から一度でも呼ばれていなければ red。
`tests/*.py` の top-level の `MUTATIONS = {...}` の key は、`tests/run-tests.sh` から
`python3 "$ROOT/tests/<name>.py" ... --mutation <key>` の形（`for <var> in a b c; do ... --mutation "$<var>"` の
loop か、`--mutation <key>` の直書き）で全部呼ばれていなければならない。表に足して一覧に足し忘れると、
その退行注入は self-test の全件で流れず、保護が外れても気づけない（#206: merge-pr.py の `approvalhint`）。
使い方: check-mutation-coverage.py <root>（root 直下の tests/ を見る）。ずれがあれば行を出して exit 1。
"""
import ast
import re
import sys
from pathlib import Path

LOOP = re.compile(r"^\s*for\s+(\w+)\s+in\s+(.+?)\s*;\s*do\b")
DONE_WORD = re.compile(r"(?:^|;)\s*done\b")
TEST_FILE = re.compile(r"tests/([A-Za-z0-9_.-]+\.py)")
MUTATION_ARG = re.compile(r"--mutation\s+(\"?\$\{?\w+\}?\"?|[A-Za-z0-9_-]+)")


def table_keys(path):
    """top-level の `MUTATIONS = ...` の key（文字列）を返す。無ければ None。

    dict は key の集合。list / tuple（test が自分で全件を回す形）は空集合を返し、呼ばれているかだけを見る。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MUTATIONS" for t in node.targets):
            if isinstance(node.value, ast.Dict):
                return {k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}, True
            if isinstance(node.value, (ast.List, ast.Tuple)):
                return set(), False
    return None


def covered_by_runner(runner):
    """runner の中で `tests/<name>.py` に `--mutation` で渡される key を file ごとに集める。

    戻り値は (file ごとの key の集合, 呼ばれている file の集合)。行頭が `#` の行は読み飛ばす。
    loop は入れ子を stack で持ち、同じ行の `done` はその行の処理後に外す。
    """
    covered = {}
    called = set()
    stack = []
    for line in runner.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        body = line
        match = LOOP.match(line)
        if match:
            stack.append((match.group(1), match.group(2).split()))
            body = line[match.end():]
        # `done` で body を区切り、その手前までを現在の loop の中として数える
        segments = DONE_WORD.split(body)
        for index, segment in enumerate(segments):
            files = TEST_FILE.findall(segment)
            called.update(files)
            for arg in MUTATION_ARG.findall(segment) if files else []:
                if arg.startswith("$") or arg.startswith('"$'):
                    var = re.sub(r"[\"${}]", "", arg)
                    names = next((items for name, items in reversed(stack) if name == var), [])
                else:
                    names = [arg]
                for name in files:
                    covered.setdefault(name, set()).update(names)
            if index < len(segments) - 1 and stack:
                stack.pop()
    return covered, called


def main():
    root = Path(sys.argv[1])
    runner = root / "tests/run-tests.sh"
    covered, called = covered_by_runner(runner)
    problems = []
    for path in sorted((root / "tests").glob("*.py")):
        table = table_keys(path)
        if table is None:
            continue
        keys, is_dict = table
        if not is_dict:
            if path.name not in called:
                problems.append("tests/%s: MUTATIONS を持つが run-tests.sh から呼ばれていない" % path.name)
            continue
        listed = covered.get(path.name, set())
        missing = sorted(keys - listed)
        unknown = sorted(listed - keys)
        if missing:
            problems.append("tests/%s: MUTATIONS にあるが run-tests.sh の一覧に無い: %s" % (path.name, " ".join(missing)))
        if unknown:
            problems.append("tests/%s: run-tests.sh の一覧にあるが MUTATIONS に無い: %s" % (path.name, " ".join(unknown)))
    print("\n".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
