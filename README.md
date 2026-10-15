# tempylite
簡易的なテンプレートエンジン

設計・実装計画は [docs/template_engine_plan.md](docs/template_engine_plan.md) を参照。

## 使い方

```python
from tempylite import Template

t = Template("Hello {{ name }}!", undefined="None")  # "None" | "" | "strict"
t.render({"name": "YY"})   # -> "Hello YY!"
t.render(name="YY")        # キーワード引数でも可
```

## 構文

- `{{ expression }}`：式を評価して出力。エスケープは `{{ '{{' }}` のように文字列リテラルで行う
- `{% if cond %}…{% elif cond %}…{% else %}…{% endif %}`
- `{% for x in items %}…{% else %}…{% endfor %}`（`k, v` のアンパック可。`loop.index` / `index0` / `first` / `last` / `length`）
- `{# コメント #}`
- 空白制御：`trim_blocks` / `lstrip_blocks`（デフォルト有効）、`{%-` `-%}` `{{-` `-}}`
  （`{{-1}}` は空白除去と解釈されるので、負数は `{{ -1 }}` と書く）

### 式

リテラル（数値・文字列・list・tuple・dict・set）、変数、`obj.key` / `obj["key"]`、スライス、
算術・比較・論理演算、三項演算子。`eval` は使わず `ast` のホワイトリスト評価を行う。
関数・メソッド呼び出し、lambda、内包表記、f-string、`:=` などは `TemplateSecurityError`。

## 制限事項・注意

- `.` / `[]` は dict のキーを優先し、無ければ属性を参照する。`_` で始まる属性は拒否する
- メソッドは参照できても呼び出せない
- property は属性アクセスだけで実行される。副作用のあるオブジェクトを渡さないこと
- DoS 対策の上限は `Template(..., max_expr_length=, max_nodes=, max_depth=, max_exponent=, max_sequence_size=, max_block_depth=)` で変更可能
- `str % x` 形式の書式化、`<<` / `>>` は無効
- 例外：`TemplateSyntaxError`（コンパイル時）、`TemplateSecurityError`（禁止操作・上限超過）、
  `UndefinedError`（strict）、`TemplateRuntimeError`（描画時の型エラー等）。いずれも行・列番号付き

## テスト

```
pip install pytest
pytest
```
