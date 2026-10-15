"""式の安全な評価。eval / exec / compile は使わず、ast のホワイトリスト評価を行う。

注意：property は属性アクセスだけで実行される。副作用のあるオブジェクトを
コンテキストに渡さないこと。
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Mapping
from dataclasses import dataclass

from .errors import (
    TemplateError,
    TemplateRuntimeError,
    TemplateSecurityError,
    TemplateSyntaxError,
)
from .undefined import Undefined


@dataclass(frozen=True)
class Limits:
    max_expr_length: int = 1000  # 式の文字数
    max_nodes: int = 500  # AST のノード数
    max_depth: int = 50  # AST のネストの深さ
    max_exponent: int = 100  # ** の指数の絶対値
    max_sequence_size: int = 100_000  # 文字列・リストの * の結果サイズ
    max_block_depth: int = 50  # {% %} のネスト


_ALLOWED_NODES = (
    ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.Name, ast.Attribute, ast.Subscript, ast.Slice,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
)  # fmt: skip

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
}
_UNARYOPS = {
    ast.Not: operator.not_,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Invert: operator.invert,
}
_CMPOPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

# `_` で始まらなくてもサンドボックス脱出に使えるフレーム・コード系の属性
_BLOCKED_ATTRS = frozenset({
    "gi_frame", "gi_code", "cr_frame", "cr_code", "ag_frame", "ag_code",
    "f_globals", "f_locals", "f_builtins", "f_back", "f_code",
    "tb_frame", "tb_next", "func_globals", "mro",
})  # fmt: skip

_SEQUENCES = (str, bytes, list, tuple)
_MISSING = object()


class Evaluator:
    def __init__(self, undefined: str = "None", limits: Limits | None = None):
        self.undefined = undefined
        self.limits = limits or Limits()
        self._handlers = {
            ast.Constant: lambda n, s: n.value,
            ast.List: lambda n, s: [self._ev(e, s) for e in n.elts],
            ast.Tuple: lambda n, s: tuple(self._ev(e, s) for e in n.elts),
            ast.Set: lambda n, s: {self._ev(e, s) for e in n.elts},
            ast.Dict: self._dict,
            ast.Name: self._name,
            ast.Attribute: self._attribute,
            ast.Subscript: self._subscript,
            ast.Slice: self._slice,
            ast.BinOp: self._binop,
            ast.UnaryOp: self._unaryop,
            ast.BoolOp: self._boolop,
            ast.Compare: self._compare,
            ast.IfExp: self._ifexp,
        }

    # ---- コンパイル（構文解析と検証） ----

    def compile(self, source: str) -> ast.expr:
        src = source.strip()
        if not src:
            raise TemplateSyntaxError("empty expression")
        if len(src) > self.limits.max_expr_length:
            raise TemplateSecurityError(
                f"expression is too long (limit: {self.limits.max_expr_length} characters)"
            )
        if "\n" in src:
            src = f"({src})"
        try:
            tree = ast.parse(src, mode="eval")
        except (SyntaxError, ValueError, RecursionError, MemoryError) as e:
            detail = getattr(e, "msg", None) or str(e)
            raise TemplateSyntaxError(f"invalid expression {source.strip()!r}: {detail}") from None
        self._validate(tree.body, 1, [0])
        return tree.body

    def _validate(self, node: ast.AST, depth: int, count: list) -> None:
        limits = self.limits
        if depth > limits.max_depth:
            raise TemplateSecurityError("expression is nested too deeply")
        count[0] += 1
        if count[0] > limits.max_nodes:
            raise TemplateSecurityError("expression is too complex")
        if not isinstance(node, _ALLOWED_NODES):
            raise TemplateSecurityError(f"{type(node).__name__} is not allowed in expressions")
        if isinstance(node, ast.Dict) and None in node.keys:
            raise TemplateSecurityError("dict unpacking is not allowed in expressions")
        ops = ()
        if isinstance(node, ast.BinOp):
            ops, table = (node.op,), _BINOPS
        elif isinstance(node, ast.UnaryOp):
            ops, table = (node.op,), _UNARYOPS
        elif isinstance(node, ast.Compare):
            ops, table = node.ops, _CMPOPS
        for op in ops:
            if type(op) not in table:
                raise TemplateSecurityError(f"operator {type(op).__name__} is not allowed")
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.expr_context, ast.operator, ast.unaryop, ast.boolop, ast.cmpop)):
                continue
            self._validate(child, depth + 1, count)

    # ---- 評価 ----

    def evaluate(self, node: ast.expr, scope: Mapping):
        try:
            return self._ev(node, scope)
        except TemplateError:
            raise
        except (TypeError, ValueError, ArithmeticError, LookupError, AttributeError, MemoryError) as e:
            raise TemplateRuntimeError(f"{type(e).__name__}: {e}") from None

    def _ev(self, node, scope):
        return self._handlers[type(node)](node, scope)

    def _name(self, node, scope):
        if node.id in scope:
            return scope[node.id]
        return Undefined(node.id, self.undefined)

    def _dict(self, node, scope):
        return {self._ev(k, scope): self._ev(v, scope) for k, v in zip(node.keys, node.values)}

    def _slice(self, node, scope):
        parts = (node.lower, node.upper, node.step)
        return slice(*(None if p is None else self._ev(p, scope) for p in parts))

    def _ifexp(self, node, scope):
        return self._ev(node.body if self._ev(node.test, scope) else node.orelse, scope)

    def _boolop(self, node, scope):
        is_and = isinstance(node.op, ast.And)
        result = None
        for value in node.values:
            result = self._ev(value, scope)
            if bool(result) != is_and:
                break
        return result

    def _unaryop(self, node, scope):
        return _UNARYOPS[type(node.op)](self._ev(node.operand, scope))

    def _compare(self, node, scope):
        left = self._ev(node.left, scope)
        for op, comparator in zip(node.ops, node.comparators):
            right = self._ev(comparator, scope)
            if not _CMPOPS[type(op)](left, right):
                return False
            left = right
        return True

    def _binop(self, node, scope):
        left = self._ev(node.left, scope)
        right = self._ev(node.right, scope)
        op = type(node.op)
        limits = self.limits
        if op is ast.Pow:
            if isinstance(right, (int, float)) and abs(right) > limits.max_exponent:
                raise TemplateSecurityError(f"exponent is too large (limit: {limits.max_exponent})")
        elif op is ast.Mult:
            for seq, n in ((left, right), (right, left)):
                if isinstance(seq, _SEQUENCES) and isinstance(n, int) and len(seq) * n > limits.max_sequence_size:
                    raise TemplateSecurityError(
                        f"repeated sequence is too large (limit: {limits.max_sequence_size})"
                    )
        elif op is ast.Mod and isinstance(left, (str, bytes)):
            raise TemplateSecurityError("string formatting with % is not allowed")
        return _BINOPS[op](left, right)

    def _attribute(self, node, scope):
        obj = self._ev(node.value, scope)
        key = node.attr
        if isinstance(obj, Undefined):
            return getattr(obj, key)
        if isinstance(obj, Mapping) and key in obj:
            return obj[key]
        self._check_attr(key)
        value = getattr(obj, key, _MISSING)
        return self._undefined(obj, key) if value is _MISSING else value

    def _subscript(self, node, scope):
        obj = self._ev(node.value, scope)
        key = self._ev(node.slice, scope)
        try:
            return obj[key]
        except (LookupError, TypeError):
            pass
        if isinstance(key, str) and not (key.startswith("_") and isinstance(obj, Mapping)):
            self._check_attr(key)
            value = getattr(obj, key, _MISSING)
            if value is not _MISSING:
                return value
        return self._undefined(obj, key)

    @staticmethod
    def _check_attr(key: str) -> None:
        if key.startswith("_") or key in _BLOCKED_ATTRS:
            raise TemplateSecurityError(f"access to attribute {key!r} is not allowed")

    def _undefined(self, obj, key) -> Undefined:
        return Undefined(f"{type(obj).__name__}[{key!r}]", self.undefined)
