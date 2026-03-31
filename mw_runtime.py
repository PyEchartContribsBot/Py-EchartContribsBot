from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from requests import Response

DEFAULT_USER_AGENT: str = (
    "WikiChartBot/1.0 (https://github.com/your-org/your-repo; "
    "contact@example.org) requests/2.x")


def parse_bool_env(raw_value: str, *, default: bool) -> bool:
    value = raw_value.strip().lower()
    if not value:
        return default
    if value == "true":
        return True
    if value == "false":
        return False
    raise RuntimeError("仅支持 true/false 或留空")


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


def parse_mw_api_headers() -> dict[str, str]:
    """从环境变量 MW_API_HEADERS_JSON 读取 MediaWiki API 通用 Header。

    Returns:
        包含 HTTP Header 的字典，如果环境变量未设置或为空则返回空字典
    """
    headers_json = os.environ.get("MW_API_HEADERS_JSON", "").strip()
    if not headers_json:
        return {}

    try:
        parsed = json.loads(headers_json)
        if not isinstance(parsed, dict):
            raise ValueError("MW_API_HEADERS_JSON must be a JSON object")
        return parsed
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse MW_API_HEADERS_JSON: {exc}"
        ) from exc


def build_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    headers = {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip",
    }

    # 从环境变量中读取 MediaWiki API 通用 Header
    api_headers = parse_mw_api_headers()
    headers |= api_headers

    session.headers.update(headers)
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


def fetch_account_registrations(
    session: requests.Session,
    wiki_api: str,
    users: list[str],
    timeout: int,
    max_lag: int,
) -> dict[str, str]:
    """查询多个用户的注册时间。"""
    if not users:
        return {}

    params: dict[str, Any] = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "list": "users",
        "ususers": "|".join(users),
        "usprop": "registration",
        "maxlag": max_lag,
    }

    data = api_get_json(
        session=session,
        wiki_api=wiki_api,
        params=params,
        timeout=timeout,
        error_context="查询用户注册时间失败",
    )

    if "error" in data:
        api_error = data["error"]
        code = api_error.get("code", "unknown")
        info = api_error.get("info", "no details")
        raise RuntimeError(
            f"查询用户注册时间返回 API 错误 code={code}, info={info}")

    users_data = data.get("query", {}).get("users", [])
    if not isinstance(users_data, list):
        raise RuntimeError("API 响应格式异常: query.users 不是列表")

    registrations: dict[str, str] = {}
    for user_info in users_data:
        if not isinstance(user_info, dict):
            continue
        username = user_info.get("name")
        registration = user_info.get("registration")
        if isinstance(username, str) and isinstance(registration, str):
            registrations[username] = registration

    return registrations


def fetch_namespaces(
    session: requests.Session,
    wiki_api: str,
    timeout: int,
) -> dict[int, str]:
    """从 MediaWiki API 获取命名空间名称映射。"""
    params: dict[str, Any] = {
        "action": "query",
        "format": "json",
        "meta": "siteinfo",
        "formatversion": 2,
        "siprop": "namespaces",
    }

    try:
        data = api_get_json(
            session=session,
            wiki_api=wiki_api,
            params=params,
            timeout=timeout,
            error_context="获取命名空间信息失败",
        )
    except RuntimeError as exc:
        raise RuntimeError(f"无法从 API 获取命名空间: {exc}") from exc

    namespaces_data = data.get("query", {}).get("namespaces", {})
    if not namespaces_data:
        raise RuntimeError("API 响应中未包含 namespaces 数据")

    namespace_map: dict[int, str] = {}

    for ns_key, ns_info in namespaces_data.items():
        try:
            ns_id = int(ns_key)
        except ValueError:
            continue

        if not isinstance(ns_info, dict):
            continue

        # formatversion=2 使用 "name" 字段（而非 formatversion=1 的 "*" 字段）
        ns_name = ns_info.get("name", "")

        # MediaWiki API 对主命名空间返回空字符串，将其转换为"（主）"
        if ns_id == 0 and not ns_name:
            namespace_map[ns_id] = "（主）"
        elif ns_name:
            namespace_map[ns_id] = ns_name

    return namespace_map


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
