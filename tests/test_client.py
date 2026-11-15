"""Tests for the client, against responses recorded from the live service."""

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

from aiofmi import (
    FmiClient,
    FmiConnectionError,
    FmiNoDataError,
    FmiRateLimitError,
    FmiRequestError,
    FmiResponseError,
    FmiTimeoutError,
    Location,
)

from .conftest import FakeFmi, load_fixture

HELSINKI = (60.1699, 24.9384)
START = datetime(2026, 11, 15, 21, tzinfo=UTC)


async def test_forecast(client: FmiClient, fmi: FakeFmi) -> None:
    """A recorded ten-day forecast is parsed into a typed series."""
    fmi.respond("forecast_helsinki.xml")

    forecast = await client.forecast(*HELSINKI, start=START)

    assert forecast.location == Location(
        name="Central Helsinki",
        region="Helsinki",
        country="Finland",
        timezone="Europe/Helsinki",
        latitude=60.1699,
        longitude=24.9384,
    )
    assert forecast.issued == datetime(2026, 11, 15, 19, 51, tzinfo=UTC)

    # The recording has 241 rows, of which the last 9 are past the horizon.
    assert len(forecast.points) == 232
    assert forecast.points[-1].time == datetime(2026, 11, 25, 12, tzinfo=UTC)
    times = [point.time for point in forecast.points]
    assert times == sorted(times)

    first = forecast.points[0]
    assert first.time == START
    assert first.temperature == 7.19
    assert first.feels_like == 1.489966
    assert first.dew_point == 4.43
    assert first.humidity == 82.5
    assert first.pressure == 1005.3
    assert first.wind_speed == 10.2
    assert first.wind_direction == 213.0
    assert first.wind_gust == 18.8
    assert first.cloud_cover == 95.1
    assert first.precipitation == 0.0
    assert first.precipitation_probability == 0.0
    assert first.thunder_probability == 0.0
    assert first.smart_symbol == 107
    assert first.symbol == 7
    assert first.is_daytime is False

    noon = next(point for point in forecast.points if point.time.hour == 10)
    assert noon.is_daytime is True
    assert noon.symbol == noon.smart_symbol


async def test_forecast_request(client: FmiClient, fmi: FakeFmi) -> None:
    """The request names the query, the point, the time range and the parameters."""
    fmi.respond("forecast_helsinki.xml")

    await client.forecast(
        *HELSINKI,
        start=datetime(2026, 11, 15, 23, tzinfo=timezone(timedelta(hours=2))),
        end=datetime(2026, 11, 17, 21, tzinfo=UTC),
    )

    assert fmi.requests == [
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "getFeature",
            "storedquery_id": (
                "fmi::forecast::edited::weather::scandinavia::point::multipointcoverage"
            ),
            "latlon": "60.1699,24.9384",
            "starttime": "2026-11-15T21:00:00Z",
            "endtime": "2026-11-17T21:00:00Z",
            "timestep": "60",
            "parameters": (
                "Temperature,FeelsLike,DewPoint,Humidity,Pressure,WindSpeedMS,"
                "WindDirection,HourlyMaximumGust,TotalCloudCover,Precipitation1h,"
                "PoP,ProbabilityThunderstorm,SmartSymbol"
            ),
        }
    ]


async def test_forecast_default_times(client: FmiClient, fmi: FakeFmi) -> None:
    """Without times the series starts at the current hour and spans ten days."""
    fmi.respond("forecast_helsinki.xml")

    before = datetime.now(UTC)
    await client.forecast(*HELSINKI)

    start = datetime.fromisoformat(fmi.requests[0]["starttime"])
    end = datetime.fromisoformat(fmi.requests[0]["endtime"])
    assert (start.minute, start.second) == (0, 0)
    assert timedelta(0) <= before - start < timedelta(hours=1, seconds=5)
    assert end - start == timedelta(days=10)


async def test_forecast_missing_fields(client: FmiClient, fmi: FakeFmi) -> None:
    """Fields are matched without case, and absent ones are None."""
    fmi.respond("forecast_lowercase_fields.xml")

    forecast = await client.forecast(*HELSINKI, start=START)

    point = forecast.points[0]
    assert point.temperature is not None
    assert point.wind_speed is not None
    assert point.humidity is None
    assert point.smart_symbol is None
    assert point.symbol is None
    assert point.is_daytime is None


async def test_forecast_other_timezone(client: FmiClient, fmi: FakeFmi) -> None:
    """The time zone is that of the location."""
    fmi.respond("forecast_copenhagen.xml")

    forecast = await client.forecast(55.6761, 12.5683, start=START)

    assert forecast.location.timezone == "Europe/Copenhagen"
    assert forecast.location.country == "Denmark"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"latitude": 90.1, "longitude": 0}, "Invalid coordinates"),
        ({"latitude": 60, "longitude": -180.1}, "Invalid coordinates"),
        ({"latitude": float("nan"), "longitude": 25}, "Invalid coordinates"),
        ({"start": datetime(2026, 11, 15, 21)}, "timezone-aware"),  # noqa: DTZ001
        ({"start": START, "end": START}, "after the start"),
        ({"end": datetime(2099, 1, 1)}, "timezone-aware"),  # noqa: DTZ001
        ({"start": datetime(2026, 11, 15), "end": START}, "timezone-aware"),  # noqa: DTZ001
    ],
)
async def test_forecast_invalid_arguments(
    client: FmiClient, fmi: FakeFmi, kwargs: dict[str, object], message: str
) -> None:
    """Arguments the service cannot accept are refused before any request."""
    arguments: dict[str, object] = {"latitude": 60.17, "longitude": 24.94} | kwargs

    with pytest.raises(ValueError, match=message):
        await client.forecast(**arguments)  # type: ignore[arg-type]

    assert not fmi.requests


async def test_no_data(client: FmiClient, fmi: FakeFmi) -> None:
    """A point outside the forecast area raises FmiNoDataError."""
    fmi.respond("error_no_data.xml", status=400)

    with pytest.raises(FmiNoDataError) as excinfo:
        await client.forecast(0, 0)

    assert str(excinfo.value) == "FMI has no forecast for the requested location"
    assert excinfo.value.code == "OperationParsingFailed"


@pytest.mark.parametrize(
    ("fixture", "message"),
    [
        ("error_unknown_parameter.xml", "Unknown parameter 'NoSuchParam'"),
        ("error_malformed_latlon.xml", "Fmi::stod failed to convert 'abc' to double"),
    ],
)
async def test_request_error(
    client: FmiClient, fmi: FakeFmi, fixture: str, message: str
) -> None:
    """A rejected request raises FmiRequestError with the reason, not the URI."""
    fmi.respond(fixture, status=400)

    with pytest.raises(FmiRequestError) as excinfo:
        await client.forecast(*HELSINKI)

    assert not isinstance(excinfo.value, FmiNoDataError)
    assert str(excinfo.value) == message
    assert excinfo.value.code == "OperationParsingFailed"


async def test_no_values_in_range(client: FmiClient, fmi: FakeFmi) -> None:
    """A series with nothing but missing values raises FmiNoDataError."""
    body = load_fixture("forecast_copenhagen.xml").decode()
    start = body.index("<gml:doubleOrNilReasonTupleList>") + len(
        "<gml:doubleOrNilReasonTupleList>"
    )
    end = body.index("</gml:doubleOrNilReasonTupleList>")
    rows = len(body[start:end].strip().splitlines())
    fmi.body = (body[:start] + "\n" + "NaN NaN \n" * rows + body[end:]).encode()

    with pytest.raises(FmiNoDataError, match="no forecast values"):
        await client.forecast(55.6761, 12.5683)


def _edited(old: str, new: str, fixture: str = "forecast_copenhagen.xml") -> bytes:
    body = load_fixture(fixture).decode()
    assert old in body
    return body.replace(old, new).encode()


@pytest.mark.parametrize(
    ("body", "status", "message"),
    [
        (load_fixture("empty.xml"), 200, "without a forecast"),
        (b"<html>not closed", 200, "not valid XML"),
        (b"<html>not closed", 400, "not valid XML"),
        (b'<?xml version="1.0" encoding="no-such"?><a/>', 200, "not valid XML"),
        (b'<?xml version="1.0" encoding="shift_jis"?><a/>', 200, "not valid XML"),
        (b"<ExceptionReport/>", 400, "without giving a reason"),
        (load_fixture("error_forbidden.html"), 403, "HTTP status 403"),
        (b"", 503, "HTTP status 503"),
        (_edited("6.36 3.0 ", "6.36 3.0 1.0 "), 200, "unexpected length"),
        (
            _edited("<gmlcov:positions>\n", "<gmlcov:positions>\n 1 2 3\n"),
            200,
            "inconsistent",
        ),
        (_edited("6.36 3.0 ", "mild 3.0 "), 200, "could not be read"),
        (_edited("<gml:pos>", "<gml:pos>north "), 200, "usable position"),
    ],
)
async def test_response_error(
    client: FmiClient, fmi: FakeFmi, body: bytes, status: int, message: str
) -> None:
    """An unusable answer raises FmiResponseError."""
    fmi.body = body
    fmi.status = status

    with pytest.raises(FmiResponseError, match=message) as excinfo:
        await client.forecast(*HELSINKI)

    assert excinfo.value.status == (None if status in (200, 400) else status)


async def test_tolerant_parsing(client: FmiClient, fmi: FakeFmi) -> None:
    """Metadata that is missing or malformed does not fail the forecast."""
    body = load_fixture("forecast_copenhagen.xml").decode()
    start = body.index("<target:Location ")
    end = body.index("</target:Location>") + len("</target:Location>")
    body = body[:start] + body[end:]
    analysis = body.index("<gml:timePosition>", body.index("analysis-time"))
    body = body[:analysis] + "<gml:timePosition>soon" + body[analysis + 18 :]
    fmi.body = body.encode()

    forecast = await client.forecast(55.6761, 12.5683)

    assert forecast.issued is None
    assert forecast.location.name is None
    assert forecast.location.timezone is None
    assert forecast.location.latitude == 55.68


async def test_missing_analysis_time(client: FmiClient, fmi: FakeFmi) -> None:
    """A forecast without an analysis time has no issue time."""
    fmi.body = _edited("<om:parameter>", "<om:other>").replace(
        b"</om:parameter>", b"</om:other>"
    )

    assert (await client.forecast(55.6761, 12.5683)).issued is None


@pytest.mark.parametrize(
    ("headers", "retry_after"),
    [
        ({"Retry-After": "120"}, 120.0),
        ({"Retry-After": "later"}, None),
        ({"Retry-After": "nan"}, None),
        ({"Retry-After": "-5"}, None),
        ({}, None),
    ],
)
async def test_rate_limit(
    client: FmiClient, fmi: FakeFmi, headers: dict[str, str], retry_after: float | None
) -> None:
    """HTTP 429 raises FmiRateLimitError with the wait the service asked for."""
    fmi.status = 429
    fmi.headers = headers

    with pytest.raises(FmiRateLimitError) as excinfo:
        await client.forecast(*HELSINKI)

    assert excinfo.value.retry_after == retry_after


async def test_timeout(session: ClientSession) -> None:
    """A slow answer raises FmiTimeoutError."""

    async def slow(_: web.Request) -> web.Response:
        await asyncio.sleep(10)
        return web.Response()

    app = web.Application()
    app.router.add_get("/wfs", slow)
    async with TestServer(app) as server:
        client = FmiClient(
            session, url=str(server.make_url("/wfs")), request_timeout=0.05
        )
        with pytest.raises(FmiTimeoutError):
            await client.forecast(*HELSINKI)


async def test_connection_error(session: ClientSession, unused_tcp_port: int) -> None:
    """An unreachable service raises FmiConnectionError."""
    client = FmiClient(session, url=f"http://127.0.0.1:{unused_tcp_port}/wfs")

    with pytest.raises(FmiConnectionError) as excinfo:
        await client.forecast(*HELSINKI)

    assert not isinstance(excinfo.value, FmiTimeoutError)


async def test_session_raising_for_status(fmi: FakeFmi, client: FmiClient) -> None:
    """A session set to raise for HTTP errors does not change the error raised."""
    fmi.respond("error_no_data.xml", status=400)
    async with ClientSession(raise_for_status=True) as session:
        strict = FmiClient(session, url=client._url)  # noqa: SLF001
        with pytest.raises(FmiNoDataError):
            await strict.forecast(0, 0)


async def test_garbled_response(session: ClientSession) -> None:
    """A broken HTTP answer raises FmiConnectionError without the request URL."""

    async def garbage(_: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"garbage\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(garbage, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        client = FmiClient(session, url=f"http://127.0.0.1:{port}/wfs")
        with pytest.raises(FmiConnectionError) as excinfo:
            await client.forecast(*HELSINKI)

    assert "latlon" not in str(excinfo.value)


async def test_session_left_open(
    client: FmiClient, fmi: FakeFmi, session: ClientSession
) -> None:
    """The caller's session is never closed."""
    fmi.respond("forecast_helsinki.xml")

    await client.forecast(*HELSINKI)

    assert not session.closed


async def test_analysis_time_without_offset(client: FmiClient, fmi: FakeFmi) -> None:
    """An analysis time without an offset is read as UTC."""
    fmi.body = _edited("2026-11-15T19:51:00Z", "2026-11-15T19:51:00")

    forecast = await client.forecast(55.6761, 12.5683)

    assert forecast.issued == datetime(2026, 11, 15, 19, 51, tzinfo=UTC)
