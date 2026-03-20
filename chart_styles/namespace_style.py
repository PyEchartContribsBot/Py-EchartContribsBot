from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


def _group_by_month_and_namespace(
    contribs: list[dict[str, Any]],
) -> tuple[list[tuple[int, int]], dict[int, list[int]], dict[int, int]]:
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

    namespace_month_counts: dict[int, list[int]] = {
        ns_id: [
            monthly_namespace_counter.get((year, month, ns_id), 0)
            for year, month in full_months
        ]
        for ns_id in namespace_totals
    }

    return full_months, namespace_month_counts, dict(namespace_totals)


def _build_namespace_name(ns_id: int) -> str:
    return "（主）" if ns_id == 0 else f"{{{{ns:{ns_id}}}}}"


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


def _build_series_style() -> dict[str, Any]:
    return {
        "showSymbol": False,
        "lineStyle": {
            "width": 1.8,
        },
        "areaStyle": {
            "opacity": 0.16,
        },
        "barMaxWidth": 28,
    }


def build_option(
    display_name: str,
    contribs: list[dict[str, Any]],
    generated_time: str,
    chart_series_type: str,
    excluded_namespaces: set[int],
    namespace_mode: str,
    top_namespace_limit: int,
) -> dict[str, Any]:
    full_months, namespace_month_counts, namespace_totals = _group_by_month_and_namespace(
        contribs)

    x_labels = [f"{year}年{month}月" for year, month in full_months]
    selected_namespace_ids, merged_namespace_ids = _select_series_namespaces(
        namespace_totals=namespace_totals,
        namespace_mode=namespace_mode,
        top_namespace_limit=top_namespace_limit,
    )

    legend_data: list[str] = []
    series: list[dict[str, Any]] = []
    for ns_id in selected_namespace_ids:
        ns_name = _build_namespace_name(ns_id)
        legend_data.append(ns_name)
        series.append({
            "name":
            ns_name,
            "type":
            chart_series_type,
            "stack":
            "Total",
            "emphasis": {
                "focus": "series"
            },
            "data":
            namespace_month_counts.get(ns_id, [0] * len(x_labels)),
            **_build_series_style(),
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
            "name":
            other_name,
            "type":
            chart_series_type,
            "stack":
            "Total",
            "emphasis": {
                "focus": "series"
            },
            "data":
            other_data,
            **_build_series_style(),
        })

    subtext = ("按月按命名空间统计\n"
               f"{_build_excluded_namespaces_text(excluded_namespaces)}\n"
               f"（截至 {generated_time}）")

    return {
        "__WARNING__":
        "!!! DON'T MODIFY THIS PAGE MANUALLY, YOUR CHANGES WILL BE OVERWRITTEN !!!",
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
                    "type": ["line", "bar"],
                    "option": {
                        "line": {
                            "xAxis": {
                                "boundaryGap": False
                            },
                            "series": [{
                                "showSymbol": False,
                                "areaStyle": {
                                    "opacity": 0.16,
                                }
                            }]
                        },
                        "bar": {
                            "xAxis": {
                                "boundaryGap": True
                            },
                            "series": [{
                                "barMaxWidth": 28,
                            }]
                        }
                    }
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
