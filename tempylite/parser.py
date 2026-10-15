"""トークン列からノード木を構築する。"""

from __future__ import annotations

import ast
import re

from . import lexer
from .errors import TemplateError, TemplateSyntaxError
from .evaluator import Evaluator
from .nodes import Branch, For, If, Text, Var

_TAG = re.compile(r"(\w+)\s*(.*)", re.S)
_FOR = re.compile(r"(.+?)\s+in\s+(.+)", re.S)


class _Frame:
    def __init__(self, kind: str, token=None):
        self.kind = kind
        self.token = token
        self.body: list = []
        self.in_else = False
        self.else_body: list = []
        self.main_body: list = []
        # if
        self.branches: list = []
        self.test = None
        self.test_token = token
        # for
        self.target = None
        self.iter = None


def _target(node: ast.AST):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Tuple) and node.elts:
        return tuple(_target(e) for e in node.elts)
    raise ValueError


class Parser:
    def __init__(self, evaluator: Evaluator):
        self.evaluator = evaluator

    def parse(self, tokens: list) -> list:
        root = _Frame("root")
        stack = [root]
        for tok in tokens:
            top = stack[-1]
            if tok.type == lexer.TEXT:
                top.body.append(Text(tok.value))
            elif tok.type == lexer.VAR:
                top.body.append(Var(self._expr(tok, tok.value), tok.lineno, tok.col))
            else:
                self._block(tok, stack)
        if len(stack) > 1:
            tok = stack[-1].token
            raise TemplateSyntaxError(f"unclosed '{stack[-1].kind}' block", tok.lineno, tok.col)
        return root.body

    def _expr(self, tok, source: str):
        try:
            return self.evaluator.compile(source)
        except TemplateError as e:
            e.set_position(tok.lineno, tok.col)
            raise

    def _block(self, tok, stack: list) -> None:
        err = lambda msg: TemplateSyntaxError(msg, tok.lineno, tok.col)  # noqa: E731
        m = _TAG.fullmatch(tok.value.strip())
        if not m:
            raise err("empty or malformed block tag")
        name, rest = m.group(1), m.group(2).strip()
        top = stack[-1]

        if name in ("if", "for"):
            if len(stack) > self.evaluator.limits.max_block_depth:
                raise err("blocks are nested too deeply")
            frame = _Frame(name, tok)
            if name == "if":
                frame.test = self._expr(tok, rest)
            else:
                fm = _FOR.fullmatch(rest)
                if not fm:
                    raise err("invalid 'for' tag, expected 'for <target> in <expression>'")
                try:
                    frame.target = _target(ast.parse(fm.group(1), mode="eval").body)
                except (SyntaxError, ValueError):
                    raise err(f"invalid 'for' target {fm.group(1)!r}") from None
                frame.iter = self._expr(tok, fm.group(2))
            stack.append(frame)
        elif name == "elif":
            if top.kind != "if" or top.in_else:
                raise err("unexpected 'elif'")
            top.branches.append(Branch(top.test, top.body, top.test_token.lineno, top.test_token.col))
            top.test, top.test_token, top.body = self._expr(tok, rest), tok, []
        elif name == "else":
            if rest:
                raise err("'else' takes no arguments")
            if top.kind not in ("if", "for") or top.in_else:
                raise err("unexpected 'else'")
            if top.kind == "if":
                top.branches.append(Branch(top.test, top.body, top.test_token.lineno, top.test_token.col))
                top.body = top.else_body
            else:
                top.main_body, top.body = top.body, top.else_body
            top.in_else = True
        elif name in ("endif", "endfor"):
            if rest:
                raise err(f"'{name}' takes no arguments")
            expected = name[3:]
            if top.kind == "root":
                raise err(f"unexpected '{name}'")
            if top.kind != expected:
                raise err(
                    f"expected 'end{top.kind}' to close '{top.kind}' "
                    f"(line {top.token.lineno}), got '{name}'"
                )
            stack.pop()
            if expected == "if":
                if not top.in_else:
                    top.branches.append(
                        Branch(top.test, top.body, top.test_token.lineno, top.test_token.col)
                    )
                node = If(top.branches, top.else_body)
            else:
                main = top.main_body if top.in_else else top.body
                node = For(top.target, top.iter, main, top.else_body, top.token.lineno, top.token.col)
            stack[-1].body.append(node)
        else:
            raise err(f"unknown tag '{name}'")
