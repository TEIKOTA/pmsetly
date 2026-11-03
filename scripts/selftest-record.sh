#!/usr/bin/env bash
# self-test の記録の行を、bash の版を確かめて作る（#211。merge-pr.sh の `self-test:` の行の元になる）。
# 使い方:
#   scripts/selftest-record.sh run  --head <40 桁の SHA> --where <場所の label>
#   scripts/selftest-record.sh emit --head <40 桁の SHA>      （run の記録の行を stdin から複数読む）
# run: cwd の repo の HEAD が <SHA> と一致し作業ツリーが clean であることを確かめ、`bash --version` の版を取り、
#   self-test の全件を流して 1 行の記録を stdout に出す。FAIL なら exit 1（記録は FAIL で出す）。
#     self-test-run: head <SHA> bash=<版 例 5.2.15> where=<label> result=PASS|FAIL count=<N>
#   全件の見つけ方は SELFTEST_CMD（設定されていれば `bash -c` で実行）→ tests/run-tests.sh。見つからなければ exit 2。
#   label は英数字・. _ : - と空白（例: host / container review-206 / ci ubuntu）。
#   HOME が一時領域（/tmp・$TMPDIR 等）の下なら exit 2 で止まる。guard の test が `~` を一時領域と判定して落ちるため
#   （bash 5 をコンテナで流すときは agent-box の entrypoint と同じ home の配置にする）。
# emit: stdin の記録の行が (a) すべて同じ head、(b) すべて PASS、(c) major が 3 の版と 4 以上の版の両方を含む、を確かめ、
#   merge-pr.sh が受け付ける行と、場所と版を残す次の `>` の引用行を出す。(c) を満たさない（同じ major を
#   2 回流した等）なら exit 1。bash 5 はコンテナ（agent-box）か GitHub の ubuntu の CI で流す。
#     self-test: head <SHA> bash=PASS /bin/bash=PASS
#     > bash 3.2.57（host）PASS 1074 / bash 5.2.15（container review-206）PASS 1047
#   同じ記録の行が 2 回以上あっても受け付け、stderr に警告を 1 行出して 2 回目以降は数えない（引用行にも 1 回だけ載る）。
# ホストで head の写しを流すときの置き場は ~/.trashable/<repo>/selftest-<head の先頭 7 桁>/（~/worktrees/ には置かない）。
#   run は写しの中で HEAD を確かめるので、git archive の展開（.git が無い）でなく clone して head を checkout する:
#   git clone -q <repo> <置き場> && git -C <置き場> checkout -q --detach <SHA>
# SELFTEST_RECORD_BASH: 版を取る bash（既定 bash。test が偽の版を与えるために使う）
set -euo pipefail

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; }
die() { echo "✖ $1" >&2; exit "${2:-1}"; }

cmd="${1:-}"
case "$cmd" in
  -h|--help) usage; exit 0 ;;
  run|emit) shift ;;
  *) usage >&2; exit 2 ;;
esac

head_sha=""
where=""
while [ $# -gt 0 ]; do
  case "$1" in
    --head) head_sha="${2:?--head には SHA が必要です}"; shift 2 ;;
    --where) where="${2:?--where には label が必要です}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "不明な引数: $1" 2 ;;
  esac
done
[[ "$head_sha" =~ ^[0-9a-f]{40}$ ]] || die "--head は 40 桁の小文字 16 進の SHA が必要です" 2

if [ "$cmd" = "run" ]; then
  [[ "$where" =~ ^[A-Za-z0-9._:\ -]+$ ]] || die "--where は英数字・. _ : - と空白だけの label が必要です" 2
  case "$where" in *" result="*|" "*|*" ") die "--where の label が不正です（前後の空白・result= は不可）" 2 ;; esac

  tmp_root="${TMPDIR:-/tmp}"
  tmp_root="${tmp_root%/}"
  for t in /tmp /private/tmp /var/folders /private/var/folders "$tmp_root"; do
    case "$HOME/" in "$t"/*) die "HOME($HOME)が一時領域($t)の下。guard の test が落ちるので、HOME を一時領域の外に置く" 2 ;; esac
  done

  actual="$(git rev-parse HEAD 2>/dev/null)" || die "git の repo の中で流す" 2
  [ "$actual" = "$head_sha" ] || die "HEAD($actual)が --head と違う" 2
  [ -z "$(git status --porcelain)" ] || die "作業ツリーが clean でない" 2

  ver="$("${SELFTEST_RECORD_BASH:-bash}" --version | sed -n '1s/^.*version \([0-9][0-9.]*\).*$/\1/p')"
  [[ "$ver" =~ ^[0-9]+(\.[0-9]+)*$ ]] || die "bash の版を読めない" 2

  if [ "${SELFTEST_CMD+x}" = "x" ] && [ -n "$SELFTEST_CMD" ]; then
    run_it() { bash -c "$SELFTEST_CMD"; }
  elif [ -f tests/run-tests.sh ]; then
    run_it() { bash tests/run-tests.sh; }
  else
    die "流す self-test が見つからない（SELFTEST_CMD か tests/run-tests.sh）" 2
  fi

  rc=0
  out="$(run_it 2>&1)" || rc=$?
  last="$(printf '%s\n' "$out" | tail -n 1)"
  result=FAIL
  count=0
  if [[ "$last" =~ ^PASS:\ ([0-9]+)\ tests ]]; then
    count="${BASH_REMATCH[1]}"
    [ "$rc" -eq 0 ] && result=PASS
  elif [[ "$last" =~ ^passed:\ ([0-9]+)\ /\ failed:\ [0-9]+ ]]; then
    count="${BASH_REMATCH[1]}"
  else
    echo "✖ 集計行を読めない（rc=${rc}）: $last" >&2
  fi
  printf 'self-test-run: head %s bash=%s where=%s result=%s count=%s\n' "$head_sha" "$ver" "$where" "$result" "$count"
  if [ "$result" != PASS ]; then
    printf '%s\n' "$out" | tail -n 20 >&2
    exit 1
  fi
  exit 0
fi

# emit
re='^self-test-run: head ([0-9a-f]{40}) bash=([0-9]+(\.[0-9]+)*) where=([A-Za-z0-9._: -]+) result=(PASS|FAIL) count=([0-9]+)$'
old=""
new=""
n=0
seen=$'\n'
while IFS= read -r line || [ -n "$line" ]; do
  [ -n "$line" ] || continue
  [[ "$line" =~ $re ]] || die "記録の行として読めない: $line"
  case "$seen" in
    *$'\n'"$line"$'\n'*) echo "⚠ 同じ記録の行が重複している（2 回目以降は数えない）: $line" >&2; continue ;;
  esac
  seen="${seen}${line}"$'\n'
  n=$((n + 1))
  [ "${BASH_REMATCH[1]}" = "$head_sha" ] || die "head が --head と違う行がある: $line"
  [ "${BASH_REMATCH[5]}" = PASS ] || die "PASS でない行がある: $line"
  ver="${BASH_REMATCH[2]}"
  item="bash ${ver}（${BASH_REMATCH[4]}）PASS ${BASH_REMATCH[6]}"
  if [ "${ver%%.*}" -eq 3 ]; then
    old="${old:+$old / }$item"
  elif [ "${ver%%.*}" -ge 4 ]; then
    new="${new:+$new / }$item"
  else
    die "bash 3 未満の版は扱わない: $line"
  fi
done
[ "$n" -gt 0 ] || die "記録の行が stdin に無い"
if [ -z "$old" ] || [ -z "$new" ]; then
  die "bash 3 と bash 4 以上の両方の記録が要る（同じ major を 2 回流しても両方の Bash を確かめたことにならない）。bash 5 はコンテナ（agent-box）か GitHub の ubuntu の CI で流す"
fi
printf 'self-test: head %s bash=PASS /bin/bash=PASS\n' "$head_sha"
printf '> %s / %s\n' "$old" "$new"
