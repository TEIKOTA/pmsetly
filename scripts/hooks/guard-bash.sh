#!/usr/bin/env bash
# Claude Code の PreToolUse(Bash) hook。判定本体は同じ場所の guard-bash.py。
# stdin は Claude Code の hook JSON のまま Python へ渡す。Bash 3.2 互換。
set -u

# agent-box の子コンテナ内（#126 D16）では安全用の guard を外す。守りはコンテナの境界と L2 トークンが担う。
# 環境変数だけでは外さない（ホストの macOS ではルートが読み取り専用で /.dockerenv を作れない）。
if [ "${AGENT_BOX:-}" = 1 ] && [ -f /.dockerenv ]; then exit 0; fi
# 判定本体を動かせないときは通さず止める（fail-closed, #235）。exit 2 は Claude Code の block で、stderr が理由として利用者に見える。
# 復旧は Edit / Write tool か手作業で python3 の PATH・scripts/hooks/ を直す。
if ! command -v python3 >/dev/null 2>&1; then
  echo "guard-bash: python3 が見つからないため Bash を止めます（guard 無しでは通さない。PATH か python3 の導入を直す）" >&2
  exit 2
fi
here="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$here/guard-bash.py" ]; then
  echo "guard-bash: $here/guard-bash.py が無いため Bash を止めます（guard 無しでは通さない。scripts/hooks/ を直す）" >&2
  exit 2
fi
exec python3 "$here/guard-bash.py"
