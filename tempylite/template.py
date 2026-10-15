"""Template クラスと描画処理。"""

from __future__ import annotations

from collections import ChainMap
from collections.abc import Mapping

from .errors import TemplateError, TemplateRuntimeError
from .evaluator import Evaluator, Limits
from .lexer import tokenize
from .nodes import For, If, Text, Var
from .parser import Parser
from .undefined import UNDEFINED_MODES


class _Loop:
    """`loop` 変数。"""

    __slots__ = ("index0", "length")

    def __init__(self, length: int):
        self.index0 = 0
        self.length = length

    @property
    def index(self) -> int:
        return self.index0 + 1

    @property
    def first(self) -> bool:
        return self.index0 == 0

    @property
    def last(self) -> bool:
        return self.index0 == self.length - 1


class Template:
    def __init__(
        self,
        source: str,
        undefined: str = "None",
        trim_blocks: bool = True,
        lstrip_blocks: bool = True,
        **limits,
    ):
        if undefined not in UNDEFINED_MODES:
            raise ValueError(f"undefined must be one of {UNDEFINED_MODES!r}, got {undefined!r}")
        self.source = source
        self._evaluator = Evaluator(undefined, Limits(**limits))
        tokens = tokenize(source, trim_blocks, lstrip_blocks)
        self._nodes = Parser(self._evaluator).parse(tokens)

    def render(self, context: Mapping | None = None, **kwargs) -> str:
        data = {**(context or {}), **kwargs}
        out: list = []
        self._render(self._nodes, ChainMap({}, data), out)
        return "".join(out)

    # ---- 描画 ----

    def _eval(self, expr, scope, lineno, col):
        try:
            return self._evaluator.evaluate(expr, scope)
        except TemplateError as e:
            e.set_position(lineno, col)
            raise

    def _render(self, nodes: list, scope: ChainMap, out: list) -> None:
        for node in nodes:
            kind = type(node)
            if kind is Text:
                out.append(node.text)
            elif kind is Var:
                value = self._eval(node.expr, scope, node.lineno, node.col)
                try:
                    out.append(str(value))
                except TemplateError as e:
                    e.set_position(node.lineno, node.col)
                    raise
                except Exception as e:
                    raise TemplateRuntimeError(
                        f"cannot convert value to string: {e}", node.lineno, node.col
                    ) from None
            elif kind is If:
                for branch in node.branches:
                    if self._eval(branch.test, scope, branch.lineno, branch.col):
                        self._render(branch.body, scope, out)
                        break
                else:
                    self._render(node.else_body, scope, out)
            elif kind is For:
                self._render_for(node, scope, out)

    def _render_for(self, node: For, scope: ChainMap, out: list) -> None:
        iterable = self._eval(node.iter, scope, node.lineno, node.col)
        items = self._to_list(iterable, node)
        if not items:
            self._render(node.else_body, scope, out)
            return
        inner = scope.new_child()
        loop = inner["loop"] = _Loop(len(items))
        for i, item in enumerate(items):
            loop.index0 = i
            self._assign(node.target, item, inner, node)
            self._render(node.body, inner, out)

    @staticmethod
    def _to_list(value, node) -> list:
        try:
            return list(value)
        except TypeError:
            raise TemplateRuntimeError(
                f"{type(value).__name__!r} object is not iterable", node.lineno, node.col
            ) from None

    def _assign(self, target, value, scope: ChainMap, node) -> None:
        if isinstance(target, str):
            scope[target] = value
            return
        values = self._to_list(value, node)
        if len(values) != len(target):
            raise TemplateRuntimeError(
                f"cannot unpack {len(values)} values into {len(target)} targets",
                node.lineno,
                node.col,
            )
        for t, v in zip(target, values):
            self._assign(t, v, scope, node)
