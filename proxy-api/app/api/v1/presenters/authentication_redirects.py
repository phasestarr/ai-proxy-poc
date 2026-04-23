from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request, status
from fastapi.responses import RedirectResponse

from app.config.settings import settings


def build_external_microsoft_redirect_uri(request: Request) -> str:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    forwarded_host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    ).split(",")[0].strip()
    forwarded_port = (request.headers.get("x-forwarded-port") or "").split(",")[0].strip()

    host = forwarded_host
    if host and ":" not in host and forwarded_port:
        is_default_port = (forwarded_proto == "https" and forwarded_port == "443") or (
            forwarded_proto == "http" and forwarded_port == "80"
        )
        if not is_default_port:
            host = f"{host}:{forwarded_port}"

    return f"{forwarded_proto}://{host}{settings.microsoft_redirect_path}"


def build_frontend_redirect(
    return_to: str,
    *,
    auth_error: str | None = None,
) -> RedirectResponse:
    normalized_return_to = _normalize_return_to(return_to)
    if auth_error:
        normalized_return_to = _append_query_param(normalized_return_to, "auth_error", auth_error)
    return RedirectResponse(url=normalized_return_to, status_code=status.HTTP_302_FOUND)


def _normalize_return_to(return_to: str | None) -> str:
    candidate = (return_to or "/").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    return candidate


def _append_query_param(path: str, key: str, value: str) -> str:
    split_result = urlsplit(path)
    query_items = parse_qsl(split_result.query, keep_blank_values=True)
    query_items = [(item_key, item_value) for item_key, item_value in query_items if item_key != key]
    query_items.append((key, value))
    return urlunsplit(
        (
            split_result.scheme,
            split_result.netloc,
            split_result.path,
            urlencode(query_items),
            split_result.fragment,
        )
    )

