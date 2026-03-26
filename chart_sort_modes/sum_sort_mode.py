from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from chart_sort_modes import DEFAULT_ACCOUNT_REG_MARKER_OUT_OF_RANGE
from chart_sort_modes.utils import (
    build_axis_tooltip_config,
    build_category_x_axis,
    build_common_datazoom,
    build_excluded_namespaces_text,
    build_magic_type_toolbox,
    build_registration_scatter_series,
)


def _group_by_month(
    contribs: list[dict[str, Any]],
) -> tuple[list[tuple[int, int]], list[str], list[int]]:
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
        return [], [], []

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
    return full_months, x_labels, y_values


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
    multi_series_render_mode: str,
    excluded_namespaces: set[int],
    namespace_mode: str,
    top_namespace_limit: int,
    namespace_map: dict[int, str] | None = None,
    is_auto_inferred_namespaces: bool = False,
    account_registrations: dict[str, str] | None = None,
    account_reg_marker_out_of_range: str = DEFAULT_ACCOUNT_REG_MARKER_OUT_OF_RANGE,
) -> dict[str, Any]:
    del namespace_mode, top_namespace_limit, multi_series_render_mode

    full_months, x_labels, y_values = _group_by_month(contribs)
    excluded_text = build_excluded_namespaces_text(
        excluded_namespaces, namespace_map, is_auto_inferred_namespaces
    )
    subtext_prefix = f"按月总编辑数（{excluded_text}）"

    series: list[dict[str, Any]] = [{
        "name": "月编辑数",
        "type": chart_series_type,
        "data": y_values,
        **_build_series_style(),
    }]
    legend_data: list[str] = ["月编辑数"]

    registration_series = build_registration_scatter_series(
        x_labels=x_labels,
        full_months=full_months,
        account_registrations=account_registrations,
        out_of_range_strategy=account_reg_marker_out_of_range,
    )
    if registration_series:
        legend_data.append("注册时间")
        series.append(registration_series)

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
        "tooltip": build_axis_tooltip_config(),
        "toolbox": build_magic_type_toolbox(
            bar_max_width=36,
            include_line_area_style=False,
        ),
        "dataZoom": build_common_datazoom(),
        "legend": {
            "type": "scroll",
            "top": 80,
            "left": "center",
            "right": "10%",
            "data": legend_data,
        },
        "xAxis": build_category_x_axis(
            x_labels=x_labels,
            chart_series_type=chart_series_type,
        ),
        "yAxis": {
            "type": "value"
        },
        "series": series,
        "animation":
        False
    }
