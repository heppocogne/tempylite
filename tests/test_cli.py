import json
import sys

import pytest

from tempylite.cli import main

needs_toml = pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib requires 3.11+")


def run(capsys, *argv):
    code = main([str(a) for a in argv])
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture
def tpl(tmp_path):
    p = tmp_path / "file.template.txt"
    p.write_text("Hello {{ name }}!\n{% for x in xs %}{{ x }},{% endfor %}\n", encoding="utf-8")
    return p


def test_json(capsys, tmp_path, tpl):
    d = tmp_path / "d.json"
    d.write_text(json.dumps({"name": "世界", "xs": [1, 2]}), encoding="utf-8")
    assert run(capsys, tpl, "--json", d) == (0, "Hello 世界!\n1,2,", "")


@needs_toml
def test_toml(capsys, tmp_path, tpl):
    d = tmp_path / "d.toml"
    d.write_text('name = "YY"\nxs = [3]\n', encoding="utf-8")
    assert run(capsys, tpl, "--toml", d) == (0, "Hello YY!\n3,", "")


def test_merge_and_define_precedence(capsys, tmp_path, tpl):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text('{"name": "A", "xs": [1]}')
    b.write_text('{"name": "B"}')
    assert run(capsys, tpl, "--json", a, "--json", b)[1] == "Hello B!\n1,"
    assert run(capsys, tpl, "--json", a, "-D", "name=D")[1] == "Hello D!\n1,"


def test_output_file(capsys, tmp_path, tpl):
    out = tmp_path / "out.txt"
    assert run(capsys, tpl, "-D", "name=Z", "-o", out) == (0, "", "")
    assert out.read_text(encoding="utf-8") == "Hello Z!\n"


def test_options(capsys, tmp_path):
    t = tmp_path / "t"
    t.write_text("{{ missing }}|\n  {% if 1 %}\nx{% endif %}\n")
    assert run(capsys, t)[1] == "None|\nx"
    assert run(capsys, t, "--undefined", "")[1] == "|\nx"
    assert run(capsys, t, "--no-trim-blocks", "--no-lstrip-blocks")[1] == "None|\n  \nx\n"
    code, out, err = run(capsys, t, "--undefined", "strict")
    assert code == 1 and out == ""
    assert f"{t}:1:1: UndefinedError" in err


def test_template_error_position(capsys, tmp_path):
    t = tmp_path / "bad.txt"
    t.write_text("ok\n  {{ len(x) }}")
    code, _, err = run(capsys, t)
    assert code == 1
    assert f"{t}:2:3: TemplateSecurityError" in err


def test_stdin_template(capsys, monkeypatch):
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO("hi {{ a }}"))
    assert run(capsys, "-", "-D", "a=1") == (0, "hi 1", "")


@pytest.mark.parametrize("content,msg", [("{bad", "invalid JSON"), ("[1]", "top-level")])
def test_bad_data(capsys, tmp_path, tpl, content, msg):
    d = tmp_path / "d.json"
    d.write_text(content)
    code, out, err = run(capsys, tpl, "--json", d)
    assert code == 1 and out == "" and msg in err


def test_missing_files(capsys, tmp_path, tpl):
    assert "cannot read file" in run(capsys, tmp_path / "nope")[2]
    assert "cannot read file" in run(capsys, tpl, "--json", tmp_path / "nope.json")[2]


def test_usage_errors(capsys, tpl):
    with pytest.raises(SystemExit) as ei:
        main([str(tpl), "-D", "novalue"])
    assert ei.value.code == 2
    capsys.readouterr()
    assert run(capsys, "-", "--json", "-")[0] == 1


def test_python_dash_m(tmp_path, tpl):
    import subprocess
    r = subprocess.run([sys.executable, "-m", "tempylite", str(tpl), "-D", "name=M"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and r.stdout.startswith("Hello M!")
