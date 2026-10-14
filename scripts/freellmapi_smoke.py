"""Manual, fixed-prompt FreeLLMAPI connectivity smoke test.

Never prints request/response bodies, credentials, or upstream error text.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_base_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("FREELLMAPI_BASE_URL is required")
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("FREELLMAPI_BASE_URL must be an HTTPS origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("FREELLMAPI_BASE_URL must not contain credentials, query, or fragment")
    if parsed.path not in ("", "/"):
        raise ValueError("FREELLMAPI_BASE_URL must be an origin without a path")
    return f"https://{parsed.netloc}"


def run_smoke(base_url: str, api_key: str, *, timeout: float = 25.0) -> bool:
    origin = validate_base_url(base_url)
    if not api_key or "\n" in api_key or "\r" in api_key:
        raise ValueError("FREELLMAPI_API_KEY is required")
    body = json.dumps({
        "model": "auto",
        "messages": [{"role": "user", "content": "Reply with exactly FREELLMAPI_SMOKE_OK"}],
        "max_tokens": 16,
        "stream": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{origin}/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                print(f"FREELLMAPI_SMOKE=FAIL reason=http_{response.status}")
                return False
            raw_response = response.read(1_000_001)
            if len(raw_response) > 1_000_000:
                print("FREELLMAPI_SMOKE=FAIL reason=response_too_large")
                return False
            payload = json.loads(raw_response.decode("utf-8"))
        choices = payload.get("choices")
        content = choices[0].get("message", {}).get("content") if isinstance(choices, list) and choices else None
        if not isinstance(content, str) or not content.strip():
            print("FREELLMAPI_SMOKE=FAIL reason=invalid_response_shape")
            return False
        print("FREELLMAPI_SMOKE=PASS")
        return True
    except urllib.error.HTTPError as exc:
        print(f"FREELLMAPI_SMOKE=FAIL reason=http_{exc.code}")
    except urllib.error.URLError:
        print("FREELLMAPI_SMOKE=FAIL reason=network_error")
    except (TimeoutError, OSError):
        print("FREELLMAPI_SMOKE=FAIL reason=transport_error")
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError, IndexError):
        print("FREELLMAPI_SMOKE=FAIL reason=invalid_response")
    return False


def main() -> int:
    try:
        base_url = validate_base_url(os.environ.get("FREELLMAPI_BASE_URL", ""))
        api_key = os.environ.get("FREELLMAPI_API_KEY", "")
        if not api_key:
            raise ValueError("FREELLMAPI_API_KEY is required")
    except ValueError as exc:
        # Only fixed validation messages are emitted; never echo input values.
        print(f"FREELLMAPI_SMOKE=FAIL reason=configuration ({exc})")
        return 2
    return 0 if run_smoke(base_url, api_key) else 1


if __name__ == "__main__":
    sys.exit(main())
