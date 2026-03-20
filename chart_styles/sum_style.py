from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


def _group_by_month(
        contribs: list[dict[str, Any]]) -> tuple[list[str], list[int]]:
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


def _build_series_style() -> dict[str, Any]:
    return {
        "showSymbol": False,
        "barMaxWidth": 36,
        "lineStyle": {
            "width": 2,
        },
        "markPoint": {
            "data": [{
                "type": "max",
                "name": "最大值",
            }]
        },
        "markLine": {
            "data": [{
                "type": "average",
                "name": "平均值",
            }]
        },
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
    del namespace_mode, top_namespace_limit

    x_labels, y_values = _group_by_month(contribs)
    if excluded_namespaces:
        subtext_prefix = "按月总编辑数（已排除{{ns:2}}、各{{ns:1}}命名空间）"
    else:
        subtext_prefix = "按月总编辑数"

    return {
        "__WARNING__":
        "!!! DON'T MODIFY THIS PAGE MANUALLY, YOUR CHANGES WILL BE OVERWRITTEN !!!",
        "title": {
            "text": f"{display_name}的编辑历史",
            "subtext": f"{subtext_prefix}\n（截至 {generated_time}）",
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
                    "type": ["line", "bar"],
                    "option": {
                        "line": {
                            "xAxis": {
                                "boundaryGap": False
                            },
                            "series": [{
                                "showSymbol": False,
                            }]
                        },
                        "bar": {
                            "xAxis": {
                                "boundaryGap": True
                            },
                            "series": [{
                                "barMaxWidth": 36,
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
        "xAxis": {
            "type": "category",
            "boundaryGap": chart_series_type == "bar",
            "data": x_labels
        },
        "yAxis": {
            "type": "value"
        },
        "series": [{
            "name": "月编辑数",
            "type": chart_series_type,
            "data": y_values,
            **_build_series_style(),
        }],
        "animation":
        False
    }
