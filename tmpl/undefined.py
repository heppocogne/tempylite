"""未定義値を表す Undefined。"""

from __future__ import annotations

from .errors import UndefinedError

UNDEFINED_MODES = ("None", "", "strict")


class Undefined:
    """未定義変数・属性・キーの結果。連鎖アクセスしても Undefined のまま。"""

    __slots__ = ("_name", "_mode")

    def __init__(self, name: str, mode: str = "None"):
        self._name = name
        self._mode = mode

    def __str__(self) -> str:
        if self._mode == "strict":
            raise UndefinedError(f"{self._name!r} is undefined")
        return self._mode

    def __repr__(self) -> str:
        return f"Undefined({self._name!r})"

    def __bool__(self) -> bool:
        return False

    def __getattr__(self, key: str) -> "Undefined":
        if key.startswith("_"):
            raise AttributeError(key)
        return Undefined(f"{self._name}.{key}", self._mode)

    def __getitem__(self, key) -> "Undefined":
        return Undefined(f"{self._name}[{key!r}]", self._mode)

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0

    def __contains__(self, item) -> bool:
        return False

    def __eq__(self, other) -> bool:
        return isinstance(other, Undefined)

    def __hash__(self) -> int:
        return hash(Undefined)
