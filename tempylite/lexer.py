"""字句解析：テンプレート文字列を TEXT / VAR / BLOCK トークン列にする。"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass

from .errors import TemplateSyntaxError

TEXT = "TEXT"
VAR = "VAR"
BLOCK = "BLOCK"
COMMENT = "COMMENT"

_OPEN = re.compile(r"\{[{%#]")
_CLOSERS = {"{": "}}", "%": "%}"}
_OPENERS = {"{": "{{", "%": "{%", "#": "{#"}


@dataclass
class Token:
    type: str
    value: str
    lineno: int
    col: int
    strip_before: bool = False  # {{- / {%- / {#-
    strip_after: bool = False  # -}} / -%} / -#}


def _find_end(src: str, pos: int, closer: str) -> int:
    """クォートと波括弧の入れ子を追跡しながら closer の位置を返す。無ければ -1。"""
    quote = None
    depth = 0
    i, n = pos, len(src)
    while i < n:
        c = src[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "{":
            depth += 1
        elif depth == 0 and src.startswith(closer, i):
            return i
        elif c == "}":
            depth -= 1 if depth else 0
        i += 1
    return -1


def _scan(source: str) -> list:
    line_starts = [0] + [m.end() for m in re.finditer("\n", source)]

    def position(i: int):
        line = bisect_right(line_starts, i)
        return line, i - line_starts[line - 1] + 1

    tokens: list = []
    i, n = 0, len(source)
    while i < n:
        m = _OPEN.search(source, i)
        if m is None:
            tokens.append(Token(TEXT, source[i:], *position(i)))
            break
        start = m.start()
        if start > i:
            tokens.append(Token(TEXT, source[i:start], *position(i)))
        kind = source[start + 1]
        lineno, col = position(start)
        body_start = start + 2
        if kind == "#":
            end = source.find("#}", body_start)
            closer = "#}"
        else:
            closer = _CLOSERS[kind]
            end = _find_end(source, body_start, closer)
        if end == -1:
            raise TemplateSyntaxError(f"unclosed '{_OPENERS[kind]}'", lineno, col)
        content = source[body_start:end]
        strip_before = content.startswith("-")
        if strip_before:
            content = content[1:]
        strip_after = bool(content) and content.endswith("-")
        if strip_after:
            content = content[:-1]
        ttype = {"{": VAR, "%": BLOCK, "#": COMMENT}[kind]
        tokens.append(Token(ttype, content, lineno, col, strip_before, strip_after))
        i = end + len(closer)
    return tokens


def _is_tag(tok: Token) -> bool:
    return tok.type in (BLOCK, COMMENT)


def tokenize(source: str, trim_blocks: bool = True, lstrip_blocks: bool = True) -> list:
    tokens = _scan(source)

    # 空白制御は元のテキストに対して行う（lstrip → trim → 手動の順）
    if lstrip_blocks:
        for i, tok in enumerate(tokens):
            if not _is_tag(tok) or i == 0 or tokens[i - 1].type != TEXT:
                continue
            prev = tokens[i - 1]
            idx = prev.value.rfind("\n")
            if idx == -1 and i - 1 != 0:
                continue  # 同じ行に別のタグがあるので行頭ではない
            if prev.value[idx + 1:].strip(" \t") == "":
                prev.value = prev.value[: idx + 1]

    if trim_blocks:
        for i, tok in enumerate(tokens[:-1]):
            nxt = tokens[i + 1]
            if _is_tag(tok) and nxt.type == TEXT:
                if nxt.value.startswith("\r\n"):
                    nxt.value = nxt.value[2:]
                elif nxt.value.startswith("\n"):
                    nxt.value = nxt.value[1:]

    for i, tok in enumerate(tokens):
        if tok.type == TEXT:
            continue
        if tok.strip_before and i > 0 and tokens[i - 1].type == TEXT:
            tokens[i - 1].value = tokens[i - 1].value.rstrip()
        if tok.strip_after and i + 1 < len(tokens) and tokens[i + 1].type == TEXT:
            tokens[i + 1].value = tokens[i + 1].value.lstrip()

    return [t for t in tokens if t.type != COMMENT and not (t.type == TEXT and t.value == "")]
