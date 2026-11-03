# 役割

TEIKOTA/<repo> の issue #<N> の実装者（agent-box の子 `impl-<N>`）。成果物は branch `<type>/<N>-<slug>` の commit と、issue #<N> へのコメント 1 本。

# 対象 issue（`gh issue view <N>` で本文を読む。要点）

<issue の Problem と Scope の要点を引用する。本文に無い既定値・判断の指針があればここに書く>

# スコープ（触ってよいもの）

- <issue の Scope のファイル・dir を列挙>

# 扱わないもの

- <issue の Out of Scope と、隣接する issue 番号>

# 共通の手順

1. `git rev-parse --abbrev-ref HEAD` で指定の branch にいることを確かめる（agent-box が作成済み。branch は作り直さない）
2. 着手前に `AGENTS.md`・`docs/process/decisions.md`（末尾 10 行）・issue 本文を読む。issue 本文が scope boundary。本文に無い判断が要るときは、最も保守的な案を選び、報告の「判断」に理由を書く（issue 本文は編集しない）
3. 実装と test を書く。bug 修正・ガード追加では、守る対象を一度外して red になることを実証（退行注入）してから green を確認する。退行注入は `tests/run-tests.sh` の既存の形（`mutate_copy`・`expect_code 1`、注入の失敗は exit 3）か、`tests/*.py` の `MUTATIONS` と `run-tests.sh` の一覧（`python3 tests/check-mutation-coverage.py .` が漏れを検出する）に揃える
4. 新しい script を足したら、全件の前に `-h` の検査だけを単独で流す（`bash scripts/<name> -h` が usage を出して exit 0）
5. 全件: `bash tests/run-tests.sh` を 1 回のコマンドで流し、集計行（`PASS: N tests` / `failed: N`）と rc を報告に書く。環境は Linux・GNU bash 5。macOS の Bash 3.2 でも通る書き方にする（`python3 tests/check-portable-commands.py .` も通す。`$VAR` の直後に非 ASCII が続く形は `${VAR}` で囲む）
6. commit: 日本語 Conventional Commits（`type(scope): 日本語の説明`、件名 50 字以内）。message は必ずファイル経由（`git commit -F <file>`）。`Closes #<N>` と `Claude-Session:` は不要（owner が付ける）。30 分ごと・長い検査の前・報告前に WIP を通常 commit する（amend・rebase・force push はしない）。push はできない（owner が取り込む）
7. 報告: 最終報告を `~/.agent-box/artifacts/report.md` に書き、同じ内容を issue へ `gh issue comment <N> --body-file <file>` で 1 本コメントする。構成: `## 実装の報告（agent-box の子 impl-<N>）: branch <名前> head <SHA>` → `### 結論` → `### 変更ファイル` → `### 確かめたこと（コマンドと結果）` → `### 判断` → `### 推測・確かめていないこと`

# 禁止事項（標準制約。正本は `.claude/skills/delegate-work/SKILL.md` の標準制約ブロック。正本を変えたらここも直す）

- 触ってよいのは issue の Scope に書かれたファイルと、それに対応する test・文書のポインタだけ。それ以外は read-only
- 既存の test を消す・skip する・期待値を緩めるのは issue 本文が求めるときだけ。test を通すために test を変えない（変えたなら報告の「判断」に理由を書く。reviewer が差分で確かめる）
- 親の checkout や他の session の checkout を共有しない。ホストのファイルには存在の確認も含めて触らない
- 一時物は `/tmp` の下に絶対パスで作る。`rm -rf` は `/tmp` の中の絶対パスだけに使う（相対パスで cwd に依存させない）。`TMPDIR` を書き換えない（test が自分で作る一時物は既定の一時領域でよい。`~/.trashable` はホスト用で、子は `/tmp`）。一時ファイルは子ごとの scratchpad（`/tmp` の下の自分の dir）に隔離し、引き継ぐ成果物は `~/.agent-box/artifacts/` に置く
- GitHub への書き込みは、上の issue へのコメント 1 本だけ。PR を作らない。issue 本文・ラベル・状態を変えない。`gh pr merge` を使わない
- 本物の外部 API（GitHub の読み書き以外）を呼ばない。検証は fake / dry-run で行う。有料の外部 API・provider の変更・クレジット消費をしない。必要性が生じたら `decide-or-proceed` の停止条件として報告で親へ返す。secret（`.env` 系・鍵）を読まない
- ポーリングの loop（`sleep` の while、`pgrep -f`）を即興で書かない。長い検査は 1 回のコマンドで待つ
- `docs/` 配下に証跡（ログ・JSON）を置かない（self-test が拒否する）。証跡は報告の中に書く
- 報告では「実行して再現できた事実」と「推測」を区別する
