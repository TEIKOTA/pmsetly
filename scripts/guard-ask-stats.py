#!/usr/bin/env python3
"""guard の ask の記録（#250）を理由の種別ごとに数える。

usage: guard-ask-stats.py [--log <path>] [--since YYYY-MM-DD] [--by kind|head|both]

  --log    記録の file（既定: $GUARD_ASK_LOG、無ければ ~/.claude/guard-ask.log）
  --since  この日付（記録の日時の日付部分）以降だけを数える
  --by     数える単位。kind（理由の種別。既定）・head（command の先頭語）・both（種別と先頭語の組）

記録は scripts/hooks/guard-bash.py が ask を出すたびに `日時<TAB>種別<TAB>先頭語` の 1 行で追記する。
承認・拒否の結果は hook から取れないので、ここで出すのは ask が出た件数だけ（拒否は transcript の
`The user doesn't want to proceed` で別に拾う）。件数の多い順に `件数<TAB>単位` を出し、最後に合計を出す。
読めない行は数えず、件数を stderr に出す。記録が無ければその旨を出して exit 0。
"""
import argparse
import collections
import os
import sys

DEFAULT_LOG = "~/.claude/guard-ask.log"


def main():
    parser = argparse.ArgumentParser(
        description="guard の ask の記録を理由の種別ごとに数える（#250）",
        epilog="記録の形式: 日時<TAB>種別<TAB>先頭語（scripts/hooks/guard-bash.py が追記する）",
    )
    parser.add_argument("--log", default=os.environ.get("GUARD_ASK_LOG") or DEFAULT_LOG)
    parser.add_argument("--since", help="YYYY-MM-DD。この日付以降だけを数える")
    parser.add_argument("--by", choices=("kind", "head", "both"), default="kind")
    arguments = parser.parse_args()

    path = os.path.expanduser(arguments.log)
    if not os.path.isfile(path):
        print("記録が無い: %s（guard が ask を出すと作られる）" % path)
        return 0
    counts = collections.Counter()
    skipped = 0
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 3 or len(fields[0]) < 10:
                skipped += 1
                continue
            stamp, kind, head = fields
            if arguments.since and stamp[:10] < arguments.since:
                continue
            key = {"kind": kind, "head": head, "both": kind + "\t" + head}[arguments.by]
            counts[key] += 1
    for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print("%d\t%s" % (count, key))
    print("合計\t%d" % sum(counts.values()))
    if skipped:
        print("読めない行: %d（数えていない）" % skipped, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
