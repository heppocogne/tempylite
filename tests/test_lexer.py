import pytest

from tempylite import TemplateSyntaxError
from tempylite.lexer import BLOCK, TEXT, VAR, tokenize


def kinds(src, **kw):
    return [(t.type, t.value) for t in tokenize(src, **kw)]


def test_plain_text():
    assert kinds("hello") == [(TEXT, "hello")]


def test_empty():
    assert kinds("") == []


def test_var_and_text():
    assert kinds("a{{ x }}b") == [(TEXT, "a"), (VAR, " x "), (TEXT, "b")]


def test_adjacent_tags():
    assert kinds("{{a}}{{b}}") == [(VAR, "a"), (VAR, "b")]


def test_closer_inside_quotes():
    assert kinds("{{ '}}' }}") == [(VAR, " '}}' ")]
    assert kinds('{{ "}}" }}') == [(VAR, ' "}}" ')]


def test_escaped_quote():
    assert kinds(r"{{ 'a\'}}b' }}") == [(VAR, r" 'a\'}}b' ")]


def test_nested_braces_dict():
    assert kinds("{{ {'a': {'b': 1}} }}") == [(VAR, " {'a': {'b': 1}} ")]


def test_block_and_comment():
    assert kinds("{% if x %}{# hi #}y", trim_blocks=False) == [(BLOCK, " if x "), (TEXT, "y")]


def test_positions():
    toks = tokenize("ab\n  {{ x }}\n{{ y }}")
    var = [t for t in toks if t.type == VAR]
    assert (var[0].lineno, var[0].col) == (2, 3)
    assert (var[1].lineno, var[1].col) == (3, 1)


@pytest.mark.parametrize("src,pos", [
    ("{{ x", (1, 1)),
    ("ab\n  {{ x", (2, 3)),
    ("{{ '}}", (1, 1)),
    ("{% if x", (1, 1)),
    ("a {# x", (1, 3)),
])
def test_unclosed(src, pos):
    with pytest.raises(TemplateSyntaxError) as ei:
        tokenize(src)
    assert (ei.value.lineno, ei.value.col) == pos


def test_trim_blocks():
    assert kinds("{% a %}\nx", lstrip_blocks=False) == [(BLOCK, " a "), (TEXT, "x")]
    assert kinds("{% a %}\nx", trim_blocks=False, lstrip_blocks=False) == [
        (BLOCK, " a "), (TEXT, "\nx")]


def test_lstrip_blocks():
    assert kinds("a\n   {% a %}", trim_blocks=False)[0] == (TEXT, "a\n")
    assert kinds("a  {% a %}", trim_blocks=False)[0] == (TEXT, "a  ")
    assert kinds("  {% a %}", trim_blocks=False)[0] == (BLOCK, " a ")


def test_manual_strip():
    assert kinds("a  {{- x -}}  b") == [(TEXT, "a"), (VAR, " x "), (TEXT, "b")]
    assert kinds("a \n {%- x -%} \n b", trim_blocks=False, lstrip_blocks=False) == [
        (TEXT, "a"), (BLOCK, " x "), (TEXT, "b")]
