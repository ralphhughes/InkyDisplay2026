#!/usr/bin/env python3
"""Fetch the Met Office Llandudno North Shore wave-height forecast as JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, time
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


PAGE_URL = "https://weather.metoffice.gov.uk/forecast/gcmr2gtdu"
WAVE_SECTION_ID = "detailed-forecast/BeachWaveHeight"
LOCAL_TIMEZONE = ZoneInfo("Europe/London")
WAVE_VALUE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*m\b", re.IGNORECASE)
TIME_FORMATS = ("%I%p", "%I:%M%p")


class BeachForecastParser(HTMLParser):
    """Read the wave-height values from the forecast page's embedded table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.in_wave_section = False
        self.wave_section_depth = 0
        self.tables: list[dict[str, Any]] = []
        self.current_table: dict[str, Any] | None = None
        self.current_row: list[dict[str, Any]] | None = None
        self.current_cell: dict[str, Any] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "div":
            if (
                not self.in_wave_section
                and attributes.get("id") == WAVE_SECTION_ID
            ):
                self.in_wave_section = True
                self.wave_section_depth = 1
            elif self.in_wave_section:
                self.wave_section_depth += 1

        if not self.in_wave_section:
            return
        if tag == "table" and self.current_table is None:
            table_date = attributes.get("data-date")
            if table_date:
                self.current_table = {"date": table_date, "rows": []}
        elif tag == "tr" and self.current_table is not None:
            self.current_row = []
        elif (
            tag in ("th", "td")
            and self.current_row is not None
            and self.current_cell is None
        ):
            self.current_cell = {"text": [], "value": attributes.get("data-value")}
        elif self.current_cell is not None and attributes.get("data-value"):
            self.current_cell["value"] = attributes["data-value"]

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if self.in_wave_section:
            if tag in ("th", "td") and self.current_cell is not None:
                self.current_cell["text"] = " ".join(
                    "".join(self.current_cell["text"]).split()
                )
                if self.current_row is not None:
                    self.current_row.append(self.current_cell)
                self.current_cell = None
            elif tag == "tr" and self.current_row is not None:
                if self.current_table is not None:
                    self.current_table["rows"].append(self.current_row)
                self.current_row = None
            elif tag == "table" and self.current_table is not None:
                self.tables.append(self.current_table)
                self.current_table = None
            elif tag == "div":
                self.wave_section_depth -= 1
                if self.wave_section_depth == 0:
                    self.in_wave_section = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.current_cell is not None:
            self.current_cell["text"].append(data)


def _parse_hour(value: str) -> time:
    normalized = value.strip().replace(" ", "").upper()
    for time_format in TIME_FORMATS:
        try:
            return datetime.strptime(normalized, time_format).time()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized forecast time label: {value!r}")


def _parse_wave_height(cell: dict[str, Any]) -> float | None:
    raw_value = cell.get("value")
    if raw_value is not None:
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            pass

    match = WAVE_VALUE_PATTERN.search(str(cell.get("text", "")))
    return float(match.group(1)) if match else None


def extract_wave_forecast(
    parser: BeachForecastParser,
) -> list[dict[str, Any]]:
    forecast: list[dict[str, Any]] = []
    for table in parser.tables:
        try:
            forecast_date = date.fromisoformat(table["date"])
        except (KeyError, TypeError, ValueError):
            continue

        time_row = next(
            (
                row
                for row in table["rows"]
                if row and str(row[0].get("text", "")).casefold() == "time"
            ),
            None,
        )
        wave_row = next(
            (
                row
                for row in table["rows"]
                if row
                and str(row[0].get("text", "")).strip().casefold()
                in ("wave height", "height")
            ),
            None,
        )
        if time_row is None or wave_row is None:
            continue

        for time_cell, height_cell in zip(time_row[1:], wave_row[1:]):
            try:
                event_time = datetime.combine(
                    forecast_date,
                    _parse_hour(str(time_cell.get("text", ""))),
                    tzinfo=LOCAL_TIMEZONE,
                )
            except ValueError:
                continue
            forecast.append(
                {
                    "time": event_time.isoformat(),
                    "wave_height_m": _parse_wave_height(height_cell),
                }
            )

    forecast.sort(key=lambda item: item["time"])
    return forecast


def fetch_wave_forecast() -> dict[str, Any]:
    request = Request(
        PAGE_URL,
        headers={
            "Accept": "text/html",
            "User-Agent": "InkyDisplay2026 beach wave forecast inspector",
        },
    )
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")

    parser = BeachForecastParser()
    parser.feed(html)
    forecast = extract_wave_forecast(parser)
    if not forecast:
        raise ValueError(
            "No wave-height forecast was found in the page. "
            "The Met Office page markup may have changed."
        )

    return {
        "source": PAGE_URL,
        "location": "".join(parser.title_parts).strip(),
        "parameter": "wave_height",
        "units": "m",
        "fetched_at": datetime.now(LOCAL_TIMEZONE).isoformat(),
        "forecast": forecast,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="pretty-print the JSON (the default is compact JSON)",
    )
    args = parser.parse_args()

    try:
        data = fetch_wave_forecast()
        print(
            json.dumps(
                data,
                indent=2 if args.pretty else None,
                ensure_ascii=False,
                separators=None if args.pretty else (",", ":"),
            )
        )
    except HTTPError as exc:
        print(f"Met Office page returned HTTP {exc.code}.", file=sys.stderr)
        return 1
    except (OSError, URLError, UnicodeError, ValueError) as exc:
        print(f"Wave forecast fetch failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
