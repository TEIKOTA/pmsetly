# pmset の権限を「実行ユーザー限定・完全一致」の sudoers 規則で取る

## Status

accepted

## Situation

- pmsetly は `pmset -a disablesleep 0/1` を切り替えるだけの公開 OSS。誰でも数分で全コードを読めることを機能より優先する（`docs/spec.md`）。
- `pmset` の設定変更には root が要る。配布はソースからのビルドのみで、署名・公証はしない。

## Context

- 切り替えのたびにパスワードを求めると使われない（ユーザーの判断、2026-11-03）。
- 常駐 helper（SMAppService 等）は署名と daemon が前提で、コードが大きくなり読めなくなる。

## Material for decision

- 2026-11-03 の grill-me / grill-spec（issue #1）。
- 比較した案: 毎回 AppleScript の管理者認証／sudoers 規則／特権 helper。

## Decision

- `install.sh` が `/etc/sudoers.d/pmsetly` に 1 行だけ書く: 実行ユーザー（`$SUDO_USER`）に、`/usr/bin/pmset -a disablesleep 0` と `/usr/bin/pmset -a disablesleep 1` の完全一致だけを NOPASSWD で許す。書く前に `visudo -c` で検証し、`0440 root:wheel` で置く。
- アプリは `sudo -n` で実行する。アプリ自身は root でファイルを書かない。
- 却下: 毎回の認証（使われない）、特権 helper（最小・可読の方針に反する）、`%admin` への許可（範囲が広い）。

## Consequences

- 良い面: 初回 1 回の `sudo ./install.sh` 以降は無言で切り替わる。権限周りのコードが `sudo -n` の 1 行で済み、system に残るのは 1 ファイルで `sudo rm` 1 回で消せる。
- トレードオフ: そのユーザーで動く任意のプロセスが、パスワードなしでスリープ防止を切り替えられる（影響はスリープ設定のみ）。
- install.sh を実行しないと切り替えは失敗し、メニューに案内を出す。
