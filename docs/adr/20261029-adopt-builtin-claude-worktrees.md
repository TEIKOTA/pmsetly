# 2026/10/29 Claude Code 組み込みの worktree（.claude/worktrees/）を worktree の正にする

## Status
- accepted

[`20261017-allow-orb-start-and-declared-worktree-exception.md`](./20261017-allow-orb-start-and-declared-worktree-exception.md) の「owner が `~/worktrees/<repo>/<名前>` に作る」と、[`20261014-remove-worktree-lifecycle-management.md`](./20261014-remove-worktree-lifecycle-management.md) の「`git worktree remove` は guard が確認（ask）する」を、Claude Code の組み込みが作った worktree について部分 supersede する。その他（一時領域に worktree を作らない規則と guard、worktree の管理 script を戻さないこと、worktree を許すのは宣言した repo だけという条件、`setup-user-hooks.sh --worktree-access`、コンテナへの一本化）は存続する。

## Situation
- ADR 20261014 で自前の worktree 管理を撤去し、ADR 20261017 で「worktree は Linux のコンテナで動かない repo の宣言つきの例外だけ、場所は `~/worktrees/<repo>/<名前>`」と決めた。
- 2026-10-29 の棚卸しでは `~/worktrees/` に 22 dir が残り、直近 1 週間で 4 repo の worktree が更新されていた。後始末の `git worktree remove` は毎回 ask になり、残ったまま増えていた。
- 2026-10-29、利用者が「自前で worktree を管理するのは非効率ではないか」と提起し、公式ドキュメントで組み込みの配置と後片付けを確かめた（issue #251）。branch 名の扱いは同日に利用者が決めた（下の Decision 2）。

## Context
- 自前の配置規約（`~/worktrees/<repo>/<名前>`）には後片付けの仕組みが無く、owner が `git worktree remove` を打つたびに ask で止まる。組み込みは配置と後片付けを Claude Code が持つ。
- 組み込みの branch 名は `worktree-<name>` で、repo の規約 `<type>/<issue>-<slug>`（pre-push で検証）と合わない。折り合いの付け方を決める必要がある。
- `.claude/worktrees/` は repo の中にあるので、無視しないと main checkout に untracked として出る。

## Material for decision
- 公式ドキュメント（2026-10-29 に `curl -s` で取得して確認）:
  - https://code.claude.com/docs/en/worktrees.md
  - https://code.claude.com/docs/en/hooks.md（`WorktreeCreate` / `WorktreeRemove`）
  - https://code.claude.com/docs/en/settings-reference.md（`worktree.*`）
- 公式ドキュメントで確かめた事実:
  - 既定の配置: `claude --worktree <name>`（`-w`）と `EnterWorktree` は、repo の root の `.claude/worktrees/<name>/` に作る。`/tmp` ではない。
  - branch 名: 新しい branch `worktree-<name>` に作る。名前を変える設定は settings に無い（`worktree.*` は `baseRef`・`bgIsolation`・`location`・`sparsePaths`・`symlinkDirectories` で、`location` は Desktop の SSH session の remote 用）。配置や branch を変えるには `WorktreeCreate` hook で既定の処理を丸ごと置き換える。
  - 分岐元: 既定（`worktree.baseRef` = `"fresh"`）は remote の既定 branch（`origin/<default-branch>`）。
  - 後片付け（対話の session の終了時）: 変更が無ければ、名前の無い session は worktree と branch を自動で消し、名前つきの session は確認する。変更・untracked・新しい commit があれば、残すか消すかを確認する。worktree が自分の branch 以外の branch（開始点より先の commit がある）を checkout していれば確認し、どちらを選んでもその branch と commit は残す（消すのは dir と `worktree-<name>` の branch）。
  - subagent・background session の worktree: 変更が無ければ終了時に消す。変更があれば残し、定期の sweep が `cleanupPeriodDays` より古いものを消すが、変更・untracked・未 push の commit が残る worktree、背景に回していない `--worktree` session の worktree（古さに関係なく）、`git worktree add` で自分で作った worktree は sweep も残す。sweep が残したものは `git worktree remove` で消す（公式の案内）。実行中は `git worktree lock` を持つ。
  - `-p`（非対話）の実行は終了時の確認が無いので後片付けしない。lock も後の session の sweep が外すまで残る。
  - `WorktreeCreate` hook が作った worktree は、上の自動の後片付けの対象外で、削除は `WorktreeRemove` hook の責任になる。
  - 公式は `.claude/worktrees/` を `.gitignore` に足すことを勧める。
- 確かめていないこと（この ADR の時点で実機で試していない）:
  - worktree の中で `scripts/new-branch.sh` で branch を移った後、終了時の確認が上の「自分の branch 以外」の扱いどおりに出るか。
  - 名前の無い session で、変更が無いまま規約名の branch に移った場合に自動で消えるか（開始点より先の commit が無ければ確認なしで消える可能性がある。branch 自体は残る記述）。
  - Codex など Claude Code 以外のツールから `.claude/worktrees/` の worktree を使ったときの扱い（組み込みの後片付けは Claude Code の session にしか効かない）。
  - 本 repo の guard（`guard-bash.py`）が組み込みの worktree 作成の経路（Claude Code の内部処理）を検査しないこと（Bash tool を通らないため、と推測）。
- 剪定した案: `WorktreeCreate` hook で規約名の branch を作る（下の Decision 2）／`~/worktrees` のまま後片付けの script を書く（ADR 20261014 で撤去したものが戻る）／配置先を `~/worktrees` に変える設定を待つ（ローカルの配置先の設定は無い）。

## Decision
1. **worktree の正**: ホストで worktree を使うときは、Claude Code の組み込み（`claude --worktree <name>` / `EnterWorktree`）で repo 内の `.claude/worktrees/<name>/` に作る。worktree を使ってよい場合（Linux のコンテナで動かない repo の宣言、ADR 20261017）は変えない。新しく `~/worktrees/<repo>/<名前>` に作らない。既存の `~/worktrees` 配下は残し、畳むかどうかは対象を列挙して利用者が決める。
2. **branch 名**: worktree に入ったら、編集・commit の前にその中で `scripts/new-branch.sh <type> <issue番号> <slug>` を打って規約名の branch に移る。`worktree-<name>` の branch では push しない（pre-push の命名検証が拒否する）。
   - 却下: `WorktreeCreate` hook で規約名の branch を作る。hook を使うと組み込みの後片付けの対象から外れ、worktree と branch の削除が `WorktreeRemove` hook（自前の script）の責任になる。撤去した自前の管理が hook の形で戻る。
3. **後片付け**: 組み込みが作った worktree の後片付けは、組み込みの終了時の確認と sweep に任せる。ただし作業（変更・untracked・未 push の commit）が残る worktree は終了時に「残す」を選べば残り、sweep も消さない。owner が `git worktree remove` を打つ場面（作業が残って残した worktree、`-p` の実行の残り、既存の `~/worktrees`）は今までどおり guard が確認（ask）する。ask を自動で判定する仕組みは別 issue（#250）で扱う。
4. **`.gitignore`**: `.claude/worktrees/` を足す。
5. **SessionStart**: `scripts/hooks/session-start.sh` は、`git worktree list` のうち main worktree の `.claude/worktrees/` 配下のものを、別の節で branch・未コミット件数・lock つきで出す。`~/worktrees/<repo>/` の列挙（#213）は既存の worktree のために残す。
6. **存続**: 一時領域（`/tmp` 等）への worktree 作成の拒否（Bash guard・Codex guard・git の post-checkout guard）は、Codex・script 経由の保険として残す。`setup-user-hooks.sh --worktree-access` も既存の `~/worktrees` のために残す。

## Consequences
- 配置と後片付けを Claude Code が持つので、`~/worktrees` に worktree が溜まり、`git worktree remove` のたびに ask で止まる流れが新しく増えない。
- 受け入れるトレードオフ:
  - worktree に入るたびに `new-branch.sh` を 1 回打つ手間が残る。打ち忘れると `worktree-<name>` の branch に commit が乗り、push の時点で命名検証に止められる。
  - `-p` の実行の worktree は後片付けされないので、使えば手で消す（ask）ことになる。
  - `.claude/worktrees/` は repo の中にあるので、`.gitignore` を見ない検索や、tree を直接たどる test が worktree の中身を拾いうる（`rg` は `.gitignore` を見るので除外される）。
  - 組み込みの仕様（配置・branch 名・後片付け）は Claude Code の版で変わりうる。変わったら本 ADR の事実の節を確かめ直す。
- テンプレート更新で派生 repo へ文言が写る。派生 repo の `## 委譲の作業場所` の宣言との整合は、次のテンプレート反映の issue で確かめる。
