# AGENTS.md

`aiofmi` is an async Python client for the Finnish Meteorological Institute's
(FMI) open data. It exists to be the dependency of a new Home Assistant **core**
weather integration for FMI.

Keep this file up to date as decisions are made and the code changes.

## The plan

1. **This repo:** the client library. Forecast by coordinates is implemented
   (tagged `v0.1.0`, not yet on PyPI). Publish to PyPI as `aiofmi` (the name
   was free on 2026-11-15).
2. **In a fork of `home-assistant/core`:** a weather entity per location with a
   config flow and tests, submitted at Bronze with the weather platform only.
   Models to follow: **SMHI** (Platinum, library `pysmhi`) and **Met.no**
   (set up by default for the home location, library `PyMetno`). Both have
   one config entry per location, a `SingleCoordinatorWeatherEntity`,
   `PARALLEL_UPDATES = 0` and hourly and daily forecasts; SMHI also offers
   twice-daily. Met.no's home entry follows the home location (unique id
   `home`); other entries use `"<lat>-<lon>"`. Foreca (HA 2026.11) is only
   Bronze.
3. **Follow-up PRs** raise the integration's quality-scale tier. The target is
   Platinum.

Step 2 is not done in this repo. `~/devel/hacore` is an old checkout of the
user's core fork (last synced June 2024, with local changes); it needs a fresh
sync before use. Core ships its own agent skills under `.claude/skills/`
(`ha-integration-knowledge`, `ha-quality-scale-verify`, `ha-review`), which
load when working inside a core checkout.

## Working on the code

```sh
uv sync                                              # environment
uv run pytest                                        # tests; coverage must stay at 100 %
uv run ruff check . && uv run ruff format --check .  # lint and format
uv run mypy                                          # strict, over src and tests
```

- `src/aiofmi/client.py`: `FmiClient`, the HTTP request and status handling.
- `src/aiofmi/_wfs.py`: XML parsing. All knowledge of the WFS format lives here.
- `src/aiofmi/daily.py`: `daily_forecasts`, aggregation by local day.
- `src/aiofmi/models.py`, `exceptions.py`: the public types.
- `tests/fixtures/`: responses recorded from the live service on 2026-11-15.
  Record new ones with `curl` instead of writing them by hand; a hand-written
  fixture cost the Foreca PR a review round.
- Tests use a local `aiohttp` test server through the client's `url` argument;
  there is no HTTP mocking library.

**Releasing:** the version comes from the git tag through `hatch-vcs` (user's
decision); `pyproject.toml` has no version and `uv version --bump` does not
apply. Create an annotated tag (`git tag -a vX.Y.Z`), push it, and publish a
GitHub release from that tag with release notes. Untagged builds get versions
like `0.1.1.dev3+g<hash>`. `.github/workflows/release.yml` checks out the full
history so the tag is visible, then builds and uploads to PyPI with Trusted
Publishing. One-time setup, not yet done: register a pending trusted publisher
on PyPI for `aiofmi` (repository `fmidev/aiofmi`, workflow `release.yml`,
environment `pypi`) and create the `pypi` environment in the repository.

## What Home Assistant requires of this library

These three Platinum rules are the reason the library exists; none may be
compromised.

- **`async-dependency`:** real asyncio I/O. No sync HTTP wrapped in an executor.
- **`inject-websession`:** every entry point takes the caller's
  `aiohttp.ClientSession`. The library never creates or closes a session.
- **`strict-typing`:** fully typed, passes mypy strict, and ships
  `aiofmi/py.typed`. The rule has no exceptions, and hassfest checks the wheel.

Checked by core's tooling on every requirement (verified in core `dev`,
2026-11-15):

- `requires-python` may have a lower bound only. No upper bounds on `aiohttp`
  or `yarl` below a major version.
- Forbidden runtime dependencies include `async-timeout`, `backoff`,
  `setuptools` and any `types-*`.
- The wheel must not contain top-level `tests`, `docs` or `py.typed`.
- Licence metadata as an SPDX `License-Expression`; GPL is refused in review.
- The "Check requirements" bot wants a repository URL in `project.urls`, a
  PyPI release with a Trusted Publisher attestation, a tag `vX.Y.Z` matching
  each release, and no blocking calls in `async def`.

From core's "Build a Python library" page: represent the data the way the API
does and do not interpret it; raise the library's own exceptions so the
integration can tell failure kinds apart; do not retry, cache or log errors.
That is why the SmartSymbol code is passed through unmapped: the mapping to
Home Assistant conditions belongs in the integration.

Rule texts: <https://contributors.home-assistant.io/core/quality-scale/>
(a rule is at `/core/quality-scale/<rule>/`).

## Scope

Keep it to what the integration needs. Other FMI integrations grew wide
(station catalogues, lightning, sea level, radiation); that is the main thing
to avoid here.

- **Done:** point forecast by latitude and longitude, daily aggregation.
- **Likely next:** the latest observations from a station, weather warnings
  (CAP 1.2 Atom feeds at `https://alerts.fmi.fi/cap/feed/atom_{fi-FI,sv-FI,en-GB}.xml`).
- **Not planned:** grids, radar, soundings, WMS, a generic stored-query
  browser, place-name search (`place=` silently picks one of several matches,
  so it is not usable as a geocoder).

## Decisions

- **Transport: WFS, not the JSON `timeseries` endpoint.** Both serve the same
  data (compared over 232 rows). FMI announced `timeseries` in 2021 as
  "originally planned for internal use" and unsupported by the help desk, and
  it fails silently: an unknown parameter gives a column of nulls, and a point
  outside the area is served from another model. If WFS ever becomes a
  problem, only `_wfs.py` and the request in `client.py` change.
- **XML parsing: the standard library** (user's decision). Match elements by
  local name with `{*}` so a schema version bump does not break parsing.
  `Element.iter()` does not accept `{*}`; use `findall()`.
- **Daily aggregation lives here** (user's decision), as a pure function with
  an explicit, optional time zone.
- **SmartSymbol, not WeatherSymbol3.** FMI calls it the preferred code, and it
  encodes day and night (code + 100 at night), so no sun calculation is needed.
- **The core integration's domain is `fmi`** (user's decision, 2026-11-16),
  although kogeler's custom integration (active, in the default Marketplace
  list) uses it too. Where that is installed it replaces the core one and
  hides it from "Add integration". Its entries (config entry version 2) cannot
  be taken over, so the integration docs should tell its users to delete
  their entries before uninstalling it, then add the core integration.
  Precedent: core `nordpool` shares its domain with the custom
  `custom-components/nordpool`, which caused only brief confusion.
  Telling kogeler before the core PR would help their users.
- **One config entry per location** (user's decision, 2026-11-16), as SMHI
  and Met.no do. FMI has no account key that would call for a parent entry
  with location subentries, as Foreca has.
- **`aiohttp` is the only runtime dependency.** Models are plain frozen
  dataclasses.

## FMI API notes

Verified against the live service on 2026-11-15 unless marked otherwise.

- Endpoint: `https://opendata.fmi.fi/wfs`, WFS 2.0.0 `getFeature` with a
  `storedquery_id`. No account or API key.
- Query: `fmi::forecast::edited::weather::scandinavia::point::multipointcoverage`
  with `latlon=<lat>,<lon>`, `starttime`, `endtime`, `timestep` (minutes) and
  `parameters`. This is the forecaster-edited product shown on fmi.fi.
- Send times as `...Z`. `jesmak/fmi` notes that a `+00:00` suffix reaches the
  server as a space (not verified here).
- The horizon is about 9.7 days. Later rows are returned filled with `NaN`,
  so they are dropped. There is no time-range limit on the forecast query
  (observations are limited to 168 hours).
- Native resolution appears to be hourly to about +36 h, then 3-hourly, then
  6-hourly; the server interpolates onto the requested step.
- The client always asks for `timestep=60`. `Precipitation1h` stays a one-hour
  value at any step, so sums over a coarser or finer series are wrong. Steps
  align to 00:00 UTC, so `timestep=1440` cannot give local days.
- `WindGust` is always `NaN` in this product; `HourlyMaximumGust` has values.
- Field names in `swe:field` echo the spelling of the request.
- The response gives the IANA time zone of the point (`target:timezone`) and a
  reverse-geocoded place name that is not a stable identifier.
- Errors are HTTP 400 with an OWS `ExceptionReport`. Every forecast error has
  the code `OperationParsingFailed`, so only the text tells them apart:
  outside the area is `No data available for '<place>'!`. The last
  `ExceptionText` echoes the request URI with the coordinates and is dropped.
- A 200 with `numberMatched="0"` occurs when the location is missing or
  `endtime` precedes `starttime`. Other statuses can have an HTML body.
- Forecast responses carry `Cache-Control: max-age=21600` and a gateway cache
  sits in front; use the analysis time, not the response timestamp, as the age
  of the data.
- Limits: 20 000 requests a day and 600 per 5 minutes per user. What a refusal
  looks like is **not verified**; the client treats HTTP 429 as the rate limit.
- `Precipitation1h` is the amount accumulated during the hour ending at the
  timestamp: "kello 12 kohdalla oleva arvo tarkoittaa ... kello 11–12"
  (<https://www.ilmatieteenlaitos.fi/saapalvelut-verkossa>).
- FMI's own services describe a day by its weather at 15:00: "Päivän kohdalla
  oleva sääkuvake kertoo säästä klo 15, ei siis koko vuorokaudesta" (same
  page). `daily_forecasts` follows this, and leaves out a last day that ends
  before 15:00 (user's decision, 2026-11-16).
- Licence of the data: CC BY 4.0. FMI's logo may not be used with open data
  products, which matters for the Home Assistant brands submission.
- Changelog to watch: <https://en.ilmatieteenlaitos.fi/open-data-changelog>.

## Prior art

Read for behaviour and API knowledge. **Do not copy code from the GPL ones.**

| Project | Licence | Notes |
| --- | --- | --- |
| `fmi-weather-client` (PyPI; Codeberg `saaste`) | GPL-3.0 | Sync `requests`, no `py.typed`. What the existing custom integration uses. |
| `pnuu/fmiopendata` | GPL-3.0-or-later | General WFS/WMS toolkit with numpy. Its author is a colleague of the user. |
| `kogeler/fmi-hass-custom` | MIT | Custom integration, domain `fmi`. Its WeatherSymbol3 condition table has errors; do not reuse it. |
| `jesmak/fmi` | MIT | Custom integration, domain `fmi_open_data`. Uses SmartSymbol and one request per refresh, as this library does. |
| `pysmhi` | MIT | The library behind core's Platinum SMHI integration. Like FMI, SMHI serves a point series, and `pysmhi` builds the daily and twice-daily forecasts itself, by UTC day with the symbol from the first point at or after 12:00 UTC. A precedent for aggregating in the library. |
| `pyforeca` | MIT | The library behind core's Bronze Foreca integration. It returns timestamps as strings and has no parse exception, which this library improves on. |

Four core PRs for an FMI integration were opened in 2020–21 and none merged.
They failed on scope and integration design, not on the library: keep the
first PR to the weather platform, config flow only, one coordinator.

A custom integration overrides a core one with the same domain; see the
domain decision.

## Preferences and constraints

- Aim for quality over speed; the user sees no reason to settle for less than
  Platinum.
- Code, comments and docs are in English.
- Core reviewers are told to flag comments that over-explain or read like AI
  commentary. Write comments only for non-obvious constraints, here as well.
- Commit locally on `main` in logical steps; push only when the user asks.
