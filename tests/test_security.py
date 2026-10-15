import pytest

from tempylite import Template, TemplateError, TemplateSecurityError, TemplateSyntaxError


class Thing:
    secret = "s"

    def __init__(self):
        self.pub = 1


@pytest.mark.parametrize("expr", [
    "().__class__",
    "x.__dict__",
    "x.__class__.__mro__",
    "x['__class__']",
    "x._private",
    "x['_private']",
    "x.__class__.__bases__[0].__subclasses__",
    "g.gi_frame",
    "g.gi_code",
])
def test_forbidden_access(expr):
    ctx = {"x": Thing(), "g": (i for i in [])}
    with pytest.raises(TemplateSecurityError):
        Template("{{ %s }}" % expr).render(ctx)


@pytest.mark.parametrize("expr", [
    "len(x)",
    "x.pub()",
    "(lambda: 1)()",
    "[i for i in x]",
    "{i for i in x}",
    "{i: i for i in x}",
    "(i for i in x)",
    "f'{x}'",
    "(y := 1)",
    "[*x]",
    "{**x}",
    "x if (yield) else 1",
    "await x",
    "x << 1",
    "x >> 1",
    "x @ x",
])
def test_forbidden_syntax(expr):
    with pytest.raises(TemplateError) as ei:
        Template("{{ %s }}" % expr)
    assert isinstance(ei.value, (TemplateSecurityError, TemplateSyntaxError))


@pytest.mark.parametrize("expr", [
    "len(x)", "(lambda: 1)()", "[i for i in x]", "f'{x}'", "(y := 1)", "x.pub()",
])
def test_forbidden_is_security_error(expr):
    with pytest.raises(TemplateSecurityError):
        Template("{{ %s }}" % expr)


def test_forbidden_in_block_tags():
    with pytest.raises(TemplateSecurityError):
        Template("{% if x.__class__ %}{% endif %}").render(x=1)
    with pytest.raises(TemplateSecurityError):
        Template("{% for i in len(x) %}{% endfor %}")


def test_mapping_underscore_key_via_item():
    # dict の実キーなら [] で取得できる。無ければ Undefined。
    assert Template("{{ d['_a'] }}|{{ d['_b'] }}").render(d={"_a": 1}) == "1|None"


def test_public_attrs_ok():
    assert Template("{{ x.pub }}{{ x.secret }}").render(x=Thing()) == "1s"


# ---- DoS ----

def test_pow_limits():
    with pytest.raises(TemplateSecurityError):
        Template("{{ 9**9**9 }}").render()
    with pytest.raises(TemplateSecurityError):
        Template("{{ 2 ** 101 }}").render()
    assert Template("{{ 2 ** 100 }}").render() == str(2**100)
    assert Template("{{ 2 ** 101 }}", max_exponent=200).render() == str(2**101)


def test_sequence_limits():
    for src in ['"a"*10**9', '10**9*"a"', "[0]*10**9", "(1,)*10**9"]:
        with pytest.raises(TemplateSecurityError):
            Template("{{ %s }}" % src).render()
    assert Template('{{ "ab" * 3 }}').render() == "ababab"
    with pytest.raises(TemplateSecurityError):
        Template('{{ "ab" * 3 }}', max_sequence_size=5).render()


def test_percent_format_blocked():
    with pytest.raises(TemplateSecurityError):
        Template('{{ "%1000000000d" % 1 }}').render()
    assert Template("{{ 7 % 4 }}").render() == "3"


def test_expression_limits():
    with pytest.raises(TemplateSecurityError):
        Template("{{ " + "1+" * 600 + "1 }}")
    with pytest.raises(TemplateSecurityError):
        Template("{{ " + "-" * 200 + "1 }}")
    with pytest.raises(TemplateSecurityError):
        Template("{{ [" + "1," * 600 + "] }}")
    with pytest.raises((TemplateSecurityError, TemplateSyntaxError)):
        Template("{{ " + "(" * 500 + "1" + ")" * 500 + " }}")
    assert Template("{{ " + "-" * 10 + "1 }}").render() == "1"
    assert Template("{{ " + "-" * 200 + "1 }}", max_depth=300, max_nodes=300).render() == "1"
