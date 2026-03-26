from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from chart_sort_modes import (
    build_option_for_sort_mode,
    parse_account_reg_marker_out_of_range,
    parse_chart_sort_mode,
    parse_multi_series_render_mode,
)
from mw_runtime import (
    DEFAULT_USER_AGENT,
    api_get_json,
    build_session,
    fetch_account_registrations,
    fetch_namespaces,
    load_env_file,
    login_with_bot_password,
    parse_bool_env,
)

load_env_file()


def _parse_excluded_namespaces(raw_value: str) -> set[int] | None:
    """将逗号分隔的命名空间字符串解析为整数集合。

    - 空值：返回 None，触发自动推断（排除 ns=2 和奇数命名空间）
    - "false"/"null"/"none"：返回空 set()，表示不排除任何命名空间
    - 其他值：按逗号分隔解析为整数集合
    """
    value = raw_value.strip().lower()
    if not value:
        return None

    # 显式指定不排除任何命名空间
    if value in {"false", "null", "none"}:
        return set()

    namespace_ids: set[int] = set()
    for part in raw_value.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            namespace_ids.add(int(token))
        except ValueError as exc:
            raise RuntimeError("环境变量 EXCLUDED_NAMESPACES 格式错误："
                               f"{raw_value}。请使用逗号分隔的整数或 false/null/none，例如 1,2,3,5") from exc

    return namespace_ids


def _parse_namespace_mode(raw_value: str) -> str:
    mode = raw_value.strip().lower()
    if not mode:
        return "top"
    if mode not in {"top", "all"}:
        raise RuntimeError(
            "环境变量 NAMESPACE_MODE 仅支持 top 或 all，例如 NAMESPACE_MODE=top")
    return mode


def _parse_top_namespace_limit(raw_value: str) -> int:
    value = raw_value.strip()
    if not value:
        return 10
    try:
        limit = int(value)
    except ValueError as exc:
        raise RuntimeError(
            "环境变量 TOP_NAMESPACE_LIMIT 必须是正整数，例如 TOP_NAMESPACE_LIMIT=10"
        ) from exc
    if limit <= 0:
        raise RuntimeError("环境变量 TOP_NAMESPACE_LIMIT 必须大于 0")
    return limit


def _parse_chart_series_type(raw_value: str) -> str:
    value = raw_value.strip().lower()
    if not value:
        return "bar"
    if value not in {"bar", "line"}:
        raise RuntimeError(
            "环境变量 CHART_SERIES_TYPE 仅支持 bar 或 line（仅控制初始展示类型），"
            "例如 CHART_SERIES_TYPE=bar")
    return value


def _parse_multi_series_render_mode(raw_value: str) -> str:
    return parse_multi_series_render_mode(raw_value)


def _extract_first_user(user_str: str) -> str:
    """从可能包含多个用户（以|或%7C分隔）的字符串中提取第一个用户。"""
    if not user_str:
        return user_str

    delimiter = next((item for item in ("|", "%7C") if item in user_str), None)
    return user_str.split(delimiter)[0].strip() if delimiter else user_str


def _parse_multiple_users(user_str: str) -> list[str]:
    """从可能包含多个用户（以|或%7C分隔）的字符串中提取所有用户。

    按照给定的顺序返回去除空格的用户名列表。
    """
    if not user_str:
        return []

    delimiter = next((item for item in ("|", "%7C") if item in user_str), None)
    if not delimiter:
        return [user_str.strip()]

    users = [u.strip() for u in user_str.split(delimiter)]
    return [u for u in users if u]  # 过滤掉空字符串


# ===== 可配置参数 =====
WIKI_API: str = os.environ.get("WIKI_API", "").strip()  # 必填：目标站点 API
USER: str = os.environ.get("WIKI_USER", "").strip()  # 必填：统计目标用户名
DISPLAY_NAME: str = os.environ.get("DISPLAY_NAME",
                                   "").strip() or _extract_first_user(
                                       USER)  # 用于图表显示的别名，默认等效 WIKI_USER 的第一个用户
EXCLUDED_NAMESPACES: set[int] | None = _parse_excluded_namespaces(
    os.environ.get("EXCLUDED_NAMESPACES", ""))
NAMESPACE_MODE: str = _parse_namespace_mode(
    os.environ.get("NAMESPACE_MODE", "top"))
TOP_NAMESPACE_LIMIT: int = _parse_top_namespace_limit(
    os.environ.get("TOP_NAMESPACE_LIMIT", "10"))
CHART_SERIES_TYPE: str = _parse_chart_series_type(
    os.environ.get("CHART_SERIES_TYPE", "bar"))  # 仅控制初始 series.type
MULTI_SERIES_RENDER_MODE: str = _parse_multi_series_render_mode(
    os.environ.get("MULTI_SERIES_RENDER_MODE", "stacked"))
CHART_SORT_MODE = parse_chart_sort_mode(
    os.environ.get("CHART_SORT_MODE", "namespace"))
OUTPUT_FILE: str = "echart_option.json"
REQUEST_TIMEOUT_SECONDS: int = 30

# User-Agent 符合 MediaWiki API 礼仪要求
USER_AGENT: str = os.environ.get(
    "USER_AGENT",
    DEFAULT_USER_AGENT,
).strip()
MAX_LAG: int = 5  # 最大数据库延迟（秒），用于非交互式任务
BOT_LOGIN_USERNAME: str = os.environ.get("BOT_USERNAME", "").strip()
BOT_LOGIN_PASSWORD: str = os.environ.get("BOT_PASSWORD", "").strip()
USERCONTRIBS_LIMIT: str = "max"
USERCONTRIBS_FALLBACK_LIMIT: str = "499"

# 注册时间标记配置（全模式可用）
ACCOUNT_REG_MARKER_ENABLED: bool = parse_bool_env(
    os.environ.get("ACCOUNT_REG_MARKER_ENABLED", "false"),
    default=False,
)
ACCOUNT_REG_MARKER_OUT_OF_RANGE: str = parse_account_reg_marker_out_of_range(
    os.environ.get("ACCOUNT_REG_MARKER_OUT_OF_RANGE", "clamp_to_first"))


def _validate_required_config() -> None:
    missing: list[str] = []
    if not WIKI_API:
        missing.append("WIKI_API")
    if not USER:
        missing.append("WIKI_USER")
    if missing:
        raise RuntimeError("缺少必要环境变量: " + ", ".join(missing) +
                           "。请创建 .env（可从 .env.example 复制）或在系统环境中设置。")


def _login_if_configured(session: requests.Session, api_url: str) -> None:
    if not BOT_LOGIN_USERNAME or not BOT_LOGIN_PASSWORD:
        return

    try:
        login_with_bot_password(
            session=session,
            wiki_api=api_url,
            bot_username=BOT_LOGIN_USERNAME,
            bot_password=BOT_LOGIN_PASSWORD,
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_lag=MAX_LAG,
        )
    except RuntimeError as exc:
        raise RuntimeError(f"API 登录失败: {exc}") from exc


def fetch_all_contribs(api_url: str, user: str) -> list[dict[str, Any]]:
    """调用 MediaWiki API 拉取指定用户的全部 usercontribs（含 continue 分页）。"""
    session = build_session(USER_AGENT)
    _login_if_configured(session, api_url)
    all_contribs: list[dict[str, Any]] = []

    params: dict[str, Any] = {
        "action": "query",
        "format": "json",
        "list": "usercontribs",
        "ucuser": user,
        "uclimit": USERCONTRIBS_LIMIT,
        "ucprop": "ids|title|timestamp|comment|size|sizediff|flags|tags",
        "maxlag": MAX_LAG,  # 避免在服务器高负载时运行
    }

    continue_params: dict[str, Any] = {}

    while True:
        request_params = {**params, **continue_params}

        try:
            data = api_get_json(
                session=session,
                wiki_api=api_url,
                params=request_params,
                timeout=REQUEST_TIMEOUT_SECONDS,
                error_context="请求 MediaWiki API 失败",
            )
        except RuntimeError as exc:
            raise RuntimeError(str(exc)) from exc

        if "error" in data:
            api_error = data["error"]
            code = api_error.get("code", "unknown")
            info = api_error.get("info", "no details")
            if code == "action-notallowed" and params.get(
                    "uclimit") == USERCONTRIBS_LIMIT:
                params["uclimit"] = USERCONTRIBS_FALLBACK_LIMIT
                continue
            if code == "action-notallowed":
                raise RuntimeError(
                    "MediaWiki API 返回错误: code=action-notallowed, "
                    "info=Unauthorized API call。目标站点可能要求先登录，"
                    "请在环境变量中提供 BOT_USERNAME/BOT_PASSWORD。")
            raise RuntimeError(f"MediaWiki API 返回错误: code={code}, info={info}")

        contribs = data.get("query", {}).get("usercontribs", [])
        if not isinstance(contribs, list):
            raise RuntimeError("API 响应格式异常: query.usercontribs 不是列表")

        all_contribs.extend(contribs)

        if "continue" not in data:
            break
        next_continue = data["continue"]
        if not isinstance(next_continue, dict):
            raise RuntimeError("API 响应格式异常: continue 不是对象")
        continue_params = next_continue

    return all_contribs


def _auto_excluded_namespaces_from_contribs(
        contribs: list[dict[str, Any]]) -> set[int]:
    detected_namespaces: set[int] = set()
    for item in contribs:
        ns = item.get("ns")
        if isinstance(ns, int):
            detected_namespaces.add(ns)

    # 自动排除用户命名空间（2）和奇数命名空间（常见讨论页）。
    return {
        ns_id
        for ns_id in detected_namespaces if ns_id == 2 or ns_id % 2 == 1
    }


def _resolve_excluded_namespaces(
    contribs: list[dict[str, Any]],
    configured_excluded_namespaces: set[int] | None,
) -> tuple[set[int], bool]:
    """返回排除的命名空间集合和是否为自动推断的标记。

    Returns:
        (excluded_namespaces, is_auto_inferred)
    """
    if configured_excluded_namespaces is not None:
        return configured_excluded_namespaces, False
    return _auto_excluded_namespaces_from_contribs(contribs), True


def filter_namespace(contribs: list[dict[str, Any]],
                     excluded_namespaces: set[int]) -> list[dict[str, Any]]:
    """过滤掉指定命名空间。"""
    if not excluded_namespaces:
        return contribs

    filtered: list[dict[str, Any]] = []
    for item in contribs:
        ns = item.get("ns")
        if isinstance(ns, int) and ns in excluded_namespaces:
            continue
        filtered.append(item)
    return filtered


def _build_generated_time() -> str:
    now_utc = datetime.now(timezone.utc)
    return (f"{now_utc.year}年{now_utc.month}月{now_utc.day}日"
            f"{now_utc.hour:02d}:{now_utc.minute:02d}〔UTC〕")


def _group_contribs_by_user(
    contribs: list[dict[str, Any]],
    user_order: list[str],
    excluded_namespaces: set[int],
) -> dict[str, list[dict[str, Any]]]:
    """根据贡献中的 'user' 字段将贡献分组，并应用命名空间过滤。

    Args:
        contribs: 从 API 获取的贡献列表
        user_order: 用户的预期顺序
        excluded_namespaces: 需要排除的命名空间集合

    Returns:
        键为用户名，值为该用户的已过滤 contribs 列表的字典（按 user_order 顺序）
    """
    # 先按用户名分组
    grouped: dict[str, list[dict[str, Any]]] = {}
    for contrib in contribs:
        user = contrib.get("user")
        if not isinstance(user, str):
            continue
        if user not in grouped:
            grouped[user] = []
        grouped[user].append(contrib)

    # 应用命名空间过滤，并按 user_order 顺序构建结果
    result: dict[str, list[dict[str, Any]]] = {}
    for user in user_order:
        if user in grouped:
            filtered = filter_namespace(grouped[user], excluded_namespaces)
            result[user] = filtered
        else:
            result[user] = []

    return result


def main() -> None:
    """主流程：抓取、过滤、聚合、生成并写出 JSON。"""
    try:
        _validate_required_config()

        # 获取命名空间映射
        session = build_session(USER_AGENT)
        _login_if_configured(session, WIKI_API)
        namespace_map = fetch_namespaces(session, WIKI_API, REQUEST_TIMEOUT_SECONDS)

        generated_time = _build_generated_time()

        # 全模式通用：可选注册时间标记
        account_registrations: dict[str, str] = {}
        if ACCOUNT_REG_MARKER_ENABLED:
            users_for_markers = _parse_multiple_users(USER)
            try:
                account_registrations = fetch_account_registrations(
                    session=session,
                    wiki_api=WIKI_API,
                    users=users_for_markers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    max_lag=MAX_LAG,
                )
            except RuntimeError as exc:
                print(f"警告：无法查询账户注册时间: {exc}", file=sys.stderr)

        # account 模式：拉取多个用户的贡献（单个 API 请求）
        if CHART_SORT_MODE == "account":
            users = _parse_multiple_users(USER)
            if not users:
                raise RuntimeError("WIKI_USER 为空或格式错误")

            # 调用单个 API 查询，传入用管道符分隔的用户列表
            all_contribs = fetch_all_contribs(WIKI_API, USER)

            # 推断排除的命名空间
            excluded_namespaces, is_auto_inferred = _resolve_excluded_namespaces(
                all_contribs,
                EXCLUDED_NAMESPACES,
            )

            # 按用户分组贡献（已应用命名空间过滤）
            accounts_contribs = _group_contribs_by_user(
                all_contribs, users, excluded_namespaces
            )
            total_edits = sum(len(contribs) for contribs in accounts_contribs.values())
            print(f"统计总编辑数（过滤后）: {total_edits}")

            option = build_option_for_sort_mode(
                chart_sort_mode=CHART_SORT_MODE,
                display_name=DISPLAY_NAME,
                contribs=[],  # account 模式不使用此参数
                generated_time=generated_time,
                chart_series_type=CHART_SERIES_TYPE,
                multi_series_render_mode=MULTI_SERIES_RENDER_MODE,
                excluded_namespaces=excluded_namespaces,
                namespace_mode="",  # account 模式不使用此参数
                top_namespace_limit=0,  # account 模式不使用此参数
                namespace_map=namespace_map,
                accounts_contribs=accounts_contribs,
                account_order=users,
                is_auto_inferred_namespaces=is_auto_inferred,
                account_registrations=account_registrations,
                account_reg_marker_out_of_range=ACCOUNT_REG_MARKER_OUT_OF_RANGE,
            )
        else:
            # namespace 或 sum 模式：拉取单个用户的贡献
            all_contribs = fetch_all_contribs(WIKI_API, USER)
            excluded_namespaces, is_auto_inferred = _resolve_excluded_namespaces(
                all_contribs,
                EXCLUDED_NAMESPACES,
            )
            filtered_contribs = filter_namespace(
                all_contribs,
                excluded_namespaces,
            )

            print(f"统计总编辑数（过滤后）: {len(filtered_contribs)}")

            option = build_option_for_sort_mode(
                chart_sort_mode=CHART_SORT_MODE,
                display_name=DISPLAY_NAME,
                contribs=filtered_contribs,
                generated_time=generated_time,
                chart_series_type=CHART_SERIES_TYPE,
                multi_series_render_mode=MULTI_SERIES_RENDER_MODE,
                excluded_namespaces=excluded_namespaces,
                namespace_mode=NAMESPACE_MODE,
                top_namespace_limit=TOP_NAMESPACE_LIMIT,
                namespace_map=namespace_map,
                is_auto_inferred_namespaces=is_auto_inferred,
                account_registrations=account_registrations,
                account_reg_marker_out_of_range=ACCOUNT_REG_MARKER_OUT_OF_RANGE,
            )

        output_path = Path(OUTPUT_FILE)
        output_path.write_text(
            json.dumps(option, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )

        print(f"已输出 ECharts option 到: {output_path.resolve()}")

    except Exception as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
