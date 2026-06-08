"""HTTP transport helpers for MemOS backend."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

from memos_cli.telemetry import build_source_identifier, detect_framework


DEFAULT_TIMEOUT = 30.0


class AuthError(Exception):
    """Authentication error."""


class APIError(Exception):
    """MemOS API request error."""


class MemOSTransport:
    """HTTP transport with auth/header handling and route fallback support."""

    def __init__(self, *, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.framework = detect_framework()

        if not self.api_key:
            raise AuthError("No API key configured")

    def _auth_headers(
        self,
        scheme: str,
        *,
        include_tracking_headers: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        token = self.api_key
        if token.lower().startswith(("bearer ", "token ")):
            auth_value = token
        else:
            auth_value = f"{scheme} {token}"

        headers = {
            "Authorization": auth_value,
            "Content-Type": "application/json",
        }
        if include_tracking_headers:
            headers["X-Source"] = build_source_identifier(self.framework)
        if include_tracking_headers and self.framework:
            headers["X-Framework"] = self.framework
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _auth_schemes(self) -> list[str]:
        if self.api_key.lower().startswith("bearer "):
            return ["Bearer"]
        if self.api_key.lower().startswith("token "):
            return ["Token"]
        return ["Token", "Bearer"]

    def _build_url(self, path: str) -> str:
        """Join base URL and route path while avoiding duplicate version segments."""
        parsed = urlsplit(self.base_url)
        base_path = parsed.path.rstrip("/")
        route_path = path if path.startswith("/") else f"/{path}"

        if base_path.endswith("/v1") and (route_path == "/v1" or route_path.startswith("/v1/")):
            route_path = route_path[3:] or "/"

        final_path = f"{base_path}{route_path}" if base_path else route_path
        return urlunsplit((parsed.scheme, parsed.netloc, final_path, "", ""))

    def request(
        self,
        method: str,
        path: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        expected_status: set[int] | None = None,
        include_tracking_headers: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> requests.Response:
        expected = expected_status or {200}
        last_response: requests.Response | None = None
        last_error: Exception | None = None

        for scheme in self._auth_schemes():
            try:
                response = requests.request(
                    method,
                    self._build_url(path),
                    headers=self._auth_headers(
                        scheme,
                        include_tracking_headers=include_tracking_headers,
                        extra_headers=extra_headers,
                    ),
                    json=json_body,
                    params=params,
                    timeout=timeout,
                )
                last_response = response
                if response.status_code in {401, 403} and len(self._auth_schemes()) > 1:
                    continue
                if response.status_code not in expected:
                    response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as exc:
                last_error = exc
                if exc.response is not None and exc.response.status_code == 401:
                    continue
                raise APIError(format_http_error(exc.response)) from exc
            except requests.exceptions.RequestException as exc:
                raise APIError(str(exc)) from exc

        if last_response is not None and last_response.status_code in {401, 403}:
            raise AuthError("Invalid or expired API key")
        if last_error is not None:
            raise APIError(str(last_error)) from last_error
        raise APIError("Unknown API error")

    def request_json(
        self,
        method: str,
        path: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        expected_status: set[int] | None = None,
        include_tracking_headers: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self.request(
            method,
            path,
            timeout=timeout,
            json_body=json_body,
            params=params,
            expected_status=expected_status,
            include_tracking_headers=include_tracking_headers,
            extra_headers=extra_headers,
        )
        if not response.content:
            return {}
        try:
            data = response.json()
        except ValueError as exc:
            raise APIError(f"Invalid JSON response from {path}") from exc
        self._raise_for_business_error(data)
        return data

    def request_first_json(self, method: str, paths: list[str], **kwargs: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        for path in paths:
            try:
                return self.request_json(method, path, **kwargs)
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise APIError("No API path configured")

    def _raise_for_business_error(self, data: Any) -> None:
        """Raise APIError when the HTTP response is 200 but the business result is failed."""
        if not isinstance(data, dict):
            return

        code = data.get("code")
        status = str(data.get("status", "") or "").strip().lower()
        message = str(data.get("message", "") or data.get("msg", "") or "").strip()
        raw_payload = data.get("data")
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        payload_success = payload.get("success")
        payload_status = str(payload.get("status", "") or "").strip().lower()

        if payload_success is True:
            return

        if payload_success is False:
            raise APIError(
                _format_business_error(
                    code=code,
                    status=payload_status or status,
                    message=message,
                )
            )

        if isinstance(code, int) and code not in {0, 200}:
            raise APIError(_format_business_error(code=code, status=status, message=message))

        if status in {"error", "failed", "fail"}:
            raise APIError(_format_business_error(code=code, status=status, message=message))

        if payload_status in {"error", "failed", "fail"}:
            raise APIError(
                _format_business_error(
                    code=code,
                    status=payload_status,
                    message=message,
                )
            )


def format_http_error(response: requests.Response | None) -> str:
    """Format HTTP response into a user-facing error string."""
    if response is None:
        return "HTTP request failed"
    body = response.text.strip()
    if not body:
        return f"HTTP {response.status_code}"
    return f"HTTP {response.status_code}: {body}"


def _format_business_error(*, code: Any, status: str, message: str) -> str:
    """Format an application-level error embedded in a successful HTTP response."""
    parts: list[str] = ["API business error"]
    if code not in (None, ""):
        parts.append(f"code={code}")
    if status:
        parts.append(f"status={status}")
    if message:
        parts.append(f"message={message}")
    return ": ".join([parts[0], ", ".join(parts[1:])]) if len(parts) > 1 else parts[0]
