# Architecture Decision Records (ADR)

このディレクトリには、本プロジェクトのアーキテクチャやチーム運用に関する重要な意思決定を「決定のログ」として記録する。

## なぜ ADR を書くのか

- 過去の意思決定の背景・動機が暗黙知になるのを防ぐ
- 非同期コミュニケーションでの前提・背景の認識合わせを速くする
- 「なぜそうしたか」を誰でも後から振り返れるようにする

採用の経緯そのものは [`20260701-adopt-adr-format.md`](./20260701-adopt-adr-format.md) を参照。

## 運用ルール

- 重要な意思決定を行ったら、このディレクトリに Markdown で 1 ファイル 1 決定として記録する。
- ファイル名は **`YYYYMMDD-title.md`**（例: `20260701-adopt-adr-format.md`）。`title` は内容がわかる kebab-case。
- 仕様書ではなく「決定のログ」として、小さくモジュール化して書く。
- フォーマットは [`template.md`](./template.md) に従う。
- 過去 ADR で変更してよいのは `Status` セクションだけとする。supersede の有無にかかわらず `Situation` 以降の本文は書き換えず、過去 ADR を削除しない。過去の内容を現在の理解で書き直さず、判断の変遷自体を資産として扱う。
- 決定が変わった場合は新しい ADR を追加し、古い方の Status を `deprecated` または `superseded`（後継 ADR を明記）に更新する。
- 部分 supersede（旧 ADR の一部の決定だけを置き換える場合）は、旧 ADR を `accepted` のまま残し、`Status` に 1 行で「置換された条項 / 存続する条項 / 後継 ADR」を追記する。索引には何が上書きされたかを 1 行注記する。

## セクション構成

| セクション | 内容 |
|---|---|
| Status | `proposed` / `accepted` / `rejected` / `deprecated` / `superseded` |
| Situation | 決定時のビジネス上の制約や、会社・チームの状況 |
| Context | 決定が必要になった背後の動機・理由 |
| Material for decision | 決定時に参照した材料（記事・比較資料など） |
| Decision | 最終的な決定内容とその理由 |
| Consequences | 決定によって生じる結果（良い面・トレードオフ） |

## 索引

| 日付 | タイトル | Status |
|---|---|---|
| 2026-07-01 | [ADRフォーマットの採用](./20260701-adopt-adr-format.md) | accepted |
| 2026-07-06 | [issue 駆動・PR 必須の開発ワークフローの採用](./20260706-adopt-issue-driven-pr-workflow.md) | accepted |
| 2026-07-06 | [日本語 Conventional Commits を commit と PR タイトルに適用](./20260706-adopt-commit-and-pr-message-convention.md) | accepted（CI 検査条項のみ 2026-09-01 に部分 supersede） |
| 2026-07-06 | [GitHub デフォルトラベルを廃止しカスタムラベル体系を採用](./20260706-adopt-custom-github-labels.md) | accepted |
| 2026-07-06 | [server-side branch protection の導入を見送る](./20260706-defer-server-side-branch-protection.md) | accepted（CI 強制手段の条項のみ 2026-09-01 に部分 supersede） |
| 2026-07-06 | [テンプレート版数の記録と手動更新戦略の採用](./20260706-adopt-template-versioning-and-update-strategy.md) | accepted（生成経路・形式・保証・metadata コメントを 2026-09-26 に部分 supersede） |
| 2026-07-06 | [ラベル同期の削除を --prune オプトインに限定する](./20260706-clarify-label-sync-prune-behavior.md) | accepted |
| 2026-07-29 | [AI セッション運用ガード（重複確認・失敗ログ・worktree/待機規律）の採用](./20260729-adopt-ai-session-operational-guards.md) | accepted（新規 worktree の標準配置・例外規約のみ 2026-10-02 と 2026-10-14 に部分 supersede） |
| 2026-09-01 | [セッション横断監査に基づく運用ガード第 2 弾の採用](./20260901-adopt-session-audit-guards-v2.md) | accepted（PR 滞留の単一閾値条項のみ 2026-09-26 に部分 supersede） |
| 2026-09-01 | [GitHub Actions を既定オフにしローカル検証を正とする](./20260901-disable-github-actions-by-default.md) | accepted |
| 2026-09-05 | [運用ガード第 2 弾の是正（第 2 ラウンド監査の反映）](./20260905-adopt-session-audit-guards-round2.md) | accepted |
| 2026-09-18 | [AI の merge authority と human review boundary の採用](./20260918-adopt-ai-merge-authority.md) | accepted（HUMAN の承認の形と時点・AUTO 条件 1 の観測手段のみ 2026-10-16 に部分 supersede） |
| 2026-09-26 | [repo 内 producer による template provenance の採用](./20260926-adopt-repo-owned-template-provenance.md) | accepted |
| 2026-09-26 | [二段 PR backlog policy の採用](./20260926-adopt-two-stage-pr-backlog.md) | accepted |
| 2026-10-02 | [worktree の標準配置・終了記録・安全な回収の採用](./20261002-adopt-worktree-lifecycle-management.md) | superseded（2026-10-14 に worktree 管理の撤去 ADR で置換） |
| 2026-10-06 | [worktree 標準配置へのエージェント作業許可の採用](./20261006-allow-agent-access-to-worktree-root.md) | accepted |
| 2026-10-08 | [root 所有 worktree の PR 完了後の承認なし回収の採用](./20261008-allow-root-owned-worktree-reclaim-after-pr.md) | superseded（2026-10-14 に worktree 管理の撤去 ADR で置換） |
| 2026-10-08 | [セッションごとのコンテナ隔離の採用](./20261008-adopt-container-isolated-agent-sessions.md) | accepted（試作の評価で既存 worktree 管理の撤去を 2026-10-14 に決定。片付けで残すものを 2026-10-12 に補足。「新しく始める委譲は子のコンテナ」のみ、宣言つき worktree・調査の委譲を 2026-10-17 に部分 supersede） |
| 2026-10-12 | [agent-box の片付けで子の成果物を残す](./20261012-keep-agent-artifacts-on-clean.md) | accepted |
| 2026-10-12 | [子のコンテナの書き込み層・資源・権限の制限](./20261012-restrict-agent-container-writes-and-resources.md) | accepted |
| 2026-10-14 | [子のコンテナの cache を repo ごとに分け、起動前に容量を確かめる](./20261014-separate-agent-cache-per-repo-and-check-capacity.md) | accepted |
| 2026-10-14 | [merge 済みの子の ref を agent-box.sh prune で消す](./20261014-prune-merged-agent-refs.md) | accepted（HEAD の判定は 20261014-prune-review-sessions-by-commit-search で拡張） |
| 2026-10-14 | [branch を持たない子の HEAD を commit の検索で merge 済みと判定する](./20261014-prune-review-sessions-by-commit-search.md) | accepted |
| 2026-10-14 | [worktree 管理の撤去と、残す guard の範囲](./20261014-remove-worktree-lifecycle-management.md) | accepted（「新しい worktree を作らない」のみ、宣言つきの例外を 2026-10-17 に部分 supersede。組み込み worktree の後始末の ask のみ 2026-10-29 に部分 supersede） |
| 2026-10-14 | [一時物の置き場 ~/.trashable を作り、定期掃除で消す](./20261014-add-trashable-workspace.md) | accepted（`rm -rf` の確認ルールを変えない条項のみ 2026-10-16 に部分 supersede） |
| 2026-10-16 | [確認(ask)を人の判断が要る操作に絞り、一時領域の中の rm -rf は確認なしで通す](./20261016-narrow-ask-to-human-judgement.md) | accepted |
| 2026-10-16 | [merge を専用 script に通し、会話での承認を issue・PR の記録で確かめる](./20261016-gate-merge-behind-script-and-recorded-approval.md) | accepted |
| 2026-10-17 | [Docker の起動を AI に許し、Linux で動かない repo には宣言つきで worktree を許す](./20261017-allow-orb-start-and-declared-worktree-exception.md) | accepted（worktree を作る場所 `~/worktrees/<repo>/<名前>` のみ 2026-10-29 に部分 supersede） |
| 2026-10-17 | [self-test の自動実行を PostToolUse から pre-push へ移す](./20261017-move-selftest-from-posttooluse-to-pre-push.md) | accepted（「push の前には必ず通る」の条項のみ 2026-10-17 に部分 supersede） |
| 2026-10-17 | [checkout 中でない branch の push でも pre-push の検査を走らせ、self-test は流さない旨を表示する](./20261017-run-prepush-checks-for-non-current-branch.md) | accepted |
| 2026-10-29 | [Claude Code 組み込みの worktree（.claude/worktrees/）を worktree の正にする](./20261029-adopt-builtin-claude-worktrees.md) | accepted |
| 2026-11-03 | [pmset の権限を「実行ユーザー限定・完全一致」の sudoers 規則で取る](./20261103-use-scoped-sudoers-rule-for-pmset.md) | accepted |
