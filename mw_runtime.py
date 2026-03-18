from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from requests import Response

DEFAULT_USER_AGENT: str = (
    "WikiChartBot/1.0 (https://github.com/your-org/your-repo; "
    "contact@example.org) requests/2.x")


def load_env_file(env_path: str = ".env") -> None:
    path = Path(env_path)
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if ((value.startswith('"') and value.endswith('"'))
                or (value.startswith("'") and value.endswith("'"))):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def safe_get_json(response: Response) -> dict[str, Any]:
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"API returned non-JSON response, HTTP {response.status_code}"
        ) from exc


def build_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip",
    })
    return session


def api_get_json(
    session: requests.Session,
    wiki_api: str,
    params: dict[str, Any],
    timeout: int,
    error_context: str,
) -> dict[str, Any]:
    try:
        response = session.get(
            wiki_api,
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
        return safe_get_json(response)
    except Exception as exc:
        raise RuntimeError(f"{error_context}: {exc}") from exc


def api_post_json(
    session: requests.Session,
    wiki_api: str,
    data: dict[str, Any],
    timeout: int,
    error_context: str,
) -> dict[str, Any]:
    try:
        response = session.post(
            wiki_api,
            data=data,
            timeout=timeout,
        )
        response.raise_for_status()
        return safe_get_json(response)
    except Exception as exc:
        raise RuntimeError(f"{error_context}: {exc}") from exc


def get_login_token(
    session: requests.Session,
    wiki_api: str,
    timeout: int,
    max_lag: int,
) -> str:
    data = api_get_json(
        session=session,
        wiki_api=wiki_api,
        params={
            "action": "query",
            "meta": "tokens",
            "type": "login",
            "format": "json",
            "maxlag": max_lag,
        },
        timeout=timeout,
        error_context="Failed to fetch login token",
    )

    login_token = data.get("query", {}).get("tokens", {}).get("logintoken")
    if not isinstance(login_token, str) or not login_token:
        raise RuntimeError(f"Login token missing: {data}")
    return login_token


def login_with_bot_password(
    session: requests.Session,
    wiki_api: str,
    bot_username: str,
    bot_password: str,
    timeout: int,
    max_lag: int,
) -> dict[str, Any]:
    login_token = get_login_token(
        session=session,
        wiki_api=wiki_api,
        timeout=timeout,
        max_lag=max_lag,
    )

    result = api_post_json(
        session=session,
        wiki_api=wiki_api,
        data={
            "action": "login",
            "lgname": bot_username,
            "lgpassword": bot_password,
            "lgtoken": login_token,
            "format": "json",
            "maxlag": max_lag,
        },
        timeout=timeout,
        error_context="Login request failed",
    )

    login_result = result.get("login", {}).get("result")
    if login_result != "Success":
        raise RuntimeError(f"Login failed: {result}")
    return result


def get_user_groups(
    session: requests.Session,
    wiki_api: str,
    timeout: int,
    max_lag: int,
    assert_mode: str,
) -> list[str]:
    data = api_get_json(
        session=session,
        wiki_api=wiki_api,
        params={
            "action": "query",
            "meta": "userinfo",
            "uiprop": "groups",
            "format": "json",
            "assert": assert_mode,
            "maxlag": max_lag,
        },
        timeout=timeout,
        error_context="Failed to fetch user groups",
    )
    groups = data.get("query", {}).get("userinfo", {}).get("groups", [])
    return groups if isinstance(groups, list) else []


def get_csrf_token(
    session: requests.Session,
    wiki_api: str,
    timeout: int,
    max_lag: int,
    assert_mode: str,
) -> str:
    data = api_get_json(
        session=session,
        wiki_api=wiki_api,
        params={
            "action": "query",
            "meta": "tokens",
            "format": "json",
            "assert": assert_mode,
            "maxlag": max_lag,
        },
        timeout=timeout,
        error_context="Failed to fetch CSRF token",
    )

    csrf_token = data.get("query", {}).get("tokens", {}).get("csrftoken")
    if not isinstance(csrf_token, str) or not csrf_token:
        raise RuntimeError(f"CSRF token missing: {data}")
    return csrf_token
