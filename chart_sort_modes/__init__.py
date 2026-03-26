from __future__ import annotations

from typing import Any, Literal

ChartSortMode = Literal["namespace", "sum", "account"]
AccountRegMarkerOutOfRange = Literal["clamp_to_first", "hide"]
MultiSeriesRenderMode = Literal["stacked", "dataset"]

_SUPPORTED_CHART_SORT_MODES: set[str] = {"namespace", "sum", "account"}
DEFAULT_MULTI_SERIES_RENDER_MODE: MultiSeriesRenderMode = "stacked"
_SUPPORTED_MULTI_SERIES_RENDER_MODES: set[str] = {"stacked", "dataset"}

DEFAULT_ACCOUNT_REG_MARKER_OUT_OF_RANGE: AccountRegMarkerOutOfRange = "clamp_to_first"
SUPPORTED_ACCOUNT_REG_MARKER_OUT_OF_RANGE: set[str] = {"clamp_to_first", "hide"}

REGISTRATION_MARKER_SYMBOL = (
    "path://M 0 0 L 100 0 L 100 60 L 50 100 L 0 60 Z "
    "M 45 15 L 45 25 L 35 25 L 35 35 L 45 35 L 45 45 "
    "L 55 45 L 55 35 L 65 35 L 65 25 L 55 25 L 55 15 Z"
)
REGISTRATION_MARKER_COLOR = "rgba(0,160,0,0.95)"


def parse_chart_sort_mode(raw_value: str) -> ChartSortMode:
    value = raw_value.strip().lower()
    if not value:
        return "namespace"
    if value not in _SUPPORTED_CHART_SORT_MODES:
        raise RuntimeError(
            "环境变量 CHART_SORT_MODE 仅支持 namespace、sum 或 account，"
            "例如 CHART_SORT_MODE=namespace")
    return value  # type: ignore[return-value]


def parse_multi_series_render_mode(raw_value: str) -> MultiSeriesRenderMode:
    value = raw_value.strip().lower()
    if not value:
        return DEFAULT_MULTI_SERIES_RENDER_MODE
    if value not in _SUPPORTED_MULTI_SERIES_RENDER_MODES:
        raise RuntimeError(
            "环境变量 MULTI_SERIES_RENDER_MODE 仅支持 stacked 或 dataset，"
            "例如 MULTI_SERIES_RENDER_MODE=stacked")
    return value  # type: ignore[return-value]


def parse_account_reg_marker_out_of_range(raw_value: str) -> AccountRegMarkerOutOfRange:
    value = raw_value.strip().lower()
    if not value or value == DEFAULT_ACCOUNT_REG_MARKER_OUT_OF_RANGE:
        return DEFAULT_ACCOUNT_REG_MARKER_OUT_OF_RANGE
    if value in SUPPORTED_ACCOUNT_REG_MARKER_OUT_OF_RANGE:
        return value  # type: ignore[return-value]
    raise RuntimeError(
        "环境变量 ACCOUNT_REG_MARKER_OUT_OF_RANGE 仅支持 clamp_to_first 或 hide（默认 clamp_to_first）")


def build_option_for_sort_mode(
    chart_sort_mode: ChartSortMode,
    display_name: str,
    contribs: list[dict[str, Any]],
    generated_time: str,
    chart_series_type: str,
    multi_series_render_mode: MultiSeriesRenderMode,
    excluded_namespaces: set[int],
    namespace_mode: str,
    top_namespace_limit: int,
    namespace_map: dict[int, str] | None = None,
    is_auto_inferred_namespaces: bool = False,
    accounts_contribs: dict[str, list[dict[str, Any]]] | None = None,
    account_order: list[str] | None = None,
    account_registrations: dict[str, str] | None = None,
    account_reg_marker_out_of_range: AccountRegMarkerOutOfRange = (
        DEFAULT_ACCOUNT_REG_MARKER_OUT_OF_RANGE
    ),
) -> dict[str, Any]:
    if chart_sort_mode == "account":
        from chart_sort_modes.account_sort_mode import build_option as build_account_option

        if accounts_contribs is None or account_order is None:
            raise RuntimeError("account 模式需要提供 accounts_contribs 和 account_order 参数")
        return build_account_option(
            display_name=display_name,
            accounts_contribs=accounts_contribs,
            generated_time=generated_time,
            chart_series_type=chart_series_type,
            multi_series_render_mode=multi_series_render_mode,
            account_order=account_order,
            excluded_namespaces=excluded_namespaces,
            is_auto_inferred_namespaces=is_auto_inferred_namespaces,
            namespace_map=namespace_map,
            account_registrations=account_registrations or {},
            account_reg_marker_out_of_range=account_reg_marker_out_of_range,
        )

    if chart_sort_mode == "sum":
        from chart_sort_modes.sum_sort_mode import build_option as build_sum_option

        return build_sum_option(
            display_name=display_name,
            contribs=contribs,
            generated_time=generated_time,
            chart_series_type=chart_series_type,
            multi_series_render_mode=multi_series_render_mode,
            excluded_namespaces=excluded_namespaces,
            namespace_mode=namespace_mode,
            top_namespace_limit=top_namespace_limit,
            namespace_map=namespace_map,
            is_auto_inferred_namespaces=is_auto_inferred_namespaces,
            account_registrations=account_registrations or {},
            account_reg_marker_out_of_range=account_reg_marker_out_of_range,
        )

    from chart_sort_modes.namespace_sort_mode import build_option as build_namespace_option

    return build_namespace_option(
        display_name=display_name,
        contribs=contribs,
        generated_time=generated_time,
        chart_series_type=chart_series_type,
        multi_series_render_mode=multi_series_render_mode,
        excluded_namespaces=excluded_namespaces,
        namespace_mode=namespace_mode,
        top_namespace_limit=top_namespace_limit,
        namespace_map=namespace_map,
        is_auto_inferred_namespaces=is_auto_inferred_namespaces,
        account_registrations=account_registrations or {},
        account_reg_marker_out_of_range=account_reg_marker_out_of_range,
    )
