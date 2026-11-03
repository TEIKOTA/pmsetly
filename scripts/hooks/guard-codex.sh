#!/usr/bin/env bash
# Codex canonical Bash PreToolUse。ask は未対応なので拒否へ変換する。
set -euo pipefail
# agent-box の子コンテナ内（#126 D16）では安全用の guard を外す。守りはコンテナの境界と L2 トークンが担う。
# 環境変数だけでは外さない（ホストの macOS ではルートが読み取り専用で /.dockerenv を作れない）。
if [ "${AGENT_BOX:-}" = 1 ] && [ -f /.dockerenv ]; then exit 0; fi
# 判定本体を動かせないときは exit 2（Codex では deny、stderr が理由）で止める（#235）。
# 127 等の他の非 0 は Codex では hook の障害で fail-open になり、guard 無しで通る。
if ! command -v python3 >/dev/null 2>&1; then
  echo "guard-codex: python3 が見つからないため Bash を止めます（guard 無しでは通さない。PATH か python3 の導入を直す）" >&2
  exit 2
fi
here="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$here/guard-codex.py" ] || [ ! -f "$here/guard-bash.py" ]; then
  echo "guard-codex: $here の guard-codex.py か guard-bash.py が無いため Bash を止めます（guard 無しでは通さない。scripts/hooks/ を直す）" >&2
  exit 2
fi
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$here/guard-codex.py"
