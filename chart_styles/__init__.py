from __future__ import annotations

from typing import Any, Literal

from chart_styles.sum_style import build_option as build_sum_option
from chart_styles.namespace_style import build_option as build_namespace_option

ChartStyle = Literal["namespace", "sum"]

_SUPPORTED_CHART_STYLES: set[str] = {"namespace", "sum"}


def parse_chart_style(raw_value: str) -> ChartStyle:
    value = raw_value.strip().lower()
    if not value:
        return "namespace"
    if value not in _SUPPORTED_CHART_STYLES:
        raise RuntimeError(
            "环境变量 CHART_STYLE 仅支持 namespace 或 sum，"
            "例如 CHART_STYLE=namespace")
    return value  # type: ignore[return-value]


def build_option_for_style(
    chart_style: ChartStyle,
    display_name: str,
    contribs: list[dict[str, Any]],
    generated_time: str,
    chart_series_type: str,
    excluded_namespaces: set[int],
    namespace_mode: str,
    top_namespace_limit: int,
) -> dict[str, Any]:
    if chart_style == "sum":
        return build_sum_option(
            display_name=display_name,
            contribs=contribs,
            generated_time=generated_time,
            chart_series_type=chart_series_type,
            excluded_namespaces=excluded_namespaces,
            namespace_mode=namespace_mode,
            top_namespace_limit=top_namespace_limit,
        )

    return build_namespace_option(
        display_name=display_name,
        contribs=contribs,
        generated_time=generated_time,
        chart_series_type=chart_series_type,
        excluded_namespaces=excluded_namespaces,
        namespace_mode=namespace_mode,
        top_namespace_limit=top_namespace_limit,
    )
