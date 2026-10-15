# 簡易テンプレートエンジン 実装計画（Python）

## 1. 目的と範囲

`{{ expression }}` 形式の置換を行う軽量テンプレートエンジンを作る。
第一段階では単純な変数置換のみとし、将来的に Python 記法の安全な式評価と `{% %}` 制御文に拡張する。
最初から「字句解析 → 構文木 → 描画」の 3 層構造で作り、拡張時の作り直しを避ける。

## 2. 決定事項

| 項目 | 決定内容 |
|---|---|
| 置換構文 | `{{ expression }}`。タグ内の前後空白は自由 |
| エスケープ | `{{ '{{' }}` のように文字列リテラル式として出力（Jinja 方式） |
| 未定義変数 | `Undefined` オブジェクトを返す。文字列化はオプションで指定（デフォルト `"None"`、`""`、`"strict"` でエラー） |
| 属性・キー参照 | `obj.key` と `obj["key"]` の両方を許可 |
| `.` の解決順 | Mapping ならキー優先 → 属性（`_` 始まりは禁止） |
| `[]` の解決順 | キー優先 → 属性 |
| 制御文 | `{% if %}…{% endif %}` / `{% for %}…{% endfor %}` の終了タグ方式（インデント方式は採用しない） |
| 空白制御 | `trim_blocks` / `lstrip_blocks` をデフォルト有効。後に `{%-` / `-%}` を追加 |
| 予約構文 | `{%` と `{#` は第一段階では「未対応」エラーとして予約 |
| 式の評価 | `eval` は使わない。`ast.parse(mode="eval")` + ホワイトリスト評価器 |

## 3. 公開 API

```python
from tmpl import Template

t = Template("Hello {{ name }}!", undefined="None")  # "None" | "" | "strict"
t.render({"name": "YY"})        # -> "Hello YY!"
t.render(name="YY")             # キーワード引数でも可
```

- `Template` はコンストラクタでコンパイルし、`render()` を何度でも呼べる
- 例外：`TemplateSyntaxError`（コンパイル時）、`UndefinedError`（strict 時）、`TemplateSecurityError`（禁止操作）。いずれも行・列番号付き

## 4. アーキテクチャ

```
テンプレート文字列
  → Lexer    : TEXT / VAR /（後に BLOCK / COMMENT）トークン列
  → Parser   : ノード木（Text, Var, 後に If, For）
  → Renderer : ノード木を辿り、Evaluator で式を評価して連結
```

### ディレクトリ構成

```
tmpl/
  __init__.py     # Template と例外を公開
  errors.py       # 例外クラス（lineno, col 付き）
  lexer.py        # トークン化
  nodes.py        # ノード定義（dataclass）
  parser.py       # トークン → ノード木
  evaluator.py    # 式の評価
  undefined.py    # Undefined クラス
  template.py     # Template クラス
tests/
  test_lexer.py
  test_parser.py
  test_render.py
  test_security.py   # フェーズ2以降
```

## 5. フェーズ 1：単純置換

### 5.1 Lexer

- 入力を先頭から走査し、`{{` を見つけるまでを TEXT トークンとする
- `{{` 以降は**クォート状態を追跡しながら** `}}` を探す
  - `'` / `"` の内側では `}}` を終端とみなさない
  - バックスラッシュによるエスケープを考慮する
  - これにより `{{ '}}' }}` を正しく扱える
- `{{` が閉じられていない場合、開始位置を付けて `TemplateSyntaxError`
- `{%` / `{#` を検出したら「未対応」エラー（将来の互換性のため）
- 各トークンは `(type, value, lineno, col)` を持つ

### 5.2 式（フェーズ 1 の範囲）

対応するのは次の 2 種類のみ。前後の空白は除去する。

- 識別子：`name`（`str.isidentifier()` で判定）
- 文字列リテラル：`'...'` / `"..."`（`ast.literal_eval` で安全に解釈）

それ以外（空の `{{ }}` を含む）は `TemplateSyntaxError`。
※ フェーズ 2 で AST 評価器に置き換えるため、評価部分は `evaluator.py` に閉じ込めておく。

### 5.3 Undefined

```python
class Undefined:
    def __init__(self, name, mode): ...
    def __str__(self):      # mode に応じて "None" / "" / UndefinedError
    def __bool__(self):     # False（フェーズ3の if 用）
    def __getattr__/__getitem__:  # Undefined を返して連鎖可能に
```

### 5.4 Renderer

- Text ノードはそのまま出力、Var ノードは評価結果を `str()` して出力
- `io.StringIO` または list に追加して最後に `"".join()`

### 5.5 テスト項目

- 単純置換、複数置換、隣接タグ（`{{a}}{{b}}`）
- 空白のバリエーション（`{{x}}` / `{{   x   }}` / タブ）
- エスケープ：`{{ '{{' }}` → `{{`、`{{ '}}' }}` → `}}`、`{{ "it's" }}`
- 未定義：デフォルト `"None"`、`undefined=""`、`undefined="strict"` で例外
- 非文字列値（int, None, list）の文字列化
- エラー：閉じていない `{{`、空の `{{ }}`、不正な式、`{%` 使用時。行・列番号が正しいこと
- `{{` を含まないテキスト、空テンプレート、複数行テンプレート

## 6. フェーズ 2：安全な式評価

### 6.1 方針

`ast.parse(expr, mode="eval")` で Python 構文を解析し、自前の評価器でノードを辿る。`eval` / `exec` / `compile` の実行は一切しない。
解析はコンパイル時に行い、AST をノードに保持しておく。

### 6.2 許可するノード（ホワイトリスト）

| 分類 | ノード |
|---|---|
| リテラル | Constant, List, Tuple, Dict, Set |
| 参照 | Name（Load のみ）, Attribute, Subscript, Slice |
| 演算 | BinOp, UnaryOp, BoolOp, Compare, IfExp |

上記以外はすべて `TemplateSecurityError`。特に以下は明示的に拒否する。
Call, Lambda, 内包表記（ListComp 等）, NamedExpr（`:=`）, JoinedStr（f-string）, Starred, Await, Yield。

### 6.3 参照の解決

- `Name`：コンテキスト dict のみから解決。builtins は見せない。無ければ `Undefined`
- `Attribute`（`obj.key`）
  1. `obj` が Mapping かつ `key in obj` → `obj[key]`
  2. `key` が `_` で始まる → `TemplateSecurityError`
  3. `getattr(obj, key)`、無ければ `Undefined`
- `Subscript`（`obj[key]`）
  1. `obj[key]` を試す
  2. 失敗し、`key` が `_` で始まらない文字列なら `getattr` を試す
  3. 無ければ `Undefined`
- 呼び出し可能オブジェクト（メソッド等）が返った場合も、呼び出し構文が無いので実行されない

### 6.4 DoS 対策

- 式の文字列長の上限（例：1,000 文字）
- AST のノード数・ネストの深さの上限
- `**`：指数の上限（例：100）
- 文字列・リストの `*`：結果サイズの上限（例：100,000）
- 上限値は `Template` のオプションで変更可能にする

### 6.5 注意点

- property は属性アクセスだけで実行される。副作用のあるオブジェクトを渡さないことをドキュメントに明記する
- 将来、関数呼び出しを許可する場合は「明示的に登録した関数のみ」とし、`str.format` 等のメソッド呼び出しは許可しない

### 6.6 テスト項目

- 算術、比較、論理演算、三項演算子、リテラル
- `obj.key` / `obj["key"]` の両方（dict、オブジェクト、ネスト）
- dict キーが優先されること（`d.items` がキー `"items"` の値を返す）
- 拒否されるべき式：
  `().__class__`、`x.__dict__`、`x["__class__"]`、`len(x)`、`(lambda: 1)()`、`[i for i in x]`、`f"{x}"`、`(y := 1)`
- DoS：`9**9**9`、`"a"*10**9`、深いネスト

## 7. フェーズ 3：制御文

### 7.1 構文

```
{% if cond %} … {% elif cond %} … {% else %} … {% endif %}
{% for x in items %} … {% else %} … {% endfor %}
```

- `for` のターゲットは単一の名前とタプルのアンパック（`k, v`）を許可
- ループ変数 `loop`（`index`, `index0`, `first`, `last`, `length`）を提供する

### 7.2 Lexer の拡張

- `{% … %}` を BLOCK トークン、`{# … #}` を COMMENT トークン（出力しない）として認識
- クォートの追跡は `{{ }}` と同じロジックを共有する

### 7.3 Parser

- ブロックのスタックで構造を構築する
  - `if` / `for` で積み、`endif` / `endfor` で取り出す
  - 対応しない終了タグ、閉じられていないブロックは、開始位置付きでエラー
- ノード：`If(branches=[(cond, body)], else_body)`、`For(target, iter, body, else_body)`

### 7.4 スコープ

- ループ変数はループ内のスコープのみ。コンテキストはチェーン（`collections.ChainMap`）で管理する

### 7.5 空白制御

- `trim_blocks`（デフォルト True）：ブロックタグ直後の改行を 1 つ除去
- `lstrip_blocks`（デフォルト True）：ブロックタグの前の、行頭からの空白を除去
- `{%-` / `-%}` / `{{-` / `-}}`：隣接する TEXT トークンの空白を手動で除去
- 実装は Lexer の後処理として、TEXT トークンの端を削る

### 7.6 テスト項目

- if / elif / else の分岐、for と for-else、ネスト
- `loop` 変数、タプルのアンパック
- スコープ（ループ外でループ変数が見えないこと）
- 空白制御：オプションの有無で出力が期待通りか（複数行テンプレートでスナップショット比較）
- エラー：`endif` の欠落、`endfor` と `endif` の取り違え、不明なタグ

## 8. フェーズ 4（任意）

- フィルタ：`{{ name | upper }}`、`{{ x | default("-") }}`（登録制）
- HTML 自動エスケープ（`autoescape=True` オプション、`| safe` で解除）
- `{% set x = expr %}`
- テンプレートの継承・インクルード（必要になれば）

## 9. 進め方

1. フェーズ 1 のテストを先に書く（仕様の固定）
2. `errors.py` → `lexer.py` → `nodes.py` → `parser.py` → `evaluator.py` → `template.py` の順に実装
3. フェーズ 2 はセキュリティのテストを先に書き、拒否されることを確認しながら許可範囲を広げる
4. 各フェーズの完了時に README に構文と制限事項を追記する
