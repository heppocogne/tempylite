"""例外クラス。行・列番号（1 始まり）を保持する。"""

from __future__ import annotations


class TemplateError(Exception):
    def __init__(self, message: str, lineno: int | None = None, col: int | None = None):
        super().__init__(message)
        self.message = message
        self.lineno = lineno
        self.col = col

    def set_position(self, lineno: int, col: int) -> None:
        """位置が未設定の場合のみ設定する（内側で付いた位置を優先）。"""
        if self.lineno is None:
            self.lineno, self.col = lineno, col

    def __str__(self) -> str:
        if self.lineno is None:
            return self.message
        return f"{self.message} (line {self.lineno}, column {self.col})"


class TemplateSyntaxError(TemplateError):
    """コンパイル時の構文エラー。"""


class TemplateSecurityError(TemplateError):
    """禁止操作、または DoS 対策の上限超過。"""


class TemplateRuntimeError(TemplateError):
    """描画時の評価エラー（型エラー、ゼロ除算など）。"""


class UndefinedError(TemplateError):
    """strict モードで未定義変数を文字列化したとき。"""
