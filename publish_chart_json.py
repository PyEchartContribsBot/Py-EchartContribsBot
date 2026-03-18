from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import requests
from mw_runtime import (
    DEFAULT_USER_AGENT,
    api_get_json,
    api_post_json,
    build_session,
    get_csrf_token,
    get_user_groups,
    load_env_file,
    login_with_bot_password,
)

load_env_file()


def fail(message: str, detail: Any = None) -> None:
    if detail is not None:
        print(f"ERROR: {message}: {detail}", file=sys.stderr)
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"::warning::{message}")


@dataclass(frozen=True)
class PublishConfig:
    wiki_api: str
    wiki_page: str
    bot_username: str
    bot_password: str
    edit_tag_candidates_raw: str
    summary: str
    user_agent: str
    content_path: str = "echart_option.json"
    timeout: int = 30
    max_lag: int = 5


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

    return api_post_json(
        session=session,
        wiki_api=wiki_api,
        data=payload,
        timeout=timeout,
        error_context="Edit request failed",
    )


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
    # Preserve input order while removing empty and duplicate tags.
    stripped_tags = (token.strip() for token in raw_value.split(","))
    return list(dict.fromkeys(tag for tag in stripped_tags if tag))


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


def get_trimmed_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def resolve_edit_tag_candidates_raw() -> str:
    value = os.environ.get("EDIT_TAG_CANDIDATES")
    if value is None:
        return "bot, Bot"

    trimmed = value.strip()
    return trimmed or "bot, Bot"


def read_local_chart_option(content_path: str) -> str:
    if not os.path.exists(content_path):
        fail(
            "echart_option.json not found; ensure generate_chart_json.py generated it"
        )

    try:
        with open(content_path, "r", encoding="utf-8") as file:
            return file.read()
    except Exception as exc:
        fail("Failed to read echart_option.json", str(exc))


def build_edit_attempts(
    edit_tag_candidates: list[str],
) -> list[tuple[bool, str | None]]:
    tags_by_priority: list[str | None] = [*edit_tag_candidates, None]
    return [
        (mark_as_bot, tags)
        for mark_as_bot in (True, False)
        for tags in tags_by_priority
    ]


def load_publish_config() -> PublishConfig:
    return PublishConfig(
        wiki_api=get_trimmed_env("WIKI_API"),
        wiki_page=get_trimmed_env("WIKI_PAGE"),
        bot_username=get_trimmed_env("BOT_USERNAME"),
        bot_password=get_trimmed_env("BOT_PASSWORD"),
        edit_tag_candidates_raw=resolve_edit_tag_candidates_raw(),
        summary=get_trimmed_env("SUMMARY", "自动更新用户贡献 Echart 所用的 JSON 数据页面"),
        user_agent=get_trimmed_env("USER_AGENT", DEFAULT_USER_AGENT),
    )


def validate_publish_config(config: PublishConfig) -> None:
    if not config.wiki_api:
        fail("Missing WIKI_API (set repository variable or env)")
    if not config.wiki_page:
        fail("Missing WIKI_PAGE (set repository variable or env)")
    if not config.bot_username:
        fail("Missing BOT_USERNAME secret")
    if not config.bot_password:
        fail("Missing BOT_PASSWORD secret")


def login_or_fail(session: requests.Session, config: PublishConfig) -> None:
    try:
        login_with_bot_password(
            session=session,
            wiki_api=config.wiki_api,
            bot_username=config.bot_username,
            bot_password=config.bot_password,
            timeout=config.timeout,
            max_lag=config.max_lag,
        )
    except RuntimeError as exc:
        fail("Login failed", str(exc))


def resolve_assert_mode(session: requests.Session, config: PublishConfig) -> str:
    assert_mode = "user"
    try:
        user_groups = get_user_groups(
            session=session,
            wiki_api=config.wiki_api,
            timeout=config.timeout,
            max_lag=config.max_lag,
            assert_mode=assert_mode,
        )
    except RuntimeError as exc:
        fail("Failed to fetch user groups", str(exc))

    has_bot_group = "bot" in user_groups
    if has_bot_group:
        return "bot"

    warn(f"用户 {config.bot_username or 'BOT_USERNAME'} 未持有机器人（bot）用户组；"
         "仍会先尝试 bot=1 编辑。"
         "持续以非机器人权限执行自动化编辑可能导致被封禁。")
    return assert_mode


def get_csrf_token_or_fail(
    session: requests.Session,
    config: PublishConfig,
    assert_mode: str,
) -> str:
    try:
        return get_csrf_token(
            session=session,
            wiki_api=config.wiki_api,
            timeout=config.timeout,
            max_lag=config.max_lag,
            assert_mode=assert_mode,
        )
    except RuntimeError as exc:
        fail("Failed to fetch CSRF token", str(exc))


def fetch_current_page_content(
    session: requests.Session,
    config: PublishConfig,
    assert_mode: str,
) -> str:
    try:
        data = api_get_json(
            session=session,
            wiki_api=config.wiki_api,
            params={
                "action": "query",
                "prop": "revisions",
                "titles": config.wiki_page,
                "rvslots": "main",
                "rvprop": "content",
                "format": "json",
                "formatversion": "2",
                "assert": assert_mode,
                "maxlag": config.max_lag,
            },
            timeout=config.timeout,
            error_context="Failed to fetch current page content",
        )
    except RuntimeError as exc:
        fail("Failed to fetch current page content", str(exc))

    pages = data.get("query", {}).get("pages", [])
    if not isinstance(pages, list) or not pages:
        return ""

    revisions = pages[0].get("revisions", [])
    if not isinstance(revisions, list) or not revisions:
        return ""

    return revisions[0].get("slots", {}).get("main", {}).get("content", "")


def try_edit_with_fallbacks(
    session: requests.Session,
    config: PublishConfig,
    assert_mode: str,
    csrf_token: str,
    new_text: str,
    attempts: list[tuple[bool, str | None]],
) -> None:
    d5: dict[str, Any] = {}
    warned_bot_fallback = False
    warned_tag_fallback = False
    attempt_logs: list[str] = []

    for attempt_index, (mark_as_bot, tags) in enumerate(attempts, start=1):
        bot_flag_text = format_bot_flag(mark_as_bot)
        attempt_context = (f"attempt={attempt_index}, "
                           f"{bot_flag_text}, tags={tags!r}")
        print(f"Edit attempt started: {attempt_context}")
        try:
            d5 = post_edit(
                session=session,
                wiki_api=config.wiki_api,
                wiki_page=config.wiki_page,
                new_text=new_text,
                csrf_token=csrf_token,
                timeout=config.timeout,
                max_lag=config.max_lag,
                assert_mode=assert_mode,
                mark_as_bot=mark_as_bot,
                tags=tags,
                summary=config.summary,
            )
        except RuntimeError as exc:
            fail(f"Edit request failed ({attempt_context})", str(exc))

        if d5.get("edit", {}).get("result") == "Success":
            print(f"Edit attempt succeeded: {attempt_context}")
            print("Wiki page updated successfully.")
            return

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

    fail("Wiki edit failed after all fallbacks", {
        "last_response": d5,
        "attempt_logs": attempt_logs,
    })


def main() -> None:
    config = load_publish_config()
    validate_publish_config(config)

    new_text = read_local_chart_option(config.content_path)
    session = build_session(config.user_agent)

    login_or_fail(session, config)
    assert_mode = resolve_assert_mode(session, config)
    csrf_token = get_csrf_token_or_fail(session, config, assert_mode)
    current_text = fetch_current_page_content(session, config, assert_mode)

    if current_text == new_text:
        print("No content changes detected; skip edit.")
        raise SystemExit(0)

    edit_tag_candidates = parse_edit_tag_candidates(config.edit_tag_candidates_raw)
    print(
        f"Edit tag candidates: {edit_tag_candidates!r}  (raw: {config.edit_tag_candidates_raw!r})"
    )
    if not edit_tag_candidates:
        warn("未解析到任何可用编辑标签；本次不会发送 tags 参数。"
             "请检查 EDIT_TAG_CANDIDATES 是否为空。")

    attempts = build_edit_attempts(edit_tag_candidates)
    try_edit_with_fallbacks(
        session=session,
        config=config,
        assert_mode=assert_mode,
        csrf_token=csrf_token,
        new_text=new_text,
        attempts=attempts,
    )


if __name__ == "__main__":
    main()
