# AGENTS.md

`aiofmi` is an async Python client for the Finnish Meteorological Institute's
(FMI) open data. It exists to be the dependency of a new Home Assistant **core**
weather integration for FMI. The repository was created on 2026-11-15 and is
empty apart from this file; the first job is to build the library.

Keep this file up to date as decisions are made and the code takes shape.

## The plan

1. **This repo:** the client library. Forecast by coordinates first. Publish to
   PyPI as `aiofmi` (the name was free on 2026-11-15).
2. **In a fork of `home-assistant/core`:** a weather entity per location with a
   config flow and tests, submitted at Bronze. Foreca (added in HA 2026.11) is
   the model: one weather entity per location, home location by default, more
   locations added later, 30-minute polling.
3. **Follow-up PRs** raise the integration's quality-scale tier. The target is
   Platinum.

Step 2 is not done in this repo. `~/devel/hacore` is an old checkout of the
user's core fork (last synced June 2024, with local changes); it needs a fresh
sync before use. Core ships its own agent skills under `.claude/skills/`
(`ha-integration-knowledge`, `ha-quality-scale-verify`, `ha-review`), which
load when working inside a core checkout.

## What Platinum requires of this library

These three rules are the reason the library exists; none may be compromised.

- **`async-dependency`:** real asyncio I/O. No sync HTTP wrapped in an executor.
- **`inject-websession`:** every entry point takes the caller's
  `aiohttp.ClientSession`. The library never creates or closes a session.
- **`strict-typing`:** fully typed, passes mypy strict, and ships `py.typed`
  (PEP 561). The rule has no exceptions, and hassfest checks the marker.

Other things core expects of a dependency: a release on PyPI built from a
public repository with tagged releases, an OSI-approved licence, and few
runtime dependencies. Home Assistant requires Python 3.14, so there is no
need to support anything older.

Rule texts: <https://contributors.home-assistant.io/core/quality-scale/rules/>.
Read the library-related ones before designing the public API.

## Scope

Keep it to what the integration needs. Other FMI integrations grew wide
(station catalogues, lightning, sea level, radiation); that is the main thing
to avoid here.

- **First:** point forecast by latitude and longitude, as a typed time series.
- **Likely next:** resolving a place name to coordinates, the latest
  observations from a station, weather warnings (CAP feed).
- **Not planned:** grids, radar, soundings, WMS, a generic stored-query
  browser.

The Home Assistant weather entity needs a condition, the current values, and
hourly and daily forecasts. FMI serves a point time series only, so daily
values have to be aggregated by local day somewhere. Whether that lives here
or in the integration is undecided.

## FMI API notes

Collected by reading other clients' code, not verified against the live
service in this repo. Confirm each against real responses before relying on
it, and save the responses as test fixtures.

- Endpoint: `https://opendata.fmi.fi/wfs`, WFS 2.0.0 `getFeature` with a
  `storedquery_id`. No account or API key.
- Point forecast query used by the existing clients:
  `fmi::forecast::edited::weather::scandinavia::point::multipointcoverage`,
  with `latlon=<lat>,<lon>` (or `place=<name>`), `starttime`, `endtime`,
  `timestep` (minutes) and `parameters` (comma-separated).
- Parameters seen in use: `Temperature`, `DewPoint`, `Pressure`, `Humidity`,
  `WindDirection`, `WindSpeedMS`, `WindGust`, `HourlyMaximumGust`,
  `WeatherSymbol3`, `TotalCloudCover`, `Precipitation1h`, `PoP`,
  `ProbabilityThunderstorm`.
- A multipointcoverage response carries the field names in `swe:field`
  elements, one "lat lon unix-time" triple per row in `gmlcov:positions`, and
  the values in `gml:doubleOrNilReasonTupleList`, with `NaN` for missing.
- Observations: `fmi::observations::weather::multipointcoverage` with
  `fmisid=<station>`. The `::simple` form returns one element per value.
- Errors: HTTP 400 with an `ExceptionReport` whose `ExceptionText` elements
  give the reason, for example a too-long time range or no data for the
  place. A 200 response can also be empty (`numberMatched="0"`).
- FMI limits request rates and the time range per query. Look up the current
  limits in FMI's open data documentation and design polling around them.

## Prior art

Read for behaviour and API knowledge. **Do not copy code from the GPL ones**
unless this project also ends up GPL.

| Project | Licence | Notes |
|---|---|---|
| `fmi-weather-client` (PyPI; Codeberg `saaste`) | GPL-3.0 | Sync `requests`, `async_*` names are executor wrappers, no `py.typed`. What the existing custom integration uses. |
| `pnuu/fmiopendata` | GPL-3.0-or-later | General WFS/WMS toolkit with numpy. Good reference for station and multipoint parsing. Its author is a colleague of the user. |
| `kogeler/fmi-hass-custom` | MIT | Custom integration, domain `fmi`. Wraps `fmi-weather-client` and adds gust and probability parameters; its `fmi_client.py` shows which fields an integration ends up needing. |
| `jesmak/fmi` | MIT | Custom integration, domain `fmi_open_data`. Its `session.py` has careful WFS error handling and coverage parsing. |
| `pyforeca` (PyPI) | not checked | The library behind core's Foreca integration. Not yet read; worth studying as an accepted example of the same shape. |

A custom integration overrides a core one with the same domain, and `fmi` is
taken by kogeler's. The core integration's domain is an open decision.

## Preferences and constraints

- Aim for quality over speed; the user sees no reason to settle for less than
  Platinum.
- Code, comments and docs are in English.
- Core reviewers are told to flag comments that over-explain or read like AI
  commentary. Write comments only for non-obvious constraints, here as well.

## Open decisions (the user's to make)

- **XML parsing.** Standard library `xml.etree.ElementTree` or a dependency.
- **Where daily aggregation lives** (see Scope).
- **The core integration's domain** (see Prior art).

## Working on the code

Nothing is set up yet. When the tooling is chosen, record here the commands to
create the environment, run the tests, lint and type-check, and how releases
are made.

