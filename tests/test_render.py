import pytest

from tmpl import (
    Template, TemplateRuntimeError, TemplateSyntaxError, Undefined, UndefinedError,
)


def r(src, ctx=None, **kw):
    opts = {k: kw.pop(k) for k in list(kw) if k in ("undefined", "trim_blocks", "lstrip_blocks")}
    return Template(src, **opts).render(ctx, **kw)


# ---- フェーズ 1 ----

def test_simple():
    assert r("Hello {{ name }}!", {"name": "YY"}) == "Hello YY!"


def test_kwargs_and_dict_merge():
    t = Template("{{a}}{{b}}")
    assert t.render(a=1, b=2) == "12"
    assert t.render({"a": 1, "b": 0}, b=2) == "12"


def test_multiple_and_adjacent():
    assert r("{{a}}{{b}} {{ a }}", a="x", b="y") == "xy x"


@pytest.mark.parametrize("src", ["{{x}}", "{{   x   }}", "{{\tx\t}}", "{{\nx\n}}"])
def test_whitespace_variants(src):
    assert r(src, x="v") == "v"


def test_escapes():
    assert r("{{ '{{' }}") == "{{"
    assert r("{{ '}}' }}") == "}}"
    assert r('{{ "it\'s" }}') == "it's"
    assert r("{{ '{%' }} {{ '{#' }}") == "{% {#"


def test_undefined_modes():
    assert r("[{{ x }}]") == "[None]"
    assert r("[{{ x }}]", undefined="") == "[]"
    assert r("[{{ x.y.z }}]", undefined="") == "[]"
    with pytest.raises(UndefinedError) as ei:
        r("a\n  {{ x }}", undefined="strict")
    assert (ei.value.lineno, ei.value.col) == (2, 3)


def test_invalid_undefined_mode():
    with pytest.raises(ValueError):
        Template("x", undefined="bogus")


def test_undefined_is_object():
    assert r("{{ x == y }}") == "True"  # 両方 Undefined


def test_stringification():
    assert r("{{ a }}|{{ b }}|{{ c }}|{{ d }}", a=1, b=None, c=[1, "a"], d=1.5) == "1|None|[1, 'a']|1.5"


def test_text_only_empty_multiline():
    assert r("no tags") == "no tags"
    assert r("") == ""
    assert r("a\nb\n{{ x }}\nc\n", x=1) == "a\nb\n1\nc\n"


def test_unclosed_and_empty():
    for src in ["{{ x", "{{ }}", "{{ 1 + }}"]:
        with pytest.raises(TemplateSyntaxError):
            Template(src)


def test_unsupported_error_position():
    with pytest.raises(TemplateSyntaxError) as ei:
        Template("line1\nab {% foo %}")
    assert (ei.value.lineno, ei.value.col) == (2, 4)


def test_reuse():
    t = Template("{{ x }}")
    assert [t.render(x=i) for i in range(3)] == ["0", "1", "2"]


# ---- フェーズ 2 ----

def test_arithmetic_and_logic():
    assert r("{{ 1 + 2 * 3 }} {{ 7 // 2 }} {{ 7 % 4 }} {{ 2 ** 3 }} {{ 1 / 4 }}") == "7 3 3 8 0.25"
    assert r("{{ a < b < c }} {{ a == 1 and b }} {{ 0 or 'z' }} {{ not a }}", a=1, b=2, c=3) == "True 2 z False"
    assert r("{{ 'y' if a else 'n' }}{{ 'y' if b else 'n' }}", a=1, b=0) == "yn"
    assert r("{{ 2 in [1, 2] }} {{ 3 not in (1, 2) }} {{ x is None }}", x=None) == "True True True"


def test_literals_and_slices():
    assert r("{{ [1, 2] }}{{ (1,) }}{{ {'a': 1} }}{{ {1} }}") == "[1, 2](1,){'a': 1}{1}"
    assert r("{{ x[1:3] }}{{ x[::-1] }}{{ x[-1] }}", x="abcd") == "bcdcbad"
    assert r("{{ 'a' + 'b' }}{{ 'ab' * 2 }}") == "ab" + "abab"


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    @property
    def prop(self):
        return "P"

    def method(self):
        return "called"


def test_attr_and_item_access():
    ctx = {"d": {"a": {"b": 1}}, "o": Obj(x=Obj(y=2)), "l": [10, 20]}
    assert r("{{ d.a.b }} {{ d['a']['b'] }} {{ d.a['b'] }}", ctx) == "1 1 1"
    assert r("{{ o.x.y }} {{ o['x']['y'] }} {{ o.prop }} {{ l[1] }}", ctx) == "2 2 P 20"


def test_dict_key_priority():
    assert r("{{ d.items }} {{ d['items'] }}", d={"items": "KEY"}) == "KEY KEY"
    assert "built-in method" in r("{{ d.items }}", d={})


def test_missing_gives_undefined():
    assert r("{{ d.nope }}|{{ d['nope'] }}|{{ l[9] }}|{{ o.nope.z }}", d={}, l=[], o=Obj()) == "None|None|None|None"


def test_methods_not_called():
    out = r("{{ o.method }}", o=Obj())
    assert "called" not in out and "method" in out


def test_runtime_errors():
    for src in ["{{ 1 / 0 }}", "{{ 1 + 'a' }}", "{{ x < 1 }}"]:
        with pytest.raises(TemplateRuntimeError) as ei:
            r("\n" + src)
        assert ei.value.lineno == 2


def test_builtins_hidden():
    assert r("{{ len }}") == "None"


# ---- フェーズ 3 ----

def test_if_branches():
    src = "{% if a %}A{% elif b %}B{% else %}C{% endif %}"
    assert r(src, a=1) == "A"
    assert r(src, b=1) == "B"
    assert r(src) == "C"


def test_for_basic_and_else():
    src = "{% for x in xs %}{{ x }},{% else %}empty{% endfor %}"
    assert r(src, xs=[1, 2, 3]) == "1,2,3,"
    assert r(src, xs=[]) == "empty"
    assert r(src) == "empty"  # Undefined は空


def test_for_unpack_and_dict():
    assert r("{% for k, v in d.items_ %}{{k}}={{v}};{% endfor %}", d={"items_": [("a", 1), ("b", 2)]}) == "a=1;b=2;"
    assert r("{% for k in d %}{{ k }}{% endfor %}", d={"x": 1, "y": 2}) == "xy"
    assert r("{% for a, (b, c) in xs %}{{a}}{{b}}{{c}}{% endfor %}", xs=[(1, (2, 3))]) == "123"


def test_loop_variable():
    src = "{% for x in xs %}{{loop.index}}/{{loop.index0}}/{{loop.length}}/{{loop.first}}/{{loop.last}} {% endfor %}"
    assert r(src, xs="ab") == "1/0/2/True/False 2/1/2/False/True "


def test_nesting_and_loop_shadow():
    src = "{% for i in a %}{% for j in b %}{% if j > i %}{{i}}{{j}}{{loop.index}} {% endif %}{% endfor %}{% endfor %}"
    assert r(src, a=[1, 2], b=[1, 2, 3]) == "122 133 233 "


def test_scope():
    src = "{% for x in xs %}{% endfor %}[{{ x }}][{{ loop }}]"
    assert r(src, {"xs": [1]}) == "[None][None]"
    ctx = {"x": "outer", "xs": [1]}
    assert r("{% for x in xs %}{{x}}{% endfor %}{{x}}", ctx) == "1outer"
    assert ctx == {"x": "outer", "xs": [1]}


def test_for_errors():
    with pytest.raises(TemplateRuntimeError):
        r("{% for x in 5 %}{% endfor %}")
    with pytest.raises(TemplateRuntimeError):
        r("{% for a, b in xs %}{% endfor %}", xs=[(1, 2, 3)])
    with pytest.raises(TemplateRuntimeError) as ei:
        r("a\n{% if 1/0 %}{% endif %}")
    assert (ei.value.lineno, ei.value.col) == (2, 1)


def test_comment():
    assert r("a{# hidden {{ x }} #}b") == "ab"


# ---- 空白制御（スナップショット） ----

TPL = """\
<ul>
  {% for x in xs %}
  <li>{{ x }}</li>
  {% endfor %}
</ul>
"""


def test_default_whitespace_control():
    assert r(TPL, xs=[1, 2]) == "<ul>\n  <li>1</li>\n  <li>2</li>\n</ul>\n"


def test_no_trim_no_lstrip():
    out = r(TPL, xs=[1], trim_blocks=False, lstrip_blocks=False)
    assert out == "<ul>\n  \n  <li>1</li>\n  \n</ul>\n"


def test_trim_only_and_lstrip_only():
    assert r(TPL, xs=[1], lstrip_blocks=False) == "<ul>\n    <li>1</li>\n  </ul>\n"
    assert r(TPL, xs=[1], trim_blocks=False) == "<ul>\n\n  <li>1</li>\n\n</ul>\n"


def test_manual_strip_in_render():
    assert r("a  {{- x -}}  b", x="X") == "aXb"
    assert r("a\n{%- if x -%}\n  b\n{%- endif %}\nc", x=1, trim_blocks=False, lstrip_blocks=False) == "ab\nc"
    assert r("a  {#- c -#}  b") == "ab"


def test_inline_block_not_stripped():
    assert r("a {% if x %}b{% endif %} c", x=1) == "a b c"
