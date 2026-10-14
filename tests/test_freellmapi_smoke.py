from __future__ import annotations

import io
import json
import urllib.error

import pytest

from scripts.freellmapi_smoke import run_smoke, validate_base_url


def test_base_url_requires_https_origin():
    assert validate_base_url("https://llm.example.test/") == "https://llm.example.test"
    with pytest.raises(ValueError, match="HTTPS"):
        validate_base_url("http://llm.example.test")
    with pytest.raises(ValueError, match="origin"):
        validate_base_url("https://llm.example.test/v1")
    with pytest.raises(ValueError, match="credentials"):
        validate_base_url("https://user:secret@llm.example.test")
    with pytest.raises(ValueError, match="credentials"):
        validate_base_url("https://llm.example.test/?token=secret")


def test_smoke_logs_only_pass_fail(monkeypatch, capsys):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self):
            return json.dumps({"choices": [{"message": {"content": "FREELLMAPI_SMOKE_OK"}}]}).encode()

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://llm.example.test/v1/chat/completions"
            assert request.get_header("Authorization") == "Bearer secret-test-key"
            return Response()

    monkeypatch.setattr("scripts.freellmapi_smoke.urllib.request.build_opener", lambda *args: Opener())
    assert run_smoke("https://llm.example.test", "secret-test-key") is True
    output = capsys.readouterr().out
    assert output.strip() == "FREELLMAPI_SMOKE=PASS"
    assert "secret-test-key" not in output


def test_http_error_body_is_never_logged(monkeypatch, capsys):
    class Opener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, 429, "rate limit", {}, io.BytesIO(b"private provider detail"))

    monkeypatch.setattr("scripts.freellmapi_smoke.urllib.request.build_opener", lambda *args: Opener())
    assert run_smoke("https://llm.example.test", "secret-test-key") is False
    output = capsys.readouterr().out
    assert output.strip() == "FREELLMAPI_SMOKE=FAIL reason=http_429"
    assert "private provider detail" not in output
    assert "secret-test-key" not in output
