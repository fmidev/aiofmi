"""Tests for the aggregation of a forecast into days."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from aiofmi import ForecastPoint, Location, PointForecast, daily_forecasts
from aiofmi._wfs import parse_forecast

from .conftest import load_fixture

HELSINKI = ZoneInfo("Europe/Helsinki")


def _point(time: datetime, **values: float | None) -> ForecastPoint:
    fields: dict[str, float | None] = dict.fromkeys(
        (
            "temperature",
            "feels_like",
            "dew_point",
            "humidity",
            "pressure",
            "wind_speed",
            "wind_direction",
            "wind_gust",
            "cloud_cover",
            "precipitation",
            "precipitation_probability",
            "thunder_probability",
        )
    )
    symbol = values.pop("smart_symbol", None)
    return ForecastPoint(
        time=time.astimezone(UTC),
        smart_symbol=None if symbol is None else int(symbol),
        **(fields | values),
    )


def _forecast(
    *points: ForecastPoint, timezone: str | None = "Europe/Helsinki"
) -> PointForecast:
    location = Location(
        name=None,
        region=None,
        country=None,
        timezone=timezone,
        latitude=60.17,
        longitude=24.94,
    )
    return PointForecast(location=location, issued=None, points=points)


def test_recorded_forecast() -> None:
    """A recorded forecast splits into the local days of its location."""
    forecast = parse_forecast(load_fixture("forecast_helsinki.xml"))

    days = daily_forecasts(forecast)

    # The series runs from 2026-11-15 23:00 to 2026-11-25 14:00 in Helsinki;
    # the last day ends before 15:00 and is left out.
    assert [day.date for day in days] == [date(2026, 11, day) for day in range(15, 25)]
    assert [len(day.points) for day in days] == [1, *[24] * 9]
    assert sum(len(day.points) for day in days) == len(forecast.points) - 15

    day = days[1]
    assert day.points[0].time == datetime(2026, 11, 15, 22, tzinfo=UTC)
    temperatures = [
        point.temperature for point in day.points if point.temperature is not None
    ]
    assert day.temperature_max == max(temperatures)
    assert day.temperature_min == min(temperatures)
    assert day.smart_symbol == day.points[15].smart_symbol
    # Rain is counted from the hours ending 01:00 on the day to 00:00 on the next.
    rain = [point.precipitation or 0 for point in (*day.points[1:], days[2].points[0])]
    assert day.precipitation == pytest.approx(sum(rain))


def test_aggregates() -> None:
    """Each aggregate uses the values of its own day."""
    day = datetime(2026, 7, 1, tzinfo=HELSINKI)
    forecast = _forecast(
        _point(
            day.replace(hour=3),
            temperature=11,
            wind_speed=2,
            wind_direction=90,
            wind_gust=4,
            precipitation_probability=10,
            smart_symbol=101,
        ),
        _point(
            day.replace(hour=13),
            temperature=21,
            wind_speed=7,
            wind_direction=180,
            wind_gust=9,
            precipitation=1.5,
            precipitation_probability=60,
            smart_symbol=31,
        ),
        _point(
            day.replace(hour=16),
            temperature=19,
            wind_speed=5,
            wind_direction=270,
            wind_gust=12,
            precipitation=0.5,
            precipitation_probability=40,
            smart_symbol=1,
        ),
        _point(day.replace(day=2, hour=0), temperature=14, precipitation=4),
        _point(day.replace(day=2, hour=1), temperature=13, precipitation=8),
        _point(day.replace(day=2, hour=15), smart_symbol=2),
    )

    first, second = daily_forecasts(forecast)

    assert first.date == date(2026, 7, 1)
    assert len(first.points) == 3
    assert first.temperature_max == 21
    assert first.temperature_min == 11
    assert first.precipitation == 6
    assert first.precipitation_probability == 60
    assert first.wind_speed == 7
    assert first.wind_direction == 180
    assert first.wind_gust == 12
    assert first.smart_symbol == 1

    assert second.date == date(2026, 7, 2)
    assert second.temperature_max == 14
    assert second.temperature_min == 13
    assert second.precipitation == 8
    assert second.precipitation_probability is None
    assert second.wind_speed is None
    assert second.wind_direction is None
    assert second.wind_gust is None
    assert second.smart_symbol == 2
    assert second.symbol == 2


def test_missing_values() -> None:
    """A day without a value has None, not zero."""
    forecast = _forecast(_point(datetime(2026, 7, 1, 12, tzinfo=HELSINKI)))

    (day,) = daily_forecasts(forecast)

    assert day.temperature_max is None
    assert day.temperature_min is None
    assert day.precipitation is None
    assert day.smart_symbol is None
    assert day.symbol is None


def test_explicit_timezone() -> None:
    """Days follow the given time zone instead of the location's."""
    forecast = _forecast(
        _point(datetime(2026, 7, 1, 21, tzinfo=UTC), temperature=15),
        _point(datetime(2026, 7, 2, 13, tzinfo=UTC), temperature=14),
    )

    assert [day.date for day in daily_forecasts(forecast)] == [date(2026, 7, 2)]
    # In UTC the series ends at 13:00 on the second day, which is left out.
    assert [day.date for day in daily_forecasts(forecast, UTC)] == [date(2026, 7, 1)]
    assert [
        day.date for day in daily_forecasts(forecast, ZoneInfo("Europe/Stockholm"))
    ] == [
        date(2026, 7, 1),
        date(2026, 7, 2),
    ]


def test_daylight_saving_change() -> None:
    """The day the clocks go back has 25 hours."""
    start = datetime(2026, 10, 24, 21, tzinfo=UTC)
    forecast = _forecast(
        *(_point(start + timedelta(hours=hour), temperature=hour) for hour in range(49))
    )

    days = daily_forecasts(forecast)

    assert [(day.date, len(day.points)) for day in days] == [
        (date(2026, 10, 25), 25),
        (date(2026, 10, 26), 24),
    ]


def test_symbol_at_fifteen() -> None:
    """A day's symbol is the one at 15:00, or on the first day the closest."""
    day = datetime(2026, 11, 16, tzinfo=HELSINKI)
    forecast = _forecast(
        _point(day.replace(day=15, hour=22), smart_symbol=107),
        _point(day.replace(day=15, hour=23), smart_symbol=131),
        _point(day.replace(hour=9), smart_symbol=21),
        _point(day.replace(hour=14), smart_symbol=2),
        _point(day.replace(hour=15), smart_symbol=3),
        _point(day.replace(hour=16), smart_symbol=1),
        _point(day.replace(hour=17), smart_symbol=107),
    )
    tie = _forecast(
        _point(day.replace(hour=13), smart_symbol=2),
        _point(day.replace(hour=17), smart_symbol=1),
    )

    evening, full = daily_forecasts(forecast)
    assert evening.smart_symbol == 107
    assert evening.symbol == 7
    assert full.smart_symbol == 3
    # 13:00 and 17:00 are equally close to 15:00; the earlier one is used.
    assert daily_forecasts(tie)[0].smart_symbol == 2


def test_last_day_needs_fifteen() -> None:
    """The last day is kept only when the series reaches 15:00 on it."""
    day = datetime(2026, 11, 16, tzinfo=HELSINKI)
    points = [_point(day.replace(hour=hour), temperature=hour) for hour in range(24)]
    tomorrow = day + timedelta(days=1)

    short = _forecast(*points, _point(tomorrow.replace(hour=14), temperature=1))
    long = _forecast(*points, _point(tomorrow.replace(hour=15), temperature=1))
    only = _forecast(_point(day.replace(hour=14), temperature=1))

    assert [day.date for day in daily_forecasts(short)] == [date(2026, 11, 16)]
    assert [day.date for day in daily_forecasts(long)] == [
        date(2026, 11, 16),
        date(2026, 11, 17),
    ]
    assert [day.date for day in daily_forecasts(only)] == [date(2026, 11, 16)]
    assert daily_forecasts(_forecast()) == ()


def test_unknown_timezone() -> None:
    """A time zone name the system does not know asks for an explicit one."""
    forecast = _forecast(
        _point(datetime(2026, 7, 1, tzinfo=UTC)), timezone="Mars/Olympus"
    )

    with pytest.raises(ValueError, match="time zone"):
        daily_forecasts(forecast)


def test_no_timezone() -> None:
    """Without any time zone there are no days to aggregate by."""
    forecast = _forecast(_point(datetime(2026, 7, 1, tzinfo=UTC)), timezone=None)

    with pytest.raises(ValueError, match="time zone"):
        daily_forecasts(forecast)

    assert len(daily_forecasts(forecast, UTC)) == 1
