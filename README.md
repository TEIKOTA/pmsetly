# project-template

新規プロジェクトの初期状態として fetch して使う汎用テンプレート。
issue 駆動・PR 必須・ADR による意思決定記録・規約のローカル検査（lefthook と script）を、どのスタックでも最初から使える形で揃えている。ローカル script が正本で、GitHub Actions は既定オフ。

## 含まれるもの

- `AGENTS.md`（正本）+ `CLAUDE.md`（symlink） — AI エージェント／人間共通の運用ガイド
- `docs/adr/` — ADR テンプレートと初期 ADR（ADR フォーマット / issue 駆動 PR workflow / commit・PR 規約 / カスタムラベル）
- `docs/templates/handoff.md` — セッション引き継ぎ雛形（compact・usage limit 跨ぎの再開をノーコンテキストで可能にする）
- `docs/process/failure-patterns.seed.md` / `failure-patterns.md` — テンプレート所有の既知失敗 seed と、派生 repo の追記を保持するプロジェクト所有ログ
- `docs/process/decisions.md` — ユーザー決定レジスタ（ADR 未満の確定済み嗜好・却下済み案を 1 行で記録し、決定の揮発と再導入を防ぐ）
- `.github/` — PR・issue テンプレート、`labels.yml`、CI 定義（**既定オフ**: `workflows-disabled/` に退避。下記「CI を有効化する場合」参照）
- `scripts/` — 規約の検証（commit 件名・branch 名・PR body・PR 全体 `check-pr.sh`）、repo 初期設定、長時間ジョブの完了待ち waiter
- `tests/` — 検査スクリプトの self-test（`bash tests/run-tests.sh` のローカル実行が正本。bash 3.2 互換）
- `.claude/skills/` — 共有 skill（着手前の認識合わせ grill 系・自律判定 decide-or-proceed・commit 生成・ADR 運用・docs 監査など。一覧は各ディレクトリの `SKILL.md` を参照）。`.agents` は `.claude` への symlink（agents.md / Codex 互換。`.claude` は Claude Code の worktree 機能のため実ディレクトリにする）
- `lefthook.yml` — commit-msg / pre-push フック定義
- `.editorconfig` / `.gitattributes` / `.gitignore` / `LICENSE`（MIT）
- `.claude/settings.json` — Claude Code 用の権限既定と hook 配線（read-only コマンドの allowlist・secret ファイルの Read deny・`scripts/hooks/` の 4 hook: 開始時の現状表示 / Bash ガード / PR 作成・編集後の `check-pr.sh` 検査 / 未コミット差分の Stop 警告。self-test は編集後に自動では流さず、push の前に pre-push（`scripts/run-selftest.sh`）が流す。煩わしい hook は該当行を外せば無効化できる）
- `.codex/hooks.json` — Codex の PreToolUse(Bash) と Stop。Bash 判定は Claude と共有し、未対応の `ask` は専用 adapter で拒否へ変換する。project-local hook は変更後に `/hooks` で review / trust する。[Codex Hooks](https://learn.chatgpt.com/docs/hooks) の canonical Bash（`exec_command` を含む）に対応するが、専門 tool の opt-out・後続 `write_stdin` 入力・任意のコード内の shell 実行を全面的に監視する保証はない。

## 使い方

### 前提ツール

- `gh`（GitHub CLI）— repo 作成・issue / PR 確認・初期設定に使用
- Python 3（`python3`）— hook 設定と一部の self-test に使用
- Ruby（`ruby`）— skill frontmatter の検査に使用
- lefthook — commit-msg / pre-push のローカル hook に使用

Git と Bash も必要。macOS の `/bin/bash` 3.2 で self-test を実行できる。

### 由来を記録して作成する

repo 内の producer は [`scripts/new-project.sh`](./scripts/new-project.sh)。ローカル Git repo
または明示 URL の commit から、新規ディレクトリと `.template-version` を作成する。

```sh
scripts/new-project.sh --source-repo /path/to/project-template --revision <commit> --output /path/to/new-project
# URL を指定した場合だけ明示的に取得する
scripts/new-project.sh --source-url https://github.com/<owner>/project-template.git --revision <commit> --output /path/to/new-project
```

`--revision` は commit SHA または ref。1 回解決した完全 SHA の追跡済み snapshot を生成し、
同じ SHA を記録する。dirty / untracked ファイルと `.git` はコピーしない。実行属性と
symlink を保持し、submodule は未対応として拒否する。既存の出力先（空 directory・file・
symlink を含む）は上書きせず拒否する。親 directory は先に用意する。
commit / object 不在や取得失敗では作成に失敗する。出力先作成後の I/O 失敗では部分出力が
残る場合があるため、表示された理由と生成先を確認する。再実行で既存先を上書きしない。
Git の初期化や GitHub repo の作成は別操作として行う。

```sh
cd /path/to/new-project
git init -b main
```

### GitHub template で作成する（由来不明）

GitHub 上で template repository として使う場合:

```sh
gh repo create <owner>/<name> --template <owner>/project-template --private --clone
```

この経路と手動コピーでは producer が動かないため、由来は「不明」と扱う。
remote 名、repo 名、ファイルの類似性から取得元 commit を推測しない。

### テンプレート repo の初回公開

`project-template` 自体を GitHub へ作成した後、その repo だけを template repository に設定する。

```sh
gh repo edit <owner>/project-template --template
```

生成先の通常 repo では `--template` を設定しない。

## fetch 後チェックリスト

1. この `README.md` をプロジェクトの内容に書き換える（このセクションごと削除）
2. `LICENSE` の年・著者名を確認する
3. `AGENTS.md` の「リポジトリ構成」「コマンド」をプロジェクトに合わせて具体化する
4. `.gitignore` にスタック固有の除外を追記する（例: Python なら `__pycache__/`、Rust なら `target/`）
5. `lefthook install` を実行する（未導入なら `brew install lefthook`）
6. `scripts/setup-user-hooks.sh --claude --codex --git --trashable --worktree-access` を実行して hook をユーザーレベル（`~/.claude`・`~/.codex`・グローバル git 設定）にも配線する（古い branch・未 pull の checkout や Bash guard を通らない経路でもガードが効く。先に `--dry-run` で差分確認可。hook を追加・変更したら再実行、撤去は `--uninstall`）。`--worktree-access` は worktree 標準配置 `~/worktrees` を Claude の `additionalDirectories` と Codex の `writable_roots` に加える（[ADR](docs/adr/20261006-allow-agent-access-to-worktree-root.md)）。Codex は `/hooks` で trust するまで hook を実行しないので、`scripts/check-codex-hooks.sh` で確認する。`--trashable`（macOS のみ。launchctl が要る）は、作業・test 用の一時物の置き場 `~/.trashable/<repo>/` を作り、毎日 12:00 に launchd で掃除する（7 日を超えた項目と、合計 10 GiB を超えた分を古い順に消す。[ADR](docs/adr/20261014-add-trashable-workspace.md)）
7. GitHub に repo を作成後、`scripts/setup-github-repo.sh --prune` を実行する（デフォルトラベル入れ替え＋squash merge・commit title 固定＋**GitHub Actions 無効化**。先に `--dry-run` で確認可。2 回目以降は `--prune` なしで定義の反映のみ）
8. 初期 ADR はテンプレートの決定ログとして日付・本文を保持する
9. プロジェクト固有の技術選定は新しい ADR として記録する（`manage-adrs` skill 参照）

初期コミット前に `git status --short` で対象を確認し、生成ファイルだけを `git add` する。
commit message は `chore: プロジェクト初期化` とする。

## CI を有効化する場合（opt-in）

既定では GitHub Actions を使わず、検証はローカル（lefthook + `bash tests/run-tests.sh` + `scripts/check-pr.sh`）で完結させる。無料枠（private repo 2,000 分/月）はアカウント単位で共有され、枯渇すると全プロジェクトに billing 待ちノイズが波及するため（[ADR](./docs/adr/20260901-disable-github-actions-by-default.md)）。CI を使いたいプロジェクトだけ opt-in する:

1. `git mv .github/workflows-disabled .github/workflows` して commit する
2. `scripts/setup-github-repo.sh --enable-actions` を実行する（repo 設定の Actions 無効化をスキップ。無効化済みの repo は GitHub Settings > Actions > General から有効へ戻す）

注意:

- Actions 無効のまま branch protection の required status checks を設定しない（check が report されず PR が Expected のまま永久にブロックされる）。必須化は workflow を一度実行してから行う
- Dependabot は Actions 無効でも動き続ける（課金なし）
- 無料枠を超過しても課金は発生せず、private repo の job が月次リセットまで起動しなくなるだけ
- workflow を退避したままローカルで試すには `act -W .github/workflows-disabled/` が使える

## テンプレ更新の取り込み

上記 producer で生成したプロジェクトだけが `.template-version` に由来を記録する。
形式は JSON schema v1（`schema_version: 1`、`source`: 取得元 path / URL、`revision`:
完全 commit SHA、`fetched_at`: timezone 付き ISO 8601）。機械検証の正本は
[`scripts/lib/template-provenance.py`](./scripts/lib/template-provenance.py)。この記録は署名や
真正性の証明ではなく、手動コピーされた記録だけで作成経路を認証するものではない。
ファイルを削除すると比較の起点を失う。旧形式を推測して変換したり shell として読み込んだりしない。

利用者がローカル取得元 repo を用意した後、次を実行する:

```sh
scripts/template-diff.sh --project /path/to/new-project --source-repo /path/to/project-template
# 比較先を明示する場合（既定はローカル取得元の HEAD）
scripts/template-diff.sh --project /path/to/new-project --source-repo /path/to/project-template --to <commit>
```

stdout は記録 SHA → 比較先 SHA の upstream 差分、stderr は比較状態。
同じ SHA の場合は「比較可能」で差分が空になる。派生先 working tree との比較や
全 hunk 適用済みの証明ではない。記録された `source` にはアクセスせず、明示された
ローカル repo のみを読み取るので、取得元を移動しても必要 commit があれば比較できる。
fetch・lazy fetch・更新適用は行わない。新 commit の取得は利用者が別途明示的に行う。
metadata 欠落・不正・未対応形式や必要 commit / object 不在（shallow / partial clone を含む）は
理由付き「比較不能」（exit 2）。比較成功は exit 0。sync-docs の他の監査は継続する。

2026-09-05 以前に生成したプロジェクト（`.claude -> .agents` の symlink 構成）は、取り込み時に `rm .claude && git mv .agents .claude && ln -s .claude .agents && git add -A .claude .agents` で実ディレクトリ構成へ反転する（Claude Code の worktree 機能が symlink の `.claude` を拒否するため。[ADR](./docs/adr/20260905-adopt-session-audit-guards-round2.md)）。
必要な hunk だけを選んで適用し、判断した比較起点に合わせて `.template-version` の
`revision` / `fetched_at` を手動更新する（opt-in）。project 所有の
`docs/process/failure-patterns.md` と `docs/process/decisions.md` の追記は保持する。
背景・対応作成経路は [provenance ADR](./docs/adr/20260926-adopt-repo-owned-template-provenance.md)、
手動更新方針は [従来 ADR](./docs/adr/20260706-adopt-template-versioning-and-update-strategy.md) を参照。

## ライセンス

[MIT License](./LICENSE)
