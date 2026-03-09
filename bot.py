from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests import Response
from requests.exceptions import RequestException


def _load_env_file(env_path: str = ".env") -> None:
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


_load_env_file()


def _parse_excluded_namespaces(raw_value: str) -> set[int]:
    """将逗号分隔的命名空间字符串解析为整数集合。"""
    default_namespaces: set[int] = {
        1,
        2,
        3,
        5,
        7,
        9,
        11,
        13,
        15,
        829,
    }

    value = raw_value.strip()
    if not value:
        return default_namespaces

    namespace_ids: set[int] = set()
    for part in value.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            namespace_ids.add(int(token))
        except ValueError as exc:
            raise RuntimeError("环境变量 EXCLUDED_NAMESPACES 格式错误："
                               f"{raw_value}。请使用逗号分隔的整数，例如 1,2,3,5") from exc

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
            "环境变量 CHART_SERIES_TYPE 仅支持 bar 或 line，例如 CHART_SERIES_TYPE=bar"
        )
    return value


# ===== 可配置参数 =====
API_URL: str = os.environ.get("API_URL", "").strip()  # 必填：目标站点 API
USER: str = os.environ.get("WIKI_USER", "").strip()  # 必填：统计目标用户名
DISPLAY_NAME: str = os.environ.get(
    "DISPLAY_NAME", "").strip() or USER  # 用于图表显示的别名，默认等效 WIKI_USER
EXCLUDED_NAMESPACES: set[int] = _parse_excluded_namespaces(
    os.environ.get("EXCLUDED_NAMESPACES", ""))
NAMESPACE_MODE: str = _parse_namespace_mode(
    os.environ.get("NAMESPACE_MODE", "top"))
TOP_NAMESPACE_LIMIT: int = _parse_top_namespace_limit(
    os.environ.get("TOP_NAMESPACE_LIMIT", "10"))
CHART_SERIES_TYPE: str = _parse_chart_series_type(
    os.environ.get("CHART_SERIES_TYPE", "bar"))
OUTPUT_FILE: str = "echart_option.json"
REQUEST_TIMEOUT_SECONDS: int = 30

# User-Agent 符合 MediaWiki API 礼仪要求
USER_AGENT: str = os.environ.get(
    "USER_AGENT",
    "WikiChartBot/1.0 (https://github.com/your-org/your-repo; "
    "contact@example.org) requests/2.x",
).strip()
MAX_LAG: int = 5  # 最大数据库延迟（秒），用于非交互式任务
BOT_LOGIN_USERNAME: str = os.environ.get("BOT_USERNAME", "").strip()
BOT_LOGIN_PASSWORD: str = os.environ.get("BOT_PASSWORD", "").strip()
USERCONTRIBS_LIMIT: str = "max"
USERCONTRIBS_FALLBACK_LIMIT: str = "500"


def _validate_required_config() -> None:
    missing: list[str] = []
    if not API_URL:
        missing.append("API_URL")
    if not USER:
        missing.append("WIKI_USER")
    if missing:
        raise RuntimeError("缺少必要环境变量: " + ", ".join(missing) +
                           "。请创建 .env（可从 .env.example 复制）或在系统环境中设置。")


def _safe_get_json(response: Response) -> dict[str, Any]:
    """安全解析 JSON，并在失败时抛出包含上下文的异常。"""
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"API 返回了非 JSON 响应，HTTP {response.status_code}") from exc


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip",
    })
    return session


def _login_if_configured(session: requests.Session, api_url: str) -> None:
    if not BOT_LOGIN_USERNAME or not BOT_LOGIN_PASSWORD:
        return

    try:
        token_response = session.get(
            api_url,
            params={
                "action": "query",
                "meta": "tokens",
                "type": "login",
                "format": "json",
                "maxlag": MAX_LAG,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        token_response.raise_for_status()
        token_data = _safe_get_json(token_response)
    except RequestException as exc:
        raise RuntimeError(f"获取登录 token 失败: {exc}") from exc

    login_token = token_data.get("query", {}).get("tokens",
                                                  {}).get("logintoken")
    if not isinstance(login_token, str) or not login_token:
        raise RuntimeError("获取登录 token 失败: 响应中缺少 logintoken")

    try:
        login_response = session.post(
            api_url,
            data={
                "action": "login",
                "lgname": BOT_LOGIN_USERNAME,
                "lgpassword": BOT_LOGIN_PASSWORD,
                "lgtoken": login_token,
                "format": "json",
                "maxlag": MAX_LAG,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        login_response.raise_for_status()
        login_data = _safe_get_json(login_response)
    except RequestException as exc:
        raise RuntimeError(f"登录请求失败: {exc}") from exc

    login_result = login_data.get("login", {}).get("result")
    if login_result != "Success":
        raise RuntimeError(f"API 登录失败: {login_data}")


def fetch_all_contribs(api_url: str, user: str) -> list[dict[str, Any]]:
    """调用 MediaWiki API 拉取指定用户的全部 usercontribs（含 continue 分页）。"""
    session = _build_session()
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
            response = session.get(
                api_url,
                params=request_params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except RequestException as exc:
            raise RuntimeError(f"请求 MediaWiki API 失败: {exc}") from exc

        data = _safe_get_json(response)

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


def group_by_month_and_namespace(
    contribs: list[dict[str, Any]],
) -> tuple[list[tuple[int, int]], dict[int, list[int]], dict[int, int]]:
    """按年月和命名空间统计编辑数，并补齐完整月份轴。"""
    monthly_namespace_counter: Counter[tuple[int, int, int]] = Counter()
    month_counter: Counter[tuple[int, int]] = Counter()
    namespace_totals: Counter[int] = Counter()

    for item in contribs:
        timestamp = item.get("timestamp")
        ns = item.get("ns")
        if not isinstance(timestamp, str) or not isinstance(ns, int):
            continue

        try:
            dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue

        key = (dt.year, dt.month, ns)
        monthly_namespace_counter[key] += 1
        month_counter[(dt.year, dt.month)] += 1
        namespace_totals[ns] += 1

    if not month_counter:
        return [], {}, {}

    sorted_months = sorted(month_counter.keys())
    start_year, start_month = sorted_months[0]
    end_year, end_month = sorted_months[-1]

    full_months: list[tuple[int, int]] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        full_months.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1

    namespace_month_counts: dict[int, list[int]] = {}
    for ns_id in namespace_totals:
        namespace_month_counts[ns_id] = [
            monthly_namespace_counter.get((year, month, ns_id), 0)
            for year, month in full_months
        ]

    return full_months, namespace_month_counts, dict(namespace_totals)


def _build_namespace_name(ns_id: int) -> str:
    if ns_id == 0:
        return "（主）"
    return f"{{{{ns:{ns_id}}}}}"


def _select_series_namespaces(
    namespace_totals: dict[int, int],
    namespace_mode: str,
    top_namespace_limit: int,
) -> tuple[list[int], set[int]]:
    ordered_namespaces = sorted(
        namespace_totals,
        key=lambda ns_id: (-namespace_totals[ns_id], ns_id),
    )
    if namespace_mode == "all" or len(
            ordered_namespaces) <= top_namespace_limit:
        return ordered_namespaces, set()

    kept = ordered_namespaces[:top_namespace_limit]
    merged = set(ordered_namespaces[top_namespace_limit:])
    return kept, merged


def _namespace_hue(ns_id: int) -> int:
    # Multiplicative hashing keeps color mapping stable while distributing hues.
    return int((ns_id * 2654435761) % 360)


def _pick_lightness(variant_index: int) -> int:
    cycle = [48, 58, 40, 66]
    return cycle[variant_index % len(cycle)]


def _build_namespace_colors(
        namespace_ids: list[int]) -> dict[int, dict[str, str]]:
    hue_variant_counts: dict[int, int] = {}
    color_map: dict[int, dict[str, str]] = {}

    for ns_id in namespace_ids:
        hue = _namespace_hue(ns_id)
        variant_index = hue_variant_counts.get(hue, 0)
        hue_variant_counts[hue] = variant_index + 1

        lightness = _pick_lightness(variant_index)
        line_color = f"hsl({hue}, 62%, {lightness}%)"
        area_color = f"hsla({hue}, 62%, {lightness}%, 0.35)"
        color_map[ns_id] = {
            "line": line_color,
            "area": area_color,
        }

    return color_map


def _build_excluded_namespaces_text(excluded_namespaces: set[int]) -> str:
    if not excluded_namespaces:
        return "未排除命名空间"

    sorted_ids = sorted(excluded_namespaces)
    preview_count = 3
    preview_labels = [
        _build_namespace_name(ns_id) for ns_id in sorted_ids[:preview_count]
    ]
    if len(sorted_ids) <= preview_count:
        return "已排除：" + "、".join(preview_labels)

    return ("已排除：" + "、".join(preview_labels) + f" 等{len(sorted_ids)}个命名空间")


def _build_series_style(
    chart_series_type: str,
    line_color: str,
    area_color: str,
) -> dict[str, Any]:
    if chart_series_type == "line":
        return {
            "showSymbol": False,
            "lineStyle": {
                "width": 1.8,
                "color": line_color,
            },
            "areaStyle": {
                "color": area_color,
            },
        }

    return {
        "barMaxWidth": 28,
    }


def build_option(
    display_name: str,
    full_months: list[tuple[int, int]],
    namespace_month_counts: dict[int, list[int]],
    namespace_totals: dict[int, int],
    excluded_namespaces: set[int],
    namespace_mode: str,
    top_namespace_limit: int,
    chart_series_type: str,
) -> dict[str, Any]:
    """构建完整 Apache ECharts option JSON。"""
    now_utc = datetime.now(timezone.utc)
    generated_time = (f"{now_utc.year}年{now_utc.month}月{now_utc.day}日"
                      f"{now_utc.hour:02d}:{now_utc.minute:02d}〔UTC〕")

    x_labels = [f"{year}年{month}月" for year, month in full_months]

    selected_namespace_ids, merged_namespace_ids = _select_series_namespaces(
        namespace_totals=namespace_totals,
        namespace_mode=namespace_mode,
        top_namespace_limit=top_namespace_limit,
    )
    namespace_colors = _build_namespace_colors(selected_namespace_ids)

    legend_data: list[str] = []
    series: list[dict[str, Any]] = []
    for ns_id in selected_namespace_ids:
        ns_name = _build_namespace_name(ns_id)
        colors = namespace_colors[ns_id]
        legend_data.append(ns_name)
        series.append({
            "name":
            ns_name,
            "type":
            chart_series_type,
            "stack":
            "Total",
            "itemStyle": {
                "color": colors["line"]
            },
            "emphasis": {
                "focus": "series"
            },
            "data":
            namespace_month_counts.get(ns_id, [0] * len(x_labels)),
            **_build_series_style(
                chart_series_type=chart_series_type,
                line_color=colors["line"],
                area_color=colors["area"],
            ),
        })

    if merged_namespace_ids:
        other_data = [0] * len(x_labels)
        for ns_id in merged_namespace_ids:
            data = namespace_month_counts.get(ns_id, [0] * len(x_labels))
            other_data = [
                left + right for left, right in zip(other_data, data)
            ]

        other_name = "其他命名空间"
        legend_data.append(other_name)
        series.append({
            "name": other_name,
            "type": chart_series_type,
            "stack": "Total",
            "itemStyle": {
                "color": "hsl(0, 0%, 45%)"
            },
            "emphasis": {
                "focus": "series"
            },
            "data": other_data,
            **_build_series_style(
                chart_series_type=chart_series_type,
                line_color="hsl(0, 0%, 45%)",
                area_color="hsla(0, 0%, 45%, 0.35)",
            ),
        })

    subtext = ("按月按命名空间统计\n"
               f"{_build_excluded_namespaces_text(excluded_namespaces)}\n"
               f"（截至 {generated_time}）")

    option: dict[str, Any] = {
        "title": {
            "text": f"{display_name}的编辑历史",
            "subtext": subtext,
            "top": 8,
            "left": "center",
            "itemGap": 10,
            "subtextStyle": {
                "lineHeight": 18
            }
        },
        "grid": {
            "top": 150,
            "left": "10%",
            "right": "10%",
            "bottom": 95,
            "containLabel": True
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {
                "type": "cross",
                "animation": False
            }
        },
        "toolbox": {
            "show": True,
            "feature": {
                "dataZoom": {
                    "yAxisIndex": "none"
                },
                "magicType": {
                    "type": ["line", "bar"]
                },
                "restore": {},
                "saveAsImage": {
                    "excludeComponents": ["toolbox", "dataZoom"]
                }
            }
        },
        "axisPointer": {
            "link": {
                "xAxisIndex": "all"
            }
        },
        "dataZoom": [{
            "type": "inside",
            "xAxisIndex": [0],
            "startValue": 0,
            "end": 100
        }, {
            "show": True,
            "xAxisIndex": [0],
            "type": "slider",
            "bottom": 10,
            "start": 0,
            "end": 100
        }],
        "legend": {
            "type": "scroll",
            "top": 100,
            "left": "center",
            "right": "10%",
            "data": legend_data
        },
        "xAxis": {
            "type": "category",
            "boundaryGap": chart_series_type == "bar",
            "data": x_labels
        },
        "yAxis": {
            "type": "value"
        },
        "series":
        series,
        "animation":
        False
    }
    return option


def main() -> None:
    """主流程：抓取、过滤、聚合、生成并写出 JSON。"""
    try:
        _validate_required_config()
        all_contribs = fetch_all_contribs(API_URL, USER)
        filtered_contribs = filter_namespace(all_contribs, EXCLUDED_NAMESPACES)

        print(f"统计总编辑数（过滤后）: {len(filtered_contribs)}")

        (full_months, namespace_month_counts,
         namespace_totals) = group_by_month_and_namespace(filtered_contribs)
        option = build_option(
            display_name=DISPLAY_NAME,
            full_months=full_months,
            namespace_month_counts=namespace_month_counts,
            namespace_totals=namespace_totals,
            excluded_namespaces=EXCLUDED_NAMESPACES,
            namespace_mode=NAMESPACE_MODE,
            top_namespace_limit=TOP_NAMESPACE_LIMIT,
            chart_series_type=CHART_SERIES_TYPE,
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
