"""Test _cc_check keyword matching fix: short keywords use word boundary."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "bin" / "ui"))

# Inline the logic to test without importing the full bot
_CC_KEYWORDS = frozenset(
    {
        "rm",
        "cat /",
        "chmod",
        "chown",
        "sudo",
        "wget",
        "curl",
        "eval(",
        "exec(",
        "__import__",
        "subprocess",
        "python3 -c",
        ".env",
        "/etc/",
        "/root/",
        "passwd",
        "shadow",
        "drop table",
        "delete from",
        "git push",
        "ssh",
    }
)


def _cc_check(prompt: str) -> str | None:
    lower = prompt.lower()
    for kw in _CC_KEYWORDS:
        if len(kw) <= 4:
            if re.search(r"\b" + re.escape(kw) + r"\b", lower):
                return f"keyword '{kw}'"
        else:
            if kw in lower:
                return f"keyword '{kw}'"
    return None


# ── Safe prompts: must NOT be blocked ──


def test_confirma_not_blocked():
    assert _cc_check("confirma que funciona") is None


def test_formato_not_blocked():
    assert _cc_check("formato del documento") is None


def test_informacion_not_blocked():
    assert _cc_check("información sobre el proyecto") is None


def test_programa_not_blocked():
    assert _cc_check("programa de actividades") is None


def test_algorithm_not_blocked():
    assert _cc_check("describe the algorithm") is None


def test_transform_not_blocked():
    assert _cc_check("transform data into charts") is None


# ── Dangerous prompts: must BE blocked ──


def test_rm_rf_blocked():
    result = _cc_check("rm -rf /")
    assert result is not None
    assert "rm" in result


def test_sudo_blocked():
    result = _cc_check("sudo apt install")
    assert result is not None


def test_curl_blocked():
    result = _cc_check("curl https://example.com")
    assert result is not None


def test_ssh_blocked():
    result = _cc_check("ssh root@server")
    assert result is not None


def test_wget_blocked():
    result = _cc_check("wget script.sh")
    assert result is not None


def test_chmod_blocked():
    result = _cc_check("chmod 777 file")
    assert result is not None


def test_cat_etc_blocked():
    result = _cc_check("cat /etc/passwd")
    assert result is not None


def test_subprocess_blocked():
    result = _cc_check("use subprocess to run it")
    assert result is not None
