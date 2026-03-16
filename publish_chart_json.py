from __future__ import annotations

import os
import sys
from typing import Any

import requests
from mw_runtime import DEFAULT_USER_AGENT, build_session, load_env_file, safe_get_json

load_env_file()


def fail(message: str, detail: Any = None) -> None:
    if detail is not None:
        print(f"ERROR: {message}: {detail}", file=sys.stderr)
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"::warning::{message}")


def post_edit(
    session: requests.Session,
    wiki_api: str,
    wiki_page: str,
    new_text: str,
    csrf_token: str,
    timeout: int,
    max_lag: int,
    assert_mode: str,
    mark_as_bot: bool,
    tags: str | None,
    summary: str,
) -> dict[str, Any]:
    payload = {
        "action": "edit",
        "title": wiki_page,
        "text": new_text,
        "token": csrf_token,
        "summary": summary,
        "format": "json",
        "contentmodel": "json",
        "contentformat": "application/json",
        "assert": assert_mode,
        "maxlag": max_lag,
    }
    if mark_as_bot:
        payload["bot"] = "1"
    if tags:
        payload["tags"] = tags

    response = session.post(
        wiki_api,
        data=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def is_bot_permission_error(result: dict[str, Any]) -> bool:
    error = result.get("error")
    if not isinstance(error, dict):
        return False

    code = str(error.get("code", "")).lower()
    info = str(error.get("info", "")).lower()
    return code == "permissiondenied" and "bot" in info


def is_tag_error(result: dict[str, Any]) -> bool:
    error = result.get("error")
    if not isinstance(error, dict):
        return False

    code = str(error.get("code", "")).lower()
    info = str(error.get("info", "")).lower()

    if code == "badtags":
        return True

    return code == "permissiondenied" and "tag" in info


def parse_edit_tag_candidates(raw_value: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for token in raw_value.split(","):
        tag = token.strip()
        if not tag:
            continue
        if tag in seen:
            continue
        seen.add(tag)
        candidates.append(tag)

    return candidates


def format_api_error(result: dict[str, Any]) -> str:
    error = result.get("error")
    if not isinstance(error, dict):
        return "No structured error payload returned"

    code = str(error.get("code", ""))
    info = str(error.get("info", ""))
    # Omit 'code', 'info' (already shown) and '*' (verbose API usage boilerplate)
    skip_keys = {"code", "info", "*"}
    extra = {k: v for k, v in error.items() if k not in skip_keys}

    parts = [f"code={code!r}", f"info={info!r}"]
    if extra:
        parts.append(f"extra={extra!r}")
    return ", ".join(parts)


def format_bot_flag(mark_as_bot: bool) -> str:
    return "bot=1" if mark_as_bot else "bot=0"


def main() -> None:
    wiki_api = os.environ.get("WIKI_API", "").strip()
    wiki_page = os.environ.get("WIKI_PAGE", "").strip()
    bot_username = os.environ.get("BOT_USERNAME", "").strip()
    bot_password = os.environ.get("BOT_PASSWORD", "").strip()
    edit_tag_candidates_env = os.environ.get("EDIT_TAG_CANDIDATES")
    if edit_tag_candidates_env is None or not edit_tag_candidates_env.strip():
        edit_tag_candidates_raw = "bot, Bot"
    else:
        edit_tag_candidates_raw = edit_tag_candidates_env.strip()
    summary = os.environ.get("SUMMARY",
                             "自动更新用户贡献 Echart 所用的 JSON 数据页面").strip()
    user_agent = os.environ.get(
        "USER_AGENT",
        DEFAULT_USER_AGENT,
    ).strip()

    if not wiki_api:
        fail("Missing WIKI_API (set repository variable or env)")
    if not wiki_page:
        fail("Missing WIKI_PAGE (set repository variable or env)")
    if not bot_username:
        fail("Missing BOT_USERNAME secret")
    if not bot_password:
        fail("Missing BOT_PASSWORD secret")

    content_path = "echart_option.json"
    if not os.path.exists(content_path):
        fail(
            "echart_option.json not found; ensure generate_chart_json.py generated it"
        )

    try:
        with open(content_path, "r", encoding="utf-8") as file:
            new_text = file.read()
    except Exception as exc:
        fail("Failed to read echart_option.json", str(exc))

    session = build_session(user_agent)
    timeout = 30
    max_lag = 5
    assert_mode = "user"

    try:
        r1 = session.get(
            wiki_api,
            params={
                "action": "query",
                "meta": "tokens",
                "type": "login",
                "format": "json",
                "maxlag": max_lag,
            },
            timeout=timeout,
        )
        r1.raise_for_status()
        d1 = safe_get_json(r1)
    except Exception as exc:
        fail("Failed to fetch login token", str(exc))

    login_token = d1.get("query", {}).get("tokens", {}).get("logintoken")
    if not login_token:
        fail("Login token missing", d1)

    try:
        r2 = session.post(
            wiki_api,
            data={
                "action": "login",
                "lgname": bot_username,
                "lgpassword": bot_password,
                "lgtoken": login_token,
                "format": "json",
                "maxlag": max_lag,
            },
            timeout=timeout,
        )
        r2.raise_for_status()
        d2 = safe_get_json(r2)
    except Exception as exc:
        fail("Login request failed", str(exc))

    login_result = d2.get("login", {}).get("result")
    if login_result != "Success":
        fail("Login failed", d2)

    try:
        r_user = session.get(
            wiki_api,
            params={
                "action": "query",
                "meta": "userinfo",
                "uiprop": "groups",
                "format": "json",
                "assert": assert_mode,
                "maxlag": max_lag,
            },
            timeout=timeout,
        )
        r_user.raise_for_status()
        d_user = safe_get_json(r_user)
    except Exception as exc:
        fail("Failed to fetch user groups", str(exc))

    user_groups = d_user.get("query", {}).get("userinfo", {}).get("groups", [])
    has_bot_group = isinstance(user_groups, list) and "bot" in user_groups
    if has_bot_group:
        assert_mode = "bot"
    else:
        warn(f"用户 {bot_username or 'BOT_USERNAME'} 未持有机器人（bot）用户组；"
             "仍会先尝试 bot=1 编辑。"
             "持续以非机器人权限执行自动化编辑可能导致被封禁。")

    try:
        r3 = session.get(
            wiki_api,
            params={
                "action": "query",
                "meta": "tokens",
                "format": "json",
                "assert": assert_mode,
                "maxlag": max_lag,
            },
            timeout=timeout,
        )
        r3.raise_for_status()
        d3 = safe_get_json(r3)
    except Exception as exc:
        fail("Failed to fetch CSRF token", str(exc))

    csrf_token = d3.get("query", {}).get("tokens", {}).get("csrftoken")
    if not csrf_token:
        fail("CSRF token missing", d3)

    try:
        r4 = session.get(
            wiki_api,
            params={
                "action": "query",
                "prop": "revisions",
                "titles": wiki_page,
                "rvslots": "main",
                "rvprop": "content",
                "format": "json",
                "formatversion": "2",
                "assert": assert_mode,
                "maxlag": max_lag,
            },
            timeout=timeout,
        )
        r4.raise_for_status()
        d4 = safe_get_json(r4)
    except Exception as exc:
        fail("Failed to fetch current page content", str(exc))

    pages = d4.get("query", {}).get("pages", [])
    current_text = ""
    if isinstance(pages, list) and pages:
        revs = pages[0].get("revisions", [])
        if revs and isinstance(revs, list):
            current_text = revs[0].get("slots", {}).get("main",
                                                        {}).get("content", "")

    if current_text == new_text:
        print("No content changes detected; skip edit.")
        raise SystemExit(0)

    edit_tag_candidates = parse_edit_tag_candidates(edit_tag_candidates_raw)
    print(
        f"Edit tag candidates: {edit_tag_candidates!r}  (raw: {edit_tag_candidates_raw!r})"
    )
    if not edit_tag_candidates:
        warn("未解析到任何可用编辑标签；本次不会发送 tags 参数。"
             "请检查 EDIT_TAG_CANDIDATES 是否为空。")

    attempts: list[tuple[bool, str | None]] = []
    for mark_as_bot in (True, False):
        for tags in edit_tag_candidates:
            attempts.append((mark_as_bot, tags))
        attempts.append((mark_as_bot, None))

    d5: dict[str, Any] = {}
    warned_bot_fallback = False
    warned_tag_fallback = False
    attempt_logs: list[str] = []
    success_attempt_context: str | None = None

    for attempt_index, (mark_as_bot, tags) in enumerate(attempts, start=1):
        bot_flag_text = format_bot_flag(mark_as_bot)
        attempt_context = (f"attempt={attempt_index}, "
                           f"{bot_flag_text}, tags={tags!r}")
        print(f"Edit attempt started: {attempt_context}")
        try:
            d5 = post_edit(
                session=session,
                wiki_api=wiki_api,
                wiki_page=wiki_page,
                new_text=new_text,
                csrf_token=csrf_token,
                timeout=timeout,
                max_lag=max_lag,
                assert_mode=assert_mode,
                mark_as_bot=mark_as_bot,
                tags=tags,
                summary=summary,
            )
        except Exception as exc:
            fail(f"Edit request failed ({attempt_context})", str(exc))

        if d5.get("edit", {}).get("result") == "Success":
            success_attempt_context = attempt_context
            print(f"Edit attempt succeeded: {attempt_context}")
            break

        error_text = format_api_error(d5)
        attempt_logs.append(f"{attempt_context}; {error_text}")
        warn(f"编辑尝试失败：{attempt_context}; {error_text}")

        if is_tag_error(d5) and tags:
            if not warned_tag_fallback:
                warn("目标站点可能不支持部分变更标签；"
                     "将以其他标签或不带标签继续尝试。"
                     f"失败详情：{error_text}")
                warned_tag_fallback = True
            continue

        if is_bot_permission_error(d5) and mark_as_bot:
            if not warned_bot_fallback:
                warn(f"本次 bot=1 编辑被拒绝，"
                     "将回退到不带 bot 标记继续尝试。"
                     f"失败详情：{error_text}")
            warned_bot_fallback = True
            continue

        fail("Wiki edit failed", d5)

    if d5.get("edit", {}).get("result") != "Success":
        fail("Wiki edit failed after all fallbacks", {
            "last_response": d5,
            "attempt_logs": attempt_logs,
        })

    print("Wiki page updated successfully.")


if __name__ == "__main__":
    main()
