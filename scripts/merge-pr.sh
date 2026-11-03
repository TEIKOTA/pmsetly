#!/usr/bin/env bash
# PR を squash merge する唯一の経路（#159。正本: docs/adr/20261016-gate-merge-behind-script-and-recorded-approval.md）。
# 承認の写しと merge 条件を確かめ、判定表を PR にコメントで残してから squash merge する（1 つでも欠ければ merge しない）。
# 使い方: scripts/merge-pr.sh <PR番号> --head <SHA> --judge scope=<判断> --judge injection=<判断>
#           [--judge no-perceptual-external=なし…] [--repo <owner>/<name>] [--dry-run] [--keep-branch]
#   --head   merge する head の SHA（40 桁）。live の head と違えば止まり、gh pr merge の --match-head-commit にも渡す
#   --judge  root の判断（script は中身を確かめず、判定表に「root の申告」として写す）。scope と injection は必須。
#            事前承認で merge するなら no-perceptual-external=なし（知覚の成果物・外部影響を含まない）も必須
#   --dry-run  判定表を出すだけで、コメントも merge もしない
#   --keep-branch  merge の後に手元の同名 branch を消さない。既定では、先端が merge した head と一致する手元の同名 branch を git branch -D で消す（#227。不一致・checkout 中は残して理由を出す）
#   PR のコメントに残す記録（owner のコメントの 1 行ぜんたいが一致する形。行の後ろに文字を足すと一致しない。書式は ADR 参照）:
#     review: head <40 桁の SHA> blocking=なし
#     self-test: head <40 桁の SHA> bash=PASS /bin/bash=PASS
#       （この行と、場所・版を残す次の `>` の引用行は scripts/selftest-record.sh が作る。bash の版が 3 と 4 以上の両方であることを確かめる）
#     merge 承認: head <40 桁の SHA>
#   承認は、上の行の次の行以降に、ユーザーの発言を > で引用する（補足は行の後ろでなく引用の行に書く）
#   owner のコメントの `review-outcome: rounds=<n> …` の n の最大値が 4 以上（修正ラウンドの上限 3 を超えた）なら、区切りでの承認が無い限り merge しない。rounds を数字で読めない `review-outcome:` の行が 1 件でもあるときも同じ（#248。行が無ければ数えない）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PR_NUM=""
HEAD_SHA=""
REPO=""
DRY_RUN=0
KEEP_BRANCH=0
JUDGES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --head) HEAD_SHA="${2:?--head には SHA が必要です}"; shift 2;;
    --judge) JUDGES+=("${2:?--judge には <key>=<判断> が必要です}"); shift 2;;
    --repo) REPO="${2:?--repo には <owner>/<name> が必要です}"; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    --keep-branch) KEEP_BRANCH=1; shift;;
    -h|--help) sed -n '2,18p' "$0" | sed -nE 's/^# ?//p'; exit 0;;
    -*) echo "不明な引数: $1" >&2; exit 2;;
    *)
      if [[ -n "$PR_NUM" ]]; then echo "PR番号は 1 つだけ指定してください" >&2; exit 2; fi
      PR_NUM="$1"; shift;;
  esac
done
if ! printf '%s\n' "$PR_NUM" | grep -qE '^[0-9]+$'; then
  echo "✖ PR番号を数字で指定してください" >&2; exit 2
fi
if ! printf '%s\n' "$HEAD_SHA" | grep -qE '^[0-9a-f]{40}$'; then
  echo "✖ --head に 40 桁の SHA が必要です" >&2; exit 2
fi
command -v gh >/dev/null 2>&1 || { echo "✖ gh CLI が必要です" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "✖ python3 が必要です" >&2; exit 1; }

REPO_ARGS=()
if [[ -n "$REPO" ]]; then REPO_ARGS=(--repo "$REPO"); fi

# ---- 取得 ---------------------------------------------------------------

fetch_pr() {
  gh pr view "$PR_NUM" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --json number,state,isDraft,title,body,headRefOid,baseRefName,baseRefOid,headRefName,mergeable,mergeStateStatus,comments
}
pr_json="$(fetch_pr)" || { echo "✖ PR #$PR_NUM を取得できません" >&2; exit 1; }

# jfield <名前>: PR の JSON の単一フィールドを文字列で返す（真偽は true / false）
jfield() {
  printf '%s' "$pr_json" | python3 -c '
import json, sys
value = json.load(sys.stdin)[sys.argv[1]]
print(str(value).lower() if isinstance(value, bool) else value)' "$1"
}

# リポジトリの owner（記録の行は owner のコメントだけを数える。取れなければ誰のコメントも数えない）と既定 branch（base の条件。取れなければ base は FAIL）
repo_json="$(gh repo view ${REPO:+"$REPO"} --json nameWithOwner,defaultBranchRef 2>/dev/null)" || repo_json=""
repo_field() { # repo_field nameWithOwner|defaultBranch: 取れなければ空
  printf '%s' "$repo_json" | python3 -c '
import json, sys
data = json.load(sys.stdin)
print(data["nameWithOwner"] if sys.argv[1] == "nameWithOwner" else data["defaultBranchRef"]["name"])' "$1" 2>/dev/null || true
}
nwo="$(repo_field nameWithOwner)"
OWNER="${nwo%%/*}"
DEFAULT_BRANCH="$(repo_field defaultBranch)"

# comment_has <正規表現> [quote]: owner のコメントに、行全体が正規表現に一致する行があるか。quote なら同じコメントに > の引用行も要る
comment_has() {
  printf '%s' "$pr_json" | python3 -c '
import json, re, sys
owner = sys.argv.pop(1).lower()
pattern, need_quote = re.compile(sys.argv[1]), len(sys.argv) > 2
for comment in json.load(sys.stdin)["comments"]:
    if not owner or ((comment.get("author") or {}).get("login") or "").lower() != owner:
        continue
    lines = comment["body"].splitlines()
    if any(pattern.fullmatch(line.strip()) for line in lines) and (
            not need_quote or any(re.match(r">\s*\S", line.strip()) for line in lines)):
        sys.exit(0)
sys.exit(1)' "$OWNER" "$@"
}

# review_rounds: owner のコメントの `review-outcome: rounds=<n>` の n の最大値（行が無ければ -1）と、rounds を [0-9]+ で読めない行の数を空白区切りで返す
review_rounds() {
  printf '%s' "$pr_json" | python3 -c '
import json, re, sys
owner = sys.argv[1].lower()
best, unreadable = -1, 0
for comment in json.load(sys.stdin)["comments"]:
    author = ((comment.get("author") or {}).get("login") or "").lower()
    if not owner or author != owner:
        continue
    for line in comment["body"].splitlines():
        line = line.strip()
        if not line.startswith("review-outcome:"):
            continue
        match = re.match(r"review-outcome: rounds=([0-9]+)(\s|$)", line)
        if match:
            best = max(best, min(int(match.group(1)), 1000000))  # bash の整数の桁あふれで小さく読まない
        else:
            unreadable += 1
print(best, unreadable)' "$OWNER"
}

STATE="$(jfield state)"; DRAFT="$(jfield isDraft)"; TITLE="$(jfield title)"
LIVE_HEAD="$(jfield headRefOid)"; BASE="$(jfield baseRefName)"; BASE_OID="$(jfield baseRefOid)"
MERGEABLE="$(jfield mergeable)"; STATE_STATUS="$(jfield mergeStateStatus)"
# 直前に main が進むと GitHub が mergeable を計算中で UNKNOWN を返す。数秒おいて読み直し、確定した値で判定する（#183）。
# 読み直しても UNKNOWN なら、そのまま下の判定で FAIL にする（fail-closed）。待ちは MERGE_PR_UNKNOWN_WAIT（秒）、回数は MERGE_PR_UNKNOWN_RETRIES で変える
UNKNOWN_RETRIES="${MERGE_PR_UNKNOWN_RETRIES:-5}"
UNKNOWN_WAIT="${MERGE_PR_UNKNOWN_WAIT:-3}"
attempt=0
while [[ "$MERGEABLE" == "UNKNOWN" || "$STATE_STATUS" == "UNKNOWN" ]] && [[ "$attempt" -lt "$UNKNOWN_RETRIES" ]]; do
  attempt=$((attempt + 1))
  sleep "$UNKNOWN_WAIT"
  pr_json="$(fetch_pr)" || { echo "✖ PR #$PR_NUM を取得できません" >&2; exit 1; }
  STATE="$(jfield state)"; DRAFT="$(jfield isDraft)"; TITLE="$(jfield title)"
  LIVE_HEAD="$(jfield headRefOid)"; BASE="$(jfield baseRefName)"; BASE_OID="$(jfield baseRefOid)"
  MERGEABLE="$(jfield mergeable)"; STATE_STATUS="$(jfield mergeStateStatus)"
done

# ---- 判定表 ---------------------------------------------------------------

FAILS=0
ROWS=""
# row <確認者> <結果 PASS|FAIL|申告> <条件> <詳細>
row() {
  [[ "$2" == "FAIL" ]] && FAILS=$((FAILS + 1))
  ROWS="$ROWS| $3 | $1 | $2 | $4 |"$'\n'
}
judge_value() { # judge_value <key>: --judge の値（無ければ空）
  local entry
  for entry in ${JUDGES[@]+"${JUDGES[@]}"}; do
    if [[ "${entry%%=*}" == "$1" && "$entry" == *=* ]]; then printf '%s' "${entry#*=}"; return; fi
  done
}

# 1. 状態・head・base
if [[ "$STATE" == "OPEN" && "$DRAFT" == "false" ]]; then row script PASS "open かつ draft でない" "state=$STATE"; else row script FAIL "open かつ draft でない" "state=$STATE draft=$DRAFT"; fi
if [[ "$LIVE_HEAD" == "$HEAD_SHA" ]]; then row script PASS "head が提示した SHA と一致" "\`$HEAD_SHA\`"; else row script FAIL "head が提示した SHA と一致" "live=\`$LIVE_HEAD\` 提示=\`$HEAD_SHA\`"; fi
# 幹は main か、その repo の既定 branch（SabolinGood は development と main、Nowflo は release/v1 と main。テンプレートは main だけ）。既定 branch が取れなければ FAIL
if [[ -z "$DEFAULT_BRANCH" ]]; then row script FAIL "base が main か既定 branch" "base=${BASE} 既定 branch を取得できない"
elif [[ "$BASE" == "main" || "$BASE" == "$DEFAULT_BRANCH" ]]; then row script PASS "base が main か既定 branch" "base=$BASE 既定 branch=$DEFAULT_BRANCH (\`$BASE_OID\`)"
else row script FAIL "base が main か既定 branch" "base=${BASE} 既定 branch=${DEFAULT_BRANCH}（stacked child は親を merge してから ${DEFAULT_BRANCH} に付け替える）"; fi
if [[ "$MERGEABLE" == "MERGEABLE" && "$STATE_STATUS" == "CLEAN" ]]; then row script PASS "mergeable かつ clean" "mergeable=$MERGEABLE status=$STATE_STATUS"; else
  unknown_note=""
  if [[ "$MERGEABLE" == "UNKNOWN" || "$STATE_STATUS" == "UNKNOWN" ]]; then unknown_note="（GitHub が計算中。少しおいてやり直す）"; fi
  row script FAIL "mergeable かつ clean" "mergeable=$MERGEABLE status=$STATE_STATUS$unknown_note"
fi

# 2. merge-tree（base と head を取り直し、衝突が無いか）
mt_ok=0
if git fetch --quiet origin "+refs/pull/$PR_NUM/head:refs/merge-pr/$PR_NUM/head" "+refs/heads/$BASE:refs/merge-pr/$PR_NUM/base" 2>/dev/null \
   && [[ "$(git rev-parse "refs/merge-pr/$PR_NUM/head")" == "$HEAD_SHA" ]] \
   && git merge-tree --write-tree "refs/merge-pr/$PR_NUM/base" "refs/merge-pr/$PR_NUM/head" >/dev/null 2>&1; then
  mt_ok=1
fi
if [[ "$mt_ok" -eq 1 ]]; then row script PASS "merge-tree に衝突が無い" "origin/$BASE と \`$HEAD_SHA\`"; else row script FAIL "merge-tree に衝突が無い" "取得の失敗・head の不一致・衝突のいずれか"; fi

# 2b. git diff --check（merge-base からの差分に空白の誤りが無い）。取得に失敗していれば merge-tree の行が FAIL を出す
if [[ "$mt_ok" -eq 1 ]] && git diff --check "refs/merge-pr/$PR_NUM/base...refs/merge-pr/$PR_NUM/head" >/dev/null 2>&1; then
  row script PASS "git diff --check" "空白の誤りなし"
else
  row script FAIL "git diff --check" "空白の誤りがある、または head を取得できていない"
fi

# 3. scripts/check-pr.sh
if cp_out="$(bash "$ROOT/check-pr.sh" "$PR_NUM" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} 2>&1)"; then
  row script PASS "scripts/check-pr.sh" "タイトル・body・issue 連結"
else
  row script FAIL "scripts/check-pr.sh" "$(printf '%s' "$cp_out" | tr '\n' ' ')"
fi

# 4. 未解決のレビュースレッド
unresolved=""
if [[ -n "$nwo" ]]; then
  query='query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){reviewThreads(first:100){pageInfo{hasNextPage} nodes{isResolved}}}}}'
  if unresolved="$(gh api graphql -f query="$query" -F owner="${nwo%%/*}" -F name="${nwo#*/}" -F number="$PR_NUM" 2>/dev/null | python3 -c '
import json, sys
threads = json.load(sys.stdin)["data"]["repository"]["pullRequest"]["reviewThreads"]
print("取りきれない" if threads["pageInfo"]["hasNextPage"] else sum(1 for node in threads["nodes"] if not node["isResolved"]))')"; then :; else unresolved="取得失敗"; fi
else
  unresolved="取得失敗"
fi
if [[ "$unresolved" == "0" ]]; then row script PASS "未解決のレビュースレッドが 0" "0 件"; else row script FAIL "未解決のレビュースレッドが 0" "$unresolved"; fi

# 5. 記録（コメントの行）。head に結んであり、head が変われば無効になる
if comment_has "review: head $HEAD_SHA blocking=なし"; then row script PASS "別 context の独立レビューが head に対して blocking なし" "コメントの記録"; else row script FAIL "別 context の独立レビューが head に対して blocking なし" "\`review: head <SHA> blocking=なし\` の記録が無い"; fi
if comment_has "self-test: head $HEAD_SHA bash=PASS /bin/bash=PASS"; then row script PASS "両方の Bash の self-test が通る" "コメントの記録"; else row script FAIL "両方の Bash の self-test が通る" "\`self-test: head <SHA> bash=PASS /bin/bash=PASS\` の記録が無い"; fi

# 6. root の判断（script は中身を確かめない）
for key in scope injection; do
  value="$(judge_value "$key")"
  case "$key" in
    scope) label="diff が issue の範囲内で、合意に無い新しい判断が無い";;
    injection) label="guard・bug 修正の退行注入で red → 復元後 green（対象外なら理由）";;
  esac
  if [[ -n "$value" ]]; then row root 申告 "$label" "$value"; else row root FAIL "$label" "--judge $key=<判断> が無い"; fi
done

# 7. 承認の写し。どちらも無ければ merge しない
approval=""
pre_blocked=""
perceptual="$(judge_value no-perceptual-external)"
issues="$(printf '%s' "$(jfield body)" | bash "$ROOT/check-pr-body-close.sh" --title "$TITLE" --print-issues 2>/dev/null || true)"
for n in $issues; do
  section="$(gh issue view "$n" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --json body 2>/dev/null | python3 -c '
import json, sys
inside, lines = False, []
for line in json.load(sys.stdin)["body"].splitlines():
    if line.startswith("## "):
        inside = line.strip() == "## merge の事前承認"
    elif inside:
        lines.append(line)
print("\n".join(lines))' || true)"
  if printf '%s\n' "$section" | grep -qE '^- 条件:'; then
    if [[ "$perceptual" == なし* ]]; then
      approval="事前承認（issue #$n の「merge の事前承認」）"
    else
      pre_blocked="issue #$n に事前承認はあるが --judge no-perceptual-external=なし が無い（区切りでの承認なら不要）"
    fi
  fi
done
cp_ok=0
if comment_has "merge 承認: head $HEAD_SHA" quote; then cp_ok=1; fi
if [[ "$cp_ok" -eq 1 ]]; then
  approval="${approval:+$approval と }区切りでの承認（PR のコメント）"
elif [[ -n "$pre_blocked" ]]; then
  row script FAIL "事前承認は知覚の成果物・外部影響を含まない PR に使えない" "$pre_blocked"
fi
if [[ -n "$approval" ]]; then row script PASS "merge の承認の写しが記録されている" "$approval"; else
  hint=""
  if comment_has "merge 承認: head $HEAD_SHA.+"; then
    hint="。\`merge 承認: head $HEAD_SHA\` で始まるが行全体が一致しない行がある（行の後ろに余計な文字がある。補足は次の \`>\` の引用行へ）"
  elif comment_has "merge 承認: head $HEAD_SHA"; then
    hint="。承認の行はあるが、同じコメントに \`>\` で始まるユーザー発言の引用行が無い"
  fi
  row script FAIL "merge の承認の写しが記録されている" "issue の「merge の事前承認」も、head に結んだ区切りの承認も無い。期待する書式: owner のコメントの 1 行ぜんたいが \`merge 承認: head $HEAD_SHA\` で、同じコメントに \`>\` で始まる引用行$hint"
fi

# 8. 修正ラウンドの上限（#248。run-issue-loop の段 5）。上限を超えた PR は事前承認では通さず、区切りでの承認だけで通す
ROUNDS_LIMIT=3
rounds_label="修正ラウンドが ${ROUNDS_LIMIT} 回以内（超えたら区切りでの承認）"
if rounds_out="$(review_rounds)"; then
  rounds="${rounds_out% *}"; rounds_unreadable="${rounds_out#* }"
  rounds_note=""
  if [[ "$rounds_unreadable" != "0" ]]; then rounds_note="（rounds を数字で読めない \`review-outcome:\` の行 ${rounds_unreadable} 件は数えず、区切りでの承認で通す）"; fi
  # 読めない行（書き損じ）で上限が外れないよう、1 件でもあれば上限を超えたときと同じく区切りでの承認を求める
  if [[ "$rounds_unreadable" != "0" && "$cp_ok" -ne 1 ]]; then row script FAIL "$rounds_label" "rounds を数字で読めない \`review-outcome:\` の行が ${rounds_unreadable} 件ある。書式（\`review-outcome: rounds=<数字> …\`）を直すか、区切りでの承認（owner のコメントの 1 行ぜんたいが \`merge 承認: head $HEAD_SHA\` で、同じコメントに \`>\` の引用行）が要る"
  elif [[ "$rounds" -lt 0 ]]; then row script PASS "$rounds_label" "\`review-outcome: rounds=<n>\` の行なし（数えない）${rounds_note}"
  elif [[ "$rounds" -le "$ROUNDS_LIMIT" ]]; then row script PASS "$rounds_label" "rounds=${rounds}${rounds_note}"
  elif [[ "$cp_ok" -eq 1 ]]; then row script PASS "$rounds_label" "rounds=${rounds} は上限を超えるが、head に結んだ区切りでの承認がある${rounds_note}"
  else row script FAIL "$rounds_label" "rounds=${rounds} は上限 ${ROUNDS_LIMIT} を超える。issue の「merge の事前承認」では通さない。owner のコメントの 1 行ぜんたいが \`merge 承認: head $HEAD_SHA\` で、同じコメントに \`>\` の引用行が要る${rounds_note}"; fi
else
  row script FAIL "$rounds_label" "\`review-outcome:\` の行を読めない"
fi

# ---- 結果 -----------------------------------------------------------------

VERDICT="merge する"
[[ "$FAILS" -gt 0 ]] && VERDICT="merge しない（FAIL $FAILS 件）"
TABLE="## merge 判定（scripts/merge-pr.sh）"$'\n\n'"head: \`$HEAD_SHA\` / base: $BASE / 判定: $VERDICT"$'\n\n'
TABLE="$TABLE| 条件 | 確認者 | 結果 | 詳細 |"$'\n'"|---|---|---|---|"$'\n'"$ROWS"
printf '%s\n' "$TABLE"
if [[ "$FAILS" -gt 0 ]]; then exit 1; fi
if [[ "$DRY_RUN" -eq 1 ]]; then echo "（--dry-run: コメントも merge もしない）"; exit 0; fi

body_file="$(mktemp)"
trap 'rm -f "$body_file"' EXIT
printf '%s\n' "$TABLE" > "$body_file"
gh pr comment "$PR_NUM" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --body-file "$body_file"
gh pr merge "$PR_NUM" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --squash --match-head-commit "$HEAD_SHA"

# ---- merge 後の手元の topic branch（#227）----------------------------------
# squash merge では main の commit が branch の子孫にならず git branch -d は使えない。先端が merge した head と一致するときだけ -D で消す。
# checkout 中は git branch -D が拒否するので残す（main へ戻す操作はしない）。結果は merge の exit code に影響させない
if [[ "$KEEP_BRANCH" -eq 0 ]]; then
  HEAD_REF="$(jfield headRefName 2>/dev/null || true)"
  if [[ -n "$HEAD_REF" ]] && local_tip="$(git rev-parse --verify -q "refs/heads/$HEAD_REF" 2>/dev/null)"; then
    if [[ "$local_tip" != "$HEAD_SHA" ]]; then
      echo "（手元の branch ${HEAD_REF} は先端が merge した head と違うので残す: push していない commit が無いか確かめ、不要なら git branch -D ${HEAD_REF}）"
    elif git branch -D "$HEAD_REF" >/dev/null 2>&1; then
      echo "手元の branch ${HEAD_REF} を消した（先端が merge した head と一致）"
    else
      echo "（手元の branch ${HEAD_REF} は消せなかった。どこかの worktree で checkout 中なら切り替えてから git branch -D ${HEAD_REF}）"
    fi
  fi
fi
