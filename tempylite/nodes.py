"""構文木のノード定義。"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Union

# for のターゲット：名前、または（ネスト可能な）名前のタプル
Target = Union[str, tuple]


@dataclass
class Text:
    text: str


@dataclass
class Var:
    expr: ast.expr
    lineno: int
    col: int


@dataclass
class Branch:
    test: ast.expr
    body: list
    lineno: int
    col: int


@dataclass
class If:
    branches: list  # list[Branch]
    else_body: list = field(default_factory=list)


@dataclass
class For:
    target: Target
    iter: ast.expr
    body: list
    else_body: list
    lineno: int
    col: int
