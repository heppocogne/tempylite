import pytest

from tmpl import TemplateSyntaxError, TemplateSecurityError
from tmpl.evaluator import Evaluator
from tmpl.lexer import tokenize
from tmpl.nodes import For, If, Text, Var
from tmpl.parser import Parser


def parse(src):
    return Parser(Evaluator()).parse(tokenize(src))


def test_nodes():
    nodes = parse("a{{ x }}b")
    assert [type(n) for n in nodes] == [Text, Var, Text]


def test_if_structure():
    (node,) = parse("{% if a %}1{% elif b %}2{% else %}3{% endif %}")
    assert isinstance(node, If)
    assert len(node.branches) == 2
    assert node.else_body == [Text("3")]


def test_for_structure():
    (node,) = parse("{% for k, v in d %}x{% else %}y{% endfor %}")
    assert isinstance(node, For)
    assert node.target == ("k", "v")
    assert node.body == [Text("x")] and node.else_body == [Text("y")]


def test_for_nested_target():
    (node,) = parse("{% for a, (b, c) in d %}{% endfor %}")
    assert node.target == ("a", ("b", "c"))


@pytest.mark.parametrize("src,pos", [
    ("{% if x %}", (1, 1)),
    ("ab\n{% for x in y %}", (2, 1)),
    ("{% if x %}{% endfor %}", (1, 11)),
    ("{% for x in y %}{% endif %}", (1, 17)),
    ("{% endif %}", (1, 1)),
    ("{% else %}", (1, 1)),
    ("{% elif x %}", (1, 1)),
    ("{% for x in y %}{% elif z %}{% endfor %}", (1, 17)),
    ("{% if a %}{% else %}{% else %}{% endif %}", (1, 21)),
    ("{% foo %}", (1, 1)),
    ("{% %}", (1, 1)),
    ("{% if %}x{% endif %}", (1, 1)),
    ("{% for x y %}{% endfor %}", (1, 1)),
    ("{% for 1 in y %}{% endfor %}", (1, 1)),
    ("{% endif x %}", (1, 1)),
    ("{{ 1 + }}", (1, 1)),
    ("a\n{{ }}", (2, 1)),
])
def test_syntax_errors(src, pos):
    with pytest.raises(TemplateSyntaxError) as ei:
        parse(src)
    assert (ei.value.lineno, ei.value.col) == pos


def test_security_error_has_position():
    with pytest.raises(TemplateSecurityError) as ei:
        parse("x\n  {{ f(1) }}")
    assert (ei.value.lineno, ei.value.col) == (2, 3)


def test_block_nesting_limit():
    with pytest.raises(TemplateSyntaxError):
        parse("{% if x %}" * 100 + "{% endif %}" * 100)
