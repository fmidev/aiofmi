# aiofmi

Async Python client for the [Finnish Meteorological Institute's open data](https://en.ilmatieteenlaitos.fi/open-data).

It fetches FMI's official point forecast, the one shown on fmi.fi and in the
FMI weather app, as a typed time series. The forecast covers Finland and
nearby areas and reaches about ten days ahead.

- Built on `aiohttp`, its only dependency. You pass in the `ClientSession`.
- Fully typed, ships `py.typed`.
- Requires Python 3.14.

## Install

```sh
pip install aiofmi
```

## Use

```python
import asyncio

import aiohttp

from aiofmi import FmiClient, daily_forecasts


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        client = FmiClient(session)
        forecast = await client.forecast(60.1699, 24.9384)

    print(forecast.location.name, forecast.location.timezone)
    for point in forecast.points[:3]:
        print(point.time, point.temperature, point.wind_speed, point.smart_symbol)
    for day in daily_forecasts(forecast):
        print(day.date, day.temperature_min, day.temperature_max, day.precipitation)


asyncio.run(main())
```

### `FmiClient(session, *, request_timeout=30, url=...)`

The client never creates or closes a session.

### `await client.forecast(latitude, longitude, *, start=None, end=None, timestep=timedelta(hours=1))`

Returns a `Forecast`:

| Attribute | Contents |
| --- | --- |
| `location` | `name`, `region`, `country`, `timezone` (IANA name), `latitude`, `longitude`. The name is that of the nearest known place and is not a stable identifier. |
| `issued` | Analysis time of the forecast. |
| `points` | `ForecastPoint`s in chronological order. |

By default the series starts at the beginning of the current hour and runs
hourly to the end of the forecast. `start` and `end` must be timezone-aware.

A `ForecastPoint` has a timezone-aware UTC `time` and these values, each
`None` when FMI does not provide it:

| Attribute | Unit |
| --- | --- |
| `temperature`, `feels_like`, `dew_point` | °C |
| `humidity`, `cloud_cover` | % |
| `pressure` | hPa |
| `wind_speed`, `wind_gust` | m/s |
| `wind_direction` | degrees |
| `precipitation` | mm during the preceding hour |
| `precipitation_probability`, `thunder_probability` | % |
| `smart_symbol` | FMI [SmartSymbol](https://www.ilmatieteenlaitos.fi/latauspalvelun-pikaohje) code, with 100 added at night |

`point.symbol` is the code without the night offset and `point.is_daytime`
tells which half it came from.

### `daily_forecasts(forecast, tz=None)`

Groups the points by calendar day and returns `DailyForecast`s with
`temperature_max`, `temperature_min`, `precipitation` (sum),
`precipitation_probability` (highest), `wind_speed` (highest),
`wind_direction` (at the highest wind speed), `wind_gust` (highest),
`smart_symbol` (of the point closest to 14:00) and the day's `points`.

Days are those of `tz`, by default the time zone of the forecast location.
The first and last day cover only the hours the series contains.

### Errors

All derive from `FmiError`.

| Exception | Meaning |
| --- | --- |
| `FmiConnectionError` | The service could not be reached. |
| `FmiTimeoutError` | No answer within `request_timeout`. Subclass of `FmiConnectionError`. |
| `FmiRateLimitError` | HTTP 429. `retry_after` holds the wait in seconds, if given. |
| `FmiResponseError` | An unexpected HTTP status (`status`) or an unreadable response. |
| `FmiRequestError` | FMI rejected the request. `code` holds the OWS exception code. |
| `FmiNoDataError` | No forecast for the location, typically because it is outside the forecast area. Subclass of `FmiRequestError`. |

Invalid arguments raise `ValueError` before any request is made.

## Terms of use

FMI's open data is licensed under
[CC BY 4.0](https://en.ilmatieteenlaitos.fi/open-data-licence); credit the
Finnish Meteorological Institute when you publish it. The service allows
20 000 requests a day and 600 per five minutes per user. The forecast is
updated a few times a day, so there is little to gain from polling more often
than every half hour.

## Development

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

Tests run against responses recorded from the live service, in
`tests/fixtures`.
