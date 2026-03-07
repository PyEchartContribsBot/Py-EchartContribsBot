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


# ===== 可配置参数 =====
API_URL: str = os.environ.get("API_URL", "").strip()  # 必填：目标站点 API
USER: str = os.environ.get("WIKI_USER", "").strip()  # 必填：统计目标用户名
DISPLAY_NAME: str = os.environ.get(
    "DISPLAY_NAME", "").strip() or USER  # 用于图表显示的别名，默认等效 WIKI_USER
EXCLUDED_NAMESPACES: set[int] = _parse_excluded_namespaces(
    os.environ.get("EXCLUDED_NAMESPACES", ""))
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


def group_by_month(
        contribs: list[dict[str, Any]]) -> tuple[list[str], list[int]]:
    """按真实年月排序并统计每月编辑次数。"""
    monthly_counter: Counter[tuple[int, int]] = Counter()

    for item in contribs:
        timestamp = item.get("timestamp")
        if not isinstance(timestamp, str):
            continue

        try:
            dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue

        monthly_counter[(dt.year, dt.month)] += 1

    if not monthly_counter:
        return [], []

    sorted_months = sorted(monthly_counter.keys())

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

    x_labels = [f"{year}年{month}月" for year, month in full_months]
    y_values = [monthly_counter.get(key, 0) for key in full_months]
    return x_labels, y_values


def build_option(display_name: str, x_labels: list[str],
                 y_values: list[int]) -> dict[str, Any]:
    """构建完整 Apache ECharts option JSON。"""
    now_utc = datetime.now(timezone.utc)
    generated_time = (f"{now_utc.year}年{now_utc.month}月{now_utc.day}日"
                      f"{now_utc.hour:02d}:{now_utc.minute:02d}〔UTC〕")

    option: dict[str, Any] = {
        "title": {
            "text": f"{display_name}的编辑历史",
            "subtext": f"按月统计次数\n排除“用户”和讨论命名空间\n（截至 {generated_time}）",
            "left": "center",
            "itemGap": 10,
            "subtextStyle": {
                "lineHeight": 18
            }
        },
        "grid": {
            "top": 110,
            "left": "10%",
            "right": "10%",
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
            "start": 0,
            "end": 100
        }],
        "legend": {
            "data": ["编辑次数"]
        },
        "xAxis": {
            "data": x_labels
        },
        "yAxis": {},
        "series": [{
            "name": "月编辑数",
            "type": "line",
            "showSymbol": False,
            "label": {
                "formatter": "{c}",
                "distance": 0,
                "backgroundColor": "transparent",
                "padding": 1
            },
            "data": y_values,
            "markPoint": {
                "data": [{
                    "type": "max",
                    "name": "最大值"
                }]
            },
            "markLine": {
                "data": [{
                    "type": "average",
                    "name": "平均值"
                }]
            }
        }],
        "animation":
        True
    }
    return option


def main() -> None:
    """主流程：抓取、过滤、聚合、生成并写出 JSON。"""
    try:
        _validate_required_config()
        all_contribs = fetch_all_contribs(API_URL, USER)
        filtered_contribs = filter_namespace(all_contribs, EXCLUDED_NAMESPACES)

        print(f"统计总编辑数（过滤后）: {len(filtered_contribs)}")

        x_labels, y_values = group_by_month(filtered_contribs)
        option = build_option(DISPLAY_NAME, x_labels, y_values)

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
