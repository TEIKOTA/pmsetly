---
name: run-issue-loop
description: Use when one or more GitHub issues should be driven end to end through delegated children - a writer child implements and reports, the owner opens the PR and records both-bash self-tests, a separate-context reviewer child returns blocking findings, fix rounds repeat until none remain, the root merges via scripts/merge-pr.sh, then cleans up and picks the next issue (e.g. "issue を解消して", "#N を子に任せて merge まで", "writer と reviewer で回して").
---

# Run Issue Loop

issue を「writer の子 → PR → 別 context の reviewer の子 → blocking が無くなるまで修正 → root が merge → 次の issue」で回す owner の手順書。各段の正本は括弧内にあり、ここへ複製しない（委譲の規律は [`delegate-work`](../delegate-work/SKILL.md)、owner が自分で実装するときは [`fix-issue`](../fix-issue/SKILL.md)、コンテナの操作は [`agent-containers`](../../../docs/process/agent-containers.md)、権限と承認は ADR [20260918](../../../docs/adr/20260918-adopt-ai-merge-authority.md)・[20261016](../../../docs/adr/20261016-gate-merge-behind-script-and-recorded-approval.md)）。この skill が足すのは順序と「次に何を確かめるか」だけ。

## 0. 入口（loop を始める前に 1 回）

- 対象の issue を選ぶ。仕様が十分（Scope・Done When がある）で `authority:adr` でないものから。`authority:adr` や「決めること」が本文にある issue は利用者の決定が先（[`decide-or-proceed`](../decide-or-proceed/SKILL.md)）。着手前の重複確認は `gh issue list --state all` / `gh pr list --state all`（AGENTS.md 開発フロー）。
- 枠: `ListAgents` と `scripts/agent-box.sh list` で動いている子を数える。上限 3。レビュー・修正ループの終端までを 1 枠と数える（`delegate-work` 並列度）。Workflow は同時に起動しない。
- 承認の形を決める: issue 本文に「## merge の事前承認」節（`- 条件:` の行）があれば事前承認、無ければ区切りでの承認（ADR 20261016）。利用者の発言を AI が解釈して写すのは避け、無ければ区切りで聞く（下の 7）。

## 1. writer の子

- 依頼文は [`templates/writer.md`](./templates/writer.md) の `<...>` を埋める（5 要素と標準制約は `delegate-work` が正本。雛形は転記契約: `delegate-work` の標準制約ブロックを変えたら雛形も同時に直す）。issue の要点は本文を引用し、子が親の会話を読めない前提で書く。
- 起動: `scripts/agent-box.sh start impl-<N> --branch <type>/<N>-<slug> --prompt-file <依頼文>`（branch 名は `scripts/new-branch.sh` と同じ規約。利用者が model を指定したら `--model <name>` を足す。省略時は account の既定）。
- 待ち: `docker wait agent-<repo>-impl-<N>` をバックグラウンドで 1 回（コンテナ名は `start` の出力の `container`。形は `agent-<repo の小文字>-impl-<N>`。即興の polling は guard が止める）。子の回数・予算の上限（`--max-turns`・`--max-budget-usd`）は agent-box が起動行に付ける（#224。上限で止まった理由は `~/.agent-box/result.json`）。
- 終了後に読む順: issue のコメント（報告の正本）→ `~/agents/<repo>/.sessions/impl-<N>/home/.agent-box/{exit-code,output.log}`。集計行（`PASS: N tests`）は子の本文から写し、記憶で書かない。usage limit で止まった子は `resume impl-<N> --prompt-file <続きの依頼>` で続ける（残った差分の WIP commit を先に指示）。

## 2. owner の取り込みと PR

- `scripts/agent-box.sh collect impl-<N>` → `git branch <b> refs/agents/impl-<N>/heads/<b>` → `git push -u origin <b>`（pre-push は作業ツリーと違う commit では self-test を流さず、その旨を出す）。
- `gh pr create --base main --head <b> --title '<type>(<scope>): …' --body-file <file>`（body に `Closes #<N>`、末尾に会話の attribution）→ `scripts/check-pr.sh <PR番号>`。
- head の SHA を控える（以降の記録はすべてこの SHA に結ぶ。head が変われば取り直し）。

## 3. 検証の記録（両方の Bash）

- ホスト（bash 3.2）: `~/.trashable/<repo>/selftest-<head の先頭 7 桁>/` に `git clone` して head を checkout し、`scripts/selftest-record.sh run --head <SHA> --where host`（約 5 分。バックグラウンドで 1 回待つ）。
- コンテナ（bash 5）: reviewer の子に `scripts/selftest-record.sh run --head <SHA> --where "container review-<N>"` を流させ、その 1 行を報告に書かせる（下の 4）。
- 2 行を stdin に渡して `scripts/selftest-record.sh emit --head <SHA>` に通し、 `self-test: head <SHA> bash=PASS /bin/bash=PASS` と `>` の行を作り、owner が PR にコメントする（script は owner のコメントだけ数える）。

## 4. reviewer の子（別 context）

- 依頼文は [`templates/reviewer.md`](./templates/reviewer.md)。head を固定して渡し、観点（全件・振る舞い・退行注入の別の外し方・Bash 3.2・Scope 外）と出力の型（`## 独立レビュー（agent-box の子、別 context）: head …`、結論の先頭に **blocking なし／あり**）を書く。
- 起動: `scripts/agent-box.sh start review-<N> --base refs/heads/<b> --prompt-file <依頼文>`（`--base` は ref 名。SHA は不可）。
- 結論を読んで owner が `review: head <SHA> blocking=なし` を PR にコメントする（blocking ありなら書かない）。non-blocking は同 PR で直すか follow-up issue に起票するか採らないかを決め、同じコメントに `review-outcome: rounds=<n> blocking=<件> non-blocking=<件> rejected=<件>` の 1 行を残す（`rounds` は修正ラウンドの数で、初回のレビューだけなら 0。`blocking` / `non-blocking` は全ラウンドの合計、`rejected` は採らなかった non-blocking。reviewer が rubber stamp か過剰かを後で集計するため）。
- reviewer には test の改変（既存 test の削除・skip・期待の緩和・`MUTATIONS` の削除）を `git diff origin/main...HEAD -- tests/` で列挙させ、issue が求めていなければ blocking にさせる（writer が test を通すために test を変える退行は読むだけでは見落とす）。

## 5. 修正ラウンド

- blocking があれば writer を `resume impl-<N> --prompt-file <修正の依頼>` で続ける（指摘を本文に引用する。子は PR のコメントを読めるが、依頼文に書く）。
- 修正ラウンドは **3 回まで**（初回のレビューを含めてレビュー 4 回）。超えたら merge せず「承認待ち（収束せず）」に積み、区切りで利用者に聞く（往復が収束しない PR は仕様か設計の問題。`decisions.md` 2026-10-27）。`merge-pr.sh` は owner のコメントの `review-outcome: rounds=<n>` の最大値を読み、4 以上なら issue の事前承認だけでは merge せず、head に結んだ区切りでの承認（`merge 承認: head <SHA>`）を求める（#248。行が無ければ数えないので、`review-outcome:` の行は書き忘れない）。
- 取り込み → push で head が変わるので、3 の記録と 4 のレビュー（`review-<N>b` のように別 session 名）を取り直す。前の記録の行は head が違うので script が無視する。2 回目以降の reviewer には前回の head・前回の指摘の一覧・`git diff <前回 head>..<今回 head>` を渡し、「差分とそれが触る箇所だけを見る。前回の指摘は解消／未解消の 2 値で書く。初回以前からあるコードへの新しい指摘は blocking でなければ書かない」と依頼する（毎回 head 全体を見せると古いコードへの新しい指摘で往復が増える）。
- owner が自分で直した場合も同じ（self-test とレビューの取り直し。レビューの子には「owner の修正点」を明記する）。

## 6. merge（root だけ）

- `scripts/merge-pr.sh <PR番号> --head <SHA> --judge scope=<issue の範囲内か> --judge injection=<退行注入の red → green>`（事前承認なら `--judge no-perceptual-external=なし` も）。`--dry-run` で判定表を先に見る。
- 区切りでの承認は、利用者の発言を `merge 承認: head <SHA>` の行と `>` の引用行で PR にコメントしてから流す。auto mode の分類器が merge や承認のコメントを止めたら、回避せず、止められた事実（PR 番号・head）を区切りの報告に書いて利用者の言い回しを求める（2026-10-27 に「Merge Without Review」で承認のコメントまで止まった）。

## 7. 後始末と次の issue

- `scripts/agent-box.sh clean impl-<N>` / `clean review-<N>`（条件を満たせば承認なし）。merge 後は `git pull` で main を進めてから（merge-pr.sh は先端の一致する手元 branch を消す）`scripts/agent-box.sh prune`（古い `origin/main` だと残す側に倒れる）。
- `scripts/hooks/` を変えた PR なら `scripts/setup-user-hooks.sh --claude --codex` で複製を配り直す（SessionStart がずれを警告する）。
- 枠が空いたら 0 に戻って次の issue。区切り（バッチの終わり・usage limit・利用者の判断待ち）では `gh issue list` / `gh pr list` で残作業を列挙し、承認待ちの PR を番号・head・理由で聞く（AGENTS.md 編集ガードレール）。報告には各 PR のラウンド数と却下数（`review-outcome:` の行）を添える。
- 人間の監査を 1 本: 区切りごとに、今回 merge した／承認待ちの PR から 1 本を無作為に選び（選び方を書く。例: `gh pr list` の番号を `jot -r` / `shuf` で 1 つ）、「この PR の diff を読んでください」と提示する。結果（問題なし／見つかった）を `failure-patterns.md` か `decisions.md` に 1 行残す。AI の記録は AI が偽れる（ADR 20261016）ので、人間が無作為に読む経路を残す。
