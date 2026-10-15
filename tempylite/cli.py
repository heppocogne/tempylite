"""コマンドラインインターフェイス：tempylite TEMPLATE [--toml FILE] [--json FILE]"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .errors import TemplateError
from .template import Template
from .undefined import UNDEFINED_MODES

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


class _CliError(Exception):
    pass


def _read_text(path: str) -> str:
    try:
        if path == "-":
            return sys.stdin.read()
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise _CliError(f"{path}: cannot read file: {e}") from None


def _load_data(path: str, fmt: str) -> dict:
    text = _read_text(path)
    try:
        if fmt == "toml":
            if tomllib is None:
                raise _CliError("TOML support requires Python 3.11+ or the 'tomli' package")
            data = tomllib.loads(text)
        else:
            data = json.loads(text)
    except (ValueError, TypeError) as e:  # JSONDecodeError / TOMLDecodeError
        raise _CliError(f"{path}: invalid {fmt.upper()}: {e}") from None
    if not isinstance(data, dict):
        raise _CliError(f"{path}: top-level value must be an object/table")
    return data


def _parse_define(text: str) -> tuple:
    key, sep, value = text.partition("=")
    if not sep or not key:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {text!r}")
    return key, value


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tempylite",
        description="テンプレートファイルを描画して標準出力（または -o のファイル）に書き出す。",
    )
    p.add_argument("template", help="テンプレートファイル（'-' で標準入力）")
    p.add_argument("--toml", action="append", default=[], metavar="FILE", help="TOML のデータファイル（複数可）")
    p.add_argument("--json", action="append", default=[], metavar="FILE", help="JSON のデータファイル（複数可）")
    p.add_argument("-D", "--define", action="append", default=[], type=_parse_define, metavar="KEY=VALUE",
                   help="文字列変数を追加（複数可）。データファイルより優先")
    p.add_argument("-o", "--output", metavar="FILE", help="出力先ファイル（省略時は標準出力）")
    p.add_argument("--undefined", choices=UNDEFINED_MODES, default="None",
                   help="未定義変数の扱い（デフォルト: None）。strict でエラー")
    p.add_argument("--no-trim-blocks", action="store_true", help="trim_blocks を無効にする")
    p.add_argument("--no-lstrip-blocks", action="store_true", help="lstrip_blocks を無効にする")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    # 同じ種類内は指定順、種類間は --toml → --json → -D の順で後勝ち
    sources = [(f, "toml") for f in args.toml] + [(f, "json") for f in args.json]
    try:
        if sum(1 for f in [args.template] + [s[0] for s in sources] if f == "-") > 1:
            raise _CliError("standard input ('-') can be used only once")
        context: dict = {}
        for path, fmt in sources:
            context.update(_load_data(path, fmt))
        context.update(args.define)
        source = _read_text(args.template)
        try:
            template = Template(
                source,
                undefined=args.undefined,
                trim_blocks=not args.no_trim_blocks,
                lstrip_blocks=not args.no_lstrip_blocks,
            )
            output = template.render(context)
        except TemplateError as e:
            pos = f":{e.lineno}:{e.col}" if e.lineno is not None else ""
            raise _CliError(f"{args.template}{pos}: {type(e).__name__}: {e.message}") from None
        try:
            if args.output:
                with open(args.output, "w", encoding="utf-8", newline="") as f:
                    f.write(output)
            else:
                sys.stdout.write(output)
        except OSError as e:
            raise _CliError(f"{args.output or 'stdout'}: cannot write output: {e}") from None
    except _CliError as e:
        print(f"tempylite: error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
