#!/usr/bin/env bash
set -euo pipefail

# PR の CI(checks)の完了を待つ正本 waiter。中で `gh pr checks <PR> --watch` を 1 回呼び、その終了 code をそのまま返す。
#
# CI の待ちは、この script か `gh pr checks --watch` を 1 回で行う。`sleep N; gh pr checks` や
# while + sleep の即興 polling は guard が拒否する(gh 自身が待つので loop は要らない)。
# ログファイルの marker を待つ場合は scripts/wait-for-marker.sh を使う。
#
# 使い方:
#   scripts/wait-for-pr-checks.sh <PR番号> [--timeout <秒>] [--repo <owner/repo>]
#
# 挙動:
#   - gh pr checks --watch の終了 code を返す(0 = 全 check 成功、1 = 失敗、8 = pending など。gh の定義どおり)。
#   - --timeout を指定した場合、その秒数までに gh が終わらなければ gh を止めて exit 124。
#     timeout コマンド(macOS に無い)は使わず、背景 job の watchdog で守る。
#   - 引数の誤りは exit 2。--timeout の既定は無い(gh が終わるまで待つ)。tool の timeout より長く待ちうるので、ハーネスから呼ぶときは --timeout を付ける。
#   - wrapper 自身が TERM / INT を受けたら gh と watchdog を止めて一時 file を消し、exit 143 / 130。
#
# 呼び出し側の契約: AI ハーネスの Bash tool から呼ぶ場合、tool の timeout は --timeout より長く明示する。

usage() {
  sed -n '3,19p' "$0" | sed 's/^# \{0,1\}//'
}

pr=""
timeout_sec=""
repo=""
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --timeout)
      [ $# -ge 2 ] && [ -n "$2" ] || { echo "wait-for-pr-checks: --timeout に秒数が要る" >&2; exit 2; }
      timeout_sec="$2"; shift 2 ;;
    --repo)
      [ $# -ge 2 ] || { echo "wait-for-pr-checks: --repo に owner/repo が要る" >&2; exit 2; }
      repo="$2"; shift 2 ;;
    -*) echo "wait-for-pr-checks: 未知の option: $1" >&2; exit 2 ;;
    *)
      [ -z "$pr" ] || { echo "wait-for-pr-checks: PR 番号は 1 つだけ" >&2; exit 2; }
      pr="$1"; shift ;;
  esac
done

[ -n "$pr" ] || { echo "wait-for-pr-checks: PR 番号が要る(-h で usage)" >&2; exit 2; }
case "$pr" in *[!0-9]*) echo "wait-for-pr-checks: PR 番号は数字: $pr" >&2; exit 2 ;; esac
case "$timeout_sec" in *[!0-9]*) echo "wait-for-pr-checks: --timeout は秒数(整数): $timeout_sec" >&2; exit 2 ;; esac

args=(pr checks "$pr" --watch)
[ -z "$repo" ] || args+=(--repo "$repo")

if [ -z "$timeout_sec" ]; then
  exec gh "${args[@]}"
fi

# 打ち切りの印は一時 file で受け渡す(watchdog は subshell なので変数が戻らない)
flag="$(mktemp)"
gh_pid=""
watchdog=""
# wrapper 自身への TERM / INT では gh と watchdog を止め、一時 file を残さない(tool の timeout が wrapper だけに TERM を送る場合)
trap 'kill "$gh_pid" "$watchdog" 2>/dev/null; rm -f "$flag"; exit 143' TERM
trap 'kill "$gh_pid" "$watchdog" 2>/dev/null; rm -f "$flag"; exit 130' INT
gh "${args[@]}" &
gh_pid=$!
(
  sleep "$timeout_sec" &
  sleeper=$!
  trap 'kill "$sleeper" 2>/dev/null; exit 0' TERM
  wait "$sleeper" || true
  echo timeout > "$flag"
  kill "$gh_pid" 2>/dev/null || true
) &
watchdog=$!

rc=0
wait "$gh_pid" || rc=$?
kill "$watchdog" 2>/dev/null || true
wait "$watchdog" 2>/dev/null || true
if [ -s "$flag" ]; then
  rm -f "$flag"
  echo "wait-for-pr-checks: ${timeout_sec} 秒で打ち切った(PR #${pr})" >&2
  exit 124
fi
rm -f "$flag"
exit "$rc"
