from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

from chart_sort_modes.utils import build_excluded_namespaces_text


_HEATMAP_COLORS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
_CALENDAR_LEFT = 40
_CALENDAR_RIGHT = 40
_CALENDAR_TOP_START = 90
_CALENDAR_ROW_HEIGHT = 180


def _parse_utc_date(timestamp: str) -> date | None:
    try:
        return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").date()
    except ValueError:
        return None


def _count_daily_contribs(contribs: list[dict[str, Any]]) -> Counter[date]:
    daily_counter: Counter[date] = Counter()
    for item in contribs:
        timestamp = item.get("timestamp")
        if not isinstance(timestamp, str):
            continue

        contrib_date = _parse_utc_date(timestamp)
        if contrib_date is None:
            continue

        daily_counter[contrib_date] += 1

    return daily_counter


def _iter_dates(start_date: date, end_date: date) -> list[date]:
    days: list[date] = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def _build_date_series(
    daily_counter: Counter[date],
    start_date: date,
    end_date: date,
) -> tuple[list[list[Any]], int]:
    data: list[list[Any]] = []
    max_count = 0

    for current_date in _iter_dates(start_date, end_date):
        count = daily_counter.get(current_date, 0)
        max_count = max(max_count, count)
        data.append([current_date.isoformat(), count])

    return data, max_count


def _build_yearly_calendar_options(
    daily_counter: Counter[date],
    years: list[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    calendars: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []
    max_count = 0

    for index, year in enumerate(years):
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        data, year_max = _build_date_series(daily_counter, start_date, end_date)
        max_count = max(max_count, year_max)

        calendars.append({
            "range": str(year),
            "top": _CALENDAR_TOP_START + index * _CALENDAR_ROW_HEIGHT,
            "left": _CALENDAR_LEFT,
            "right": _CALENDAR_RIGHT,
            "cellSize": ["auto", 18],
            "splitLine": {
                "show": True,
                "lineStyle": {
                    "color": "#ffffff",
                    "width": 2,
                },
            },
            "itemStyle": {
                "borderWidth": 1,
                "borderColor": "#ffffff",
            },
            "yearLabel": {
                "show": True,
                "margin": 28,
            },
            "monthLabel": {
                "nameMap": [
                    "1月",
                    "2月",
                    "3月",
                    "4月",
                    "5月",
                    "6月",
                    "7月",
                    "8月",
                    "9月",
                    "10月",
                    "11月",
                    "12月",
                ]
            },
            "dayLabel": {
                "firstDay": 1,
                "nameMap": ["日", "一", "二", "三", "四", "五", "六"],
            },
        })
        series.append({
            "name": f"{year}年贡献",
            "type": "heatmap",
            "coordinateSystem": "calendar",
            "calendarIndex": index,
            "data": data,
        })

    return calendars, series, max_count


def _build_last365_calendar_options(
    daily_counter: Counter[date],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=364)
    data, max_count = _build_date_series(daily_counter, start_date, end_date)

    calendars = [{
        "range": [start_date.isoformat(), end_date.isoformat()],
        "top": _CALENDAR_TOP_START,
        "left": _CALENDAR_LEFT,
        "right": _CALENDAR_RIGHT,
        "cellSize": ["auto", 18],
        "splitLine": {
            "show": True,
            "lineStyle": {
                "color": "#ffffff",
                "width": 2,
            },
        },
        "itemStyle": {
            "borderWidth": 1,
            "borderColor": "#ffffff",
        },
        "yearLabel": {
            "show": True,
            "margin": 28,
        },
        "monthLabel": {
            "nameMap": [
                "1月",
                "2月",
                "3月",
                "4月",
                "5月",
                "6月",
                "7月",
                "8月",
                "9月",
                "10月",
                "11月",
                "12月",
            ]
        },
        "dayLabel": {
            "firstDay": 1,
            "nameMap": ["日", "一", "二", "三", "四", "五", "六"],
        },
    }]
    series = [{
        "name": "最近365天贡献",
        "type": "heatmap",
        "coordinateSystem": "calendar",
        "calendarIndex": 0,
        "data": data,
    }]
    return calendars, series, max_count


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
    calendar_range_mode: str = "yearly",
) -> dict[str, Any]:
    del chart_series_type, multi_series_render_mode, namespace_mode, top_namespace_limit

    daily_counter = _count_daily_contribs(contribs)
    if calendar_range_mode == "last365":
        calendars, series, max_count = _build_last365_calendar_options(daily_counter)
        subtext_prefix = "最近365天按日期总编辑数"
    else:
        years = sorted({contrib_date.year for contrib_date in daily_counter})
        if not years:
            current_year = datetime.now(timezone.utc).date().year
            years = [current_year]
        calendars, series, max_count = _build_yearly_calendar_options(daily_counter, years)
        if len(years) == 1:
            subtext_prefix = f"{years[0]}年按日期总编辑数"
        else:
            subtext_prefix = f"{years[0]}-{years[-1]}年按日期总编辑数"

    excluded_text = build_excluded_namespaces_text(
        excluded_namespaces, namespace_map, is_auto_inferred_namespaces
    )

    option: dict[str, Any] = {
        "__WARNING__":
        "!!! DON'T MODIFY THIS PAGE MANUALLY, YOUR CHANGES WILL BE OVERWRITTEN !!!",
        "title": {
            "text": f"{display_name}的编辑历史",
            "subtext": f"{subtext_prefix}\n{excluded_text}\n（截至 {generated_time}）",
            "left": "center",
            "itemGap": 10,
            "subtextStyle": {
                "lineHeight": 18,
            },
        },
        "tooltip": {
            "position": "top",
        },
        "visualMap": {
            "min": 0,
            "max": max(1, max_count),
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": 18,
            "inRange": {
                "color": _HEATMAP_COLORS,
            },
            "seriesIndex": list(range(len(series))),
        },
        "calendar": calendars,
        "series": series,
        "animation": False,
    }

    return option
