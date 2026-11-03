#!/usr/bin/env python3
"""shell script が実行する行から、macOS に無い・挙動の違う GNU 専用のコマンドの形を検出する（#212）。

子のコンテナ（Linux）では通る test が、ホスト（macOS の bash 3.2・BSD 系のコマンド）で落ちる。#161 は `timeout`、
#135 は mawk の区間表現。Linux だけで通る書き方を、ホストで流すまで待たずに機械的に止める。
検出する形は下の `RULES`（コマンド名・引数の形・理由）。足すときは理由を添える。

対象は `scripts/` と `tests/` 配下の shell（`*.sh`、拡張子なしで shebang が sh / bash のもの）。
「実行される行」と「文字列」を区別するため、shell の構文を読む（行の grep ではない）:
  - 検査するのはコマンド位置（行頭・`;` `|` `&` `(` の後・`then` `do` 等の後・`$(…)` `` `…` `` の中）の語だけ。
    `env` `exec` `nice` `nohup` `sudo` `xargs` `time` `command` の前置は読み飛ばして、実際のコマンドを見る
    （`time -p`・`eval -- …` の option も読み飛ばす。#237）
  - 配列の代入 `a=(…)`・extglob `@(…)` 等の括弧の中は語の並びで、コマンドではない（中の `$(…)` は読む）。
    `then` `do` `{` の後の関数定義 `f() {` の名前もコマンドではない。`$((…))` の中の `$(…)` は読む（#237）
  - 引用符の中・コメント・heredoc の本体・`--timeout` のような option・リダイレクトの宛先は対象外
    （guard の test の入力文字列 `"timeout 5 gh pr merge 1"` は通る）
  - `bash -c '…'`・`sh -c '…'`・`eval '…'` の文字列は、実行されるのでコマンドとして読み直す
  - `sed -i` は `sed -i ''`（BSD）と `sed -i.bak`（両方）の形を通し、suffix 無しの `sed -i`（GNU だけ）を検出する
  - 見逃しは黙って green にしない: 読めない構文は読み飛ばさず、語として残す（誤検知は fixture と実 tree で確認する）

対象外: stdin 経由の `bash`（`echo … | bash`・`bash <<EOF`）。
対象外（#237）: `env -S "…"` の文字列、`xargs --max-args 1` のような長い option の値の別語、`chrt`・`taskset` の前置、
`$'it\'s'`（ANSI-C の引用符の中の `\'`）の後の語。読み違えて見逃しうる。
`trap '…'` と `find -exec …` は読む（#219）。
対象外（第 1 版）: `tests/*.py` の subprocess の引数（list の先頭）。python の文字列から実行される形を安全に
取り出すには AST を読む必要があり、今の `tests/*.py` は guard の入力文字列が中心で実行される形は無い。必要になったら足す。
`awk` の方言は #135 で対処済み。
使い方: check-portable-commands.py <root>（root 直下の scripts/ と tests/ を再帰で見る）。
該当があれば `path:line: 内容 — 理由` を出して exit 1。
"""
import re
import sys
from pathlib import Path

# (コマンド名, 引数の正規表現 or None, 理由)。引数の正規表現は、そのコマンドの引数のどれかに一致したら該当。
# `-d`・`-c` の前に結合できるのは値を取らない flag（date は `-u` `-R`、stat は `-L` `-f` `-t`）だけとみなす。
# `date -d@5`・`-dyesterday`・`stat -c%s`・`-cL` の結合形は拾い、`date -Iseconds`・`-Idate`・`-Id`（`-I` は値を結合で取る）は通す（#237）。
# None はコマンド名だけで該当。`sed -i` は suffix の有無を見る必要があるので `check_sed_inplace` で別に扱う。
RULES = [
    ("timeout", None, "macOS に無い（coreutils の gtimeout）。待ちは wait-for-marker.sh か python の timeout で書く"),
    ("readlink", r"^(-[A-Za-z]*f[A-Za-z]*|--canonicalize.*)$", "macOS の readlink に -f が無い（古い版）。cd && pwd -P か python で解決する"),
    ("date", r"^(-[uR]*d.*|--date(=.*)?)$", "BSD の date に -d が無い（-j -f / -v）。epoch は python か date -u -r で"),
    ("stat", r"^(-[Lft]*c.*|--format(=.*)?|--printf(=.*)?)$", "BSD の stat に -c が無い（-f で書式が別物）"),
    ("grep", r"^(-[A-Za-z]*P[A-Za-z]*|--perl-regexp)$", "macOS の grep に -P（PCRE）が無い。-E か python で書く"),
    ("find", r"^(-printf|-regextype)$", "BSD の find に -printf・-regextype が無い"),
    ("tac", None, "macOS に無い（tail -r）"),
    ("shuf", None, "macOS に無い"),
    ("md5sum", None, "macOS に無い（md5 -r / shasum）"),
    ("sha1sum", None, "macOS に無い（shasum）"),
    ("sha256sum", None, "macOS に無い（shasum -a 256）"),
    ("flock", None, "macOS に無い"),
    ("setsid", None, "macOS に無い"),
    ("truncate", None, "macOS に無い"),
]
SED_INPLACE_REASON = "suffix 無しの sed -i は GNU だけ（BSD は `-i ''` が要る）。`-i.bak` で書いて消すか python で書く"

# `time` は前置（PREFIXES）として読み、`time -p timeout …` の option を読み飛ばす（#237）
KEYWORDS = {"if", "then", "else", "elif", "while", "until", "do", "!", "{", "}", "in"}
# 前置コマンドが次の語を値として取る option（`nice -n 5 timeout …`）。結合形（`-n5`）は 1 語なので不要
PREFIX_VALUE_OPTS = {
    "nice": {"-n", "--adjustment"},
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-r", "-t", "-U", "-D", "-R", "--user", "--group"},
    "env": {"-u", "-C", "--unset", "--chdir"},
    "xargs": {"-n", "-L", "-I", "-P", "-s", "-d", "-E", "-a"},
    "ionice": {"-c", "-n", "-p", "-P", "-u"},
    "stdbuf": {"-i", "-o", "-e"},
    "time": {"-f", "-o"},
}
# grep が次の語を値（パターン・file・件数）として取る option。`grep -e -P` の `-P` は option でなくパターン
GREP_VALUE_OPT = re.compile(r"^-[A-Za-z]*[efmABC]$")
FIND_EXEC = {"-exec", "-execdir", "-ok", "-okdir"}
PREFIXES = {"env", "exec", "nice", "nohup", "sudo", "xargs", "time", "command", "builtin", "ionice", "stdbuf"}
SHELLS = {"bash", "sh", "zsh", "dash"}
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")
SEPARATORS = ";&|()\n"
# 直後の `(…)` が語の一部になる形: 配列の代入（`a=(…)`・`a+=(…)`・`a[0]=(…)`）と extglob（`@(…)` 等）。
# `!` だけの語の後の `(` は否定の subshell（`if !(timeout 1 x)`）なので含めない
WORD_PAREN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=|.*[?*+@]|.+!)$")


class Word:
    __slots__ = ("value", "quoted", "line", "plain")

    def __init__(self, value, quoted, line, plain=None):
        self.value, self.quoted, self.line = value, quoted, line
        # 最初の引用符より前の部分（`FOO="a b"` なら `FOO=`）。代入の前置の判定に使う
        self.plain = value if plain is None else plain


def match_paren(text, start):
    """text[start] は `(` の直後の位置。対応する `)` の位置を返す（無ければ len）。引用符とバックスラッシュを読み飛ばす。"""
    depth, i, n = 1, start, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c in "'\"":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if (c == '"' and text[j] == "\\") else 1
            i = j + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def match_brace(text, start):
    depth, i, n = 1, start, len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def embedded_commands(text):
    """引用符の中などにある `$(…)` と `` `…` `` の中身（実行される）を (offset, 中身) で返す。"""
    found, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "$" and text.startswith("$(", i) and not text.startswith("$((", i):
            end = match_paren(text, i + 2)
            found.append((i + 2, text[i + 2:end]))
            i = end + 1
            continue
        if c == "`":
            j = i + 1
            while j < n and text[j] != "`":
                j += 2 if text[j] == "\\" else 1
            found.append((i + 1, text[i + 1:j]))
            i = j + 1
            continue
        i += 1
    return found


def line_at(text, pos, base):
    return base + text.count("\n", 0, pos)


def tokenize(text, base, subs):
    """text を単純コマンド（Word の list）に分ける。実行される入れ子（`$(…)`・`bash -c`）は subs に (text, 行) で積む。"""
    commands, ends, words = [], [], []
    cur, started, quoted, start, plain = [], False, False, 0, ""
    paren_depth = 0
    redirect_pending = False
    heredocs = []
    i, n = 0, len(text)

    def end_word():
        nonlocal cur, started, quoted, plain, redirect_pending
        if started:
            if redirect_pending:
                redirect_pending = False
            else:
                words.append(Word("".join(cur), quoted, line_at(text, start, base), plain if quoted else None))
        cur, started, quoted, plain = [], False, False, ""

    def end_command(sep=""):
        nonlocal words
        end_word()
        if words:
            commands.append(words)
            ends.append(sep)
        words = []

    def mark_quoted():
        nonlocal quoted, plain
        if not quoted:
            plain = "".join(cur)
            quoted = True

    def begin(pos):
        nonlocal started, start
        if not started:
            started, start = True, pos

    while i < n:
        c = text[i]
        if c == "\\":
            if text.startswith("\\\n", i):
                i += 2
                continue
            begin(i)
            cur.append(text[i + 1:i + 2])
            i += 2
        elif c in " \t":
            end_word()
            i += 1
        elif c == "#" and not started:
            while i < n and text[i] != "\n":
                i += 1
        elif c == "'":
            begin(i)
            mark_quoted()
            j = text.find("'", i + 1)
            j = n if j < 0 else j
            cur.append(text[i + 1:j])
            i = j + 1
        elif c == '"':
            begin(i)
            mark_quoted()
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            inner = text[i + 1:j]
            for offset, sub in embedded_commands(inner):
                subs.append((sub, line_at(text, i + 1 + offset, base)))
            cur.append(inner)
            i = j + 1
        elif c == "`":
            begin(i)
            j = i + 1
            while j < n and text[j] != "`":
                j += 2 if text[j] == "\\" else 1
            subs.append((text[i + 1:j], line_at(text, i + 1, base)))
            cur.append("`…`")
            i = j + 1
        elif c == "$" and text.startswith("$((", i):
            begin(i)
            end = match_paren(text, i + 2)
            for offset, sub in embedded_commands(text[i + 3:end]):
                subs.append((sub, line_at(text, i + 3 + offset, base)))
            cur.append("$((…))")
            i = end + 1  # end は `))` の 2 つ目の `)`（#237 までは + 2 で、`$((1));timeout` の `;` を落としていた）
        elif c == "$" and text.startswith("$(", i):
            begin(i)
            end = match_paren(text, i + 2)
            subs.append((text[i + 2:end], line_at(text, i + 2, base)))
            cur.append("$(…)")
            i = end + 1
        elif c == "$" and text.startswith("${", i):
            begin(i)
            end = match_brace(text, i + 2)
            for offset, sub in embedded_commands(text[i + 2:end]):
                subs.append((sub, line_at(text, i + 2 + offset, base)))
            cur.append(text[i:end + 1])
            i = end + 1
        elif c in "<>" and text.startswith(c + "(", i):
            begin(i)
            end = match_paren(text, i + 2)
            subs.append((text[i + 2:end], line_at(text, i + 2, base)))
            cur.append("<(…)")
            i = end + 1
        elif c in "<>":
            if started and "".join(cur).isdigit() and not quoted:
                cur, started = [], False  # fd 番号（2>/dev/null の 2）
            else:
                end_word()
            if text.startswith("<<<", i):
                redirect_pending = True
                i += 3
            elif text.startswith("<<", i):
                i += 2
                strip_tabs = text.startswith("-", i)
                i += 1 if strip_tabs else 0
                while i < n and text[i] in " \t":
                    i += 1
                j, delim, delim_quoted = i, [], False
                while j < n and text[j] not in " \t\n;|&<>()":
                    if text[j] in "'\"\\":
                        delim_quoted = True
                    else:
                        delim.append(text[j])
                    j += 1
                heredocs.append(("".join(delim), strip_tabs, delim_quoted))
                i = j
            else:
                i += 1
                while i < n and text[i] in "<>&|-" and not (text[i] == "-" and text[i - 1] not in "&"):
                    i += 1
                redirect_pending = True
        elif c == "&" and text.startswith("&>", i):
            end_word()
            i += 2 + (1 if text.startswith("&>>", i) else 0)
            redirect_pending = True
        elif c == "(" and started and not quoted and WORD_PAREN.match("".join(cur)):
            end = match_paren(text, i + 1)
            for offset, sub in embedded_commands(text[i + 1:end]):
                subs.append((sub, line_at(text, i + 1 + offset, base)))
            cur.append("(…)")
            i = end + 1
        elif c in SEPARATORS:
            function_def = re.match(r"\(\s*\)", text[i:]) if c == "(" else None
            if function_def:
                end_word()
                rest = words
                while len(rest) > 1 and not rest[0].quoted and rest[0].value in KEYWORDS:
                    rest = rest[1:]  # `then timeout() { :; }` の then（#237）
                if len(rest) == 1 or (len(rest) == 2 and rest[0].value == "function"):
                    words = []  # `timeout() { :; }` の関数定義の名前はコマンドではない
                    i += function_def.end()
                    continue
            if c == ")" and paren_depth == 0:
                # 対応する `(` が無い `)` は case の分岐の終わり。`tac|timeout)` の名前はコマンドではない
                end_word()
                words = []
                while ends and ends[-1] == "|":
                    commands.pop()
                    ends.pop()
                redirect_pending = False
                i += 1
                continue
            if c == "(":
                paren_depth += 1
            elif c == ")":
                paren_depth -= 1
            is_pipe = c == "|" and not text.startswith("||", i) and (i == 0 or text[i - 1] != "|")
            end_command("|" if is_pipe else c)
            redirect_pending = False
            i += 1
            if c == "\n" and heredocs:
                for delim, strip_tabs, delim_quoted in heredocs:
                    body_start = i
                    while i < n:
                        eol = text.find("\n", i)
                        eol = n if eol < 0 else eol
                        row = text[i:eol]
                        i = min(eol + 1, n)
                        if (row.lstrip("\t") if strip_tabs else row) == delim:
                            break
                    if not delim_quoted:
                        body = text[body_start:i]
                        for offset, sub in embedded_commands(body):
                            subs.append((sub, line_at(text, body_start + offset, base)))
                heredocs = []
        else:
            begin(i)
            cur.append(c)
            i += 1
    end_command()
    return commands


def check_sed_inplace(args):
    for j, arg in enumerate(args):
        value = arg.value
        if re.match(r"^-[A-Za-z]*i$", value) or value.startswith("--in-place"):
            following = args[j + 1] if j + 1 < len(args) else None
            if value.startswith("--in-place=") or (following and following.quoted and following.value == ""):
                continue
            return SED_INPLACE_REASON
    return None


def analyze(words, hits, subs):
    """1 つの単純コマンド（Word の list）を読み、前置を読み飛ばして実際のコマンドを RULES と照らす。"""
    i, n = 0, len(words)
    while i < n:
        word = words[i]
        value = word.value
        if (not word.quoted and value in KEYWORDS) or ASSIGN.match(word.plain):
            i += 1
            continue
        if not word.quoted and value == "function":
            i += 2  # `function f {` の f は関数名
            continue
        name = value.rsplit("/", 1)[-1]
        args = words[i + 1:]
        reason = None
        rule_args = args
        if name == "grep":
            rule_args, skip = [], False
            for a in args:
                if skip:
                    skip = False
                    continue
                rule_args.append(a)
                skip = bool(GREP_VALUE_OPT.match(a.value))
        for rule_name, pattern, why in RULES:
            if name == rule_name and (pattern is None or any(re.match(pattern, a.value) for a in rule_args)):
                reason = why
                break
        if name == "sed" and reason is None:
            reason = check_sed_inplace(args)
        if reason:
            hits.append((word.line, reason))
        if name in SHELLS:
            for j, arg in enumerate(args):
                if re.match(r"^-[A-Za-z]*c$", arg.value) and j + 1 < len(args):
                    subs.append((args[j + 1].value, args[j + 1].line))
                    break
        elif name == "eval":
            rest = args[1:] if args and args[0].value == "--" else args
            subs.append((" ".join(a.value for a in rest), word.line))
        elif name == "trap":
            rest = [a for a in args if a.value != "--"]
            if rest and not rest[0].value.startswith("-"):
                subs.append((rest[0].value, rest[0].line))
        elif name == "find":
            for j, arg in enumerate(args):
                if arg.value in FIND_EXEC:
                    k = j + 1
                    while k < len(args) and args[k].value not in (";", "+"):
                        k += 1
                    analyze(args[j + 1:k], hits, subs)
        if name in PREFIXES:
            if name == "command" and args and args[0].value in ("-v", "-V"):
                return
            i += 1
            while i < n and not words[i].quoted and words[i].value.startswith("-"):
                option = words[i].value
                i += 1
                if option in PREFIX_VALUE_OPTS.get(name, ()):
                    i += 1
            continue
        return


def scan(text, base=1):
    hits, subs = [], []
    for words in tokenize(text, base, subs):
        analyze(words, hits, subs)
    while subs:
        sub_text, sub_base = subs.pop()
        for words in tokenize(sub_text, sub_base, subs):
            analyze(words, hits, subs)
    return hits


def shell_files(root):
    for base in ("scripts", "tests"):
        for path in sorted((root / base).rglob("*")):
            if not path.is_file() or path.suffix == ".py":
                continue
            if path.suffix == ".sh":
                yield path
            elif path.suffix == "":
                with path.open(encoding="utf-8", errors="replace") as handle:
                    first = handle.readline()
                if first.startswith("#!") and re.search(r"\b(ba|z|da)?sh\b", first):
                    yield path


def main():
    root = Path(sys.argv[1])
    found = []
    for path in shell_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        for line, reason in sorted(set(scan(text))):
            shown = lines[line - 1].strip()[:100] if 0 < line <= len(lines) else ""
            found.append(f"{path.relative_to(root)}:{line}: {shown} — {reason}")
    print("\n".join(found))
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
