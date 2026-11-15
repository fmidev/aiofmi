"""Aggregation of a forecast series into local calendar days."""

from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import DailyForecast, Forecast, ForecastPoint

_SYMBOL_TIME = time(14)
_ACCUMULATION_PERIOD = timedelta(hours=1)


def _values(
    points: Iterable[ForecastPoint], getter: Callable[[ForecastPoint], float | None]
) -> list[float]:
    return [value for point in points if (value := getter(point)) is not None]


def _afternoon_distance(moment: datetime) -> timedelta:
    return abs(
        moment.replace(tzinfo=None) - datetime.combine(moment.date(), _SYMBOL_TIME)
    )


def daily_forecasts(
    forecast: Forecast, tz: tzinfo | None = None
) -> tuple[DailyForecast, ...]:
    """Aggregate a forecast by calendar day.

    Days are those of ``tz``, which defaults to the time zone of the forecast
    location. The first and the last day cover only the part of the day that
    the series contains. Precipitation counts towards the day in which the
    hour it accumulated over began, so the series must be hourly.

    The default time zone is read from the system's time zone database, which
    blocks; pass ``tz`` when calling from an event loop.
    """
    if tz is None:
        if forecast.location.timezone is None:
            msg = "The forecast location has no time zone; pass one explicitly"
            raise ValueError(msg)
        try:
            tz = ZoneInfo(forecast.location.timezone)
        except (ZoneInfoNotFoundError, ValueError) as err:
            msg = (
                "The time zone of the forecast location is unknown; pass one explicitly"
            )
            raise ValueError(msg) from err

    days: dict[date, list[tuple[datetime, ForecastPoint]]] = {}
    precipitation: dict[date, list[float]] = {}
    for point in forecast.points:
        local = point.time.astimezone(tz)
        days.setdefault(local.date(), []).append((local, point))
        if point.precipitation is not None:
            accumulated_on = (point.time - _ACCUMULATION_PERIOD).astimezone(tz).date()
            precipitation.setdefault(accumulated_on, []).append(point.precipitation)

    result: list[DailyForecast] = []
    for day, entries in days.items():
        points = tuple(point for _, point in entries)
        temperatures = _values(points, lambda point: point.temperature)
        probabilities = _values(points, lambda point: point.precipitation_probability)
        gusts = _values(points, lambda point: point.wind_gust)
        windiest = max(
            (point for point in points if point.wind_speed is not None),
            key=lambda point: point.wind_speed or 0,
            default=None,
        )
        symbols = [
            (
                not point.is_daytime,
                _afternoon_distance(local),
                index,
                point.smart_symbol,
            )
            for index, (local, point) in enumerate(entries)
            if point.smart_symbol is not None
        ]
        result.append(
            DailyForecast(
                date=day,
                points=points,
                temperature_max=max(temperatures, default=None),
                temperature_min=min(temperatures, default=None),
                precipitation=sum(precipitation[day]) if day in precipitation else None,
                precipitation_probability=max(probabilities, default=None),
                wind_speed=windiest.wind_speed if windiest else None,
                wind_direction=windiest.wind_direction if windiest else None,
                wind_gust=max(gusts, default=None),
                smart_symbol=min(symbols)[-1] if symbols else None,
            )
        )
    return tuple(result)
