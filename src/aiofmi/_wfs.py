"""Parsing of FMI WFS responses."""

import math
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from .exceptions import FmiNoDataError, FmiRequestError, FmiResponseError
from .models import ForecastPoint, Location, PointForecast

# Model field -> FMI parameter. The request is built from the same table.
FORECAST_PARAMETERS = {
    "temperature": "Temperature",
    "feels_like": "FeelsLike",
    "dew_point": "DewPoint",
    "humidity": "Humidity",
    "pressure": "Pressure",
    "wind_speed": "WindSpeedMS",
    "wind_direction": "WindDirection",
    # WindGust is always NaN in the edited forecast.
    "wind_gust": "HourlyMaximumGust",
    "cloud_cover": "TotalCloudCover",
    "precipitation": "Precipitation1h",
    "precipitation_probability": "PoP",
    "thunder_probability": "ProbabilityThunderstorm",
    "smart_symbol": "SmartSymbol",
}

_NO_DATA_PREFIX = "No data available for"


def _parse_xml(body: bytes) -> ET.Element:
    try:
        return ET.fromstring(body)  # noqa: S314 - the only input is FMI's own service
    except (ET.ParseError, LookupError, ValueError) as err:
        msg = "FMI returned a response that is not valid XML"
        raise FmiResponseError(msg) from err


def _text(parent: ET.Element, path: str) -> str | None:
    text = parent.findtext(path)
    return text.strip() if text and text.strip() else None


def parse_exception_report(body: bytes) -> FmiRequestError:
    """Turn the body of an HTTP 400 response into an exception."""
    exception = _parse_xml(body).find("{*}Exception")
    if exception is None:
        msg = "FMI rejected the request without giving a reason"
        raise FmiResponseError(msg)
    # The service appends an echo of the request URI, which carries coordinates.
    texts = [
        text
        for element in exception.findall("{*}ExceptionText")
        if (text := (element.text or "").strip()) and not text.startswith("URI:")
    ]
    message = " ".join(texts) or "FMI rejected the request"
    code = exception.get("exceptionCode")
    if message.startswith(_NO_DATA_PREFIX):
        # The service's own text names the place or its coordinates.
        return FmiNoDataError(
            "FMI has no forecast for the requested location", code=code
        )
    return FmiRequestError(message, code=code)


def _time(parent: ET.Element, path: str) -> datetime | None:
    text = _text(parent, path)
    if text is None:
        return None
    try:
        value = datetime.fromisoformat(text)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    except ValueError, OverflowError:
        return None


def _rows(parent: ET.Element, path: str) -> list[list[str]]:
    return [
        line.split()
        for line in (parent.findtext(path) or "").splitlines()
        if line.strip()
    ]


def _value(text: str) -> float | None:
    value = float(text)
    return value if math.isfinite(value) else None


def _location(observation: ET.Element) -> Location:
    position = (_text(observation, ".//{*}Point/{*}pos") or "").split()
    try:
        latitude, longitude = (float(value) for value in position)
    except ValueError as err:
        msg = "FMI returned a forecast without a usable position"
        raise FmiResponseError(msg) from err
    location = observation.find(".//{*}Location")
    if location is None:
        location = ET.Element("Location")
    return Location(
        name=_text(location, "{*}name"),
        region=_text(location, "{*}region"),
        country=_text(location, "{*}country"),
        timezone=_text(location, "{*}timezone"),
        latitude=latitude,
        longitude=longitude,
    )


def parse_forecast(body: bytes) -> PointForecast:
    """Parse a multipointcoverage point forecast."""
    observation = _parse_xml(body).find("{*}member/{*}GridSeriesObservation")
    if observation is None:
        msg = "FMI returned a response without a forecast"
        raise FmiResponseError(msg)

    # The service echoes the spelling used in the request, so match without case.
    columns = {
        field.get("name", "").lower(): index
        for index, field in enumerate(observation.findall(".//{*}field"))
    }
    positions = _rows(observation, ".//{*}positions")
    values = _rows(observation, ".//{*}doubleOrNilReasonTupleList")
    if not columns or not positions or len(positions) != len(values):
        msg = "FMI returned a forecast with inconsistent contents"
        raise FmiResponseError(msg)

    indexes = {
        attribute: columns.get(parameter.lower())
        for attribute, parameter in FORECAST_PARAMETERS.items()
    }
    points: list[ForecastPoint] = []
    try:
        for position, row in zip(positions, values, strict=True):
            if len(row) != len(columns):
                msg = "FMI returned a forecast row of unexpected length"
                raise FmiResponseError(msg)
            data = {
                attribute: None if index is None else _value(row[index])
                for attribute, index in indexes.items()
            }
            # Past the forecast horizon the service pads with rows of NaN.
            if all(value is None for value in data.values()):
                continue
            symbol = data.pop("smart_symbol")
            points.append(
                ForecastPoint(
                    time=datetime.fromtimestamp(int(position[-1]), UTC),
                    smart_symbol=None if symbol is None else int(symbol),
                    **data,
                )
            )
    except (ValueError, IndexError, OverflowError) as err:
        msg = "FMI returned a forecast with values that could not be read"
        raise FmiResponseError(msg) from err
    if not points:
        msg = "FMI has no forecast values for the requested time range"
        raise FmiNoDataError(msg)

    return PointForecast(
        location=_location(observation),
        issued=_time(
            observation, "{*}parameter/{*}NamedValue/{*}value//{*}timePosition"
        ),
        points=tuple(points),
    )
