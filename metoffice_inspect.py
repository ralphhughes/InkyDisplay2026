#!/usr/bin/env python3
"""Inspect the Met Office hourly forecast for Llandudno.

Run from the VS Code terminal with:
    python metoffice_inspect.py --format table
    python metoffice_inspect.py --format json

The API key is read from METOFFICE_API_KEY in the .env file beside this script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Any


API_URL = "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/hourly"
LATITUDE = 53.323
LONGITUDE = -3.827
ENV_FILE = Path(__file__).resolve().with_name(".env")


def load_api_key(env_file: Path = ENV_FILE) -> str:
    """Read METOFFICE_API_KEY without executing the dotenv file as shell code."""
    if not env_file.is_file():
        raise FileNotFoundError(f"Environment file not found: {env_file}")

    for line_number, line in enumerate(
        env_file.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("export "):
            entry = entry[len("export ") :].lstrip()
        if "=" not in entry:
            continue

        name, value = entry.split("=", 1)
        if name.strip() != "METOFFICE_API_KEY":
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if value:
            return value
        raise ValueError(
            f"METOFFICE_API_KEY is empty in {env_file} on line {line_number}"
        )

    raise ValueError(f"METOFFICE_API_KEY was not found in {env_file}")


def fetch_response(api_key: str) -> dict[str, Any]:
    query = urlencode(
        {
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "includeLocationName": "true",
            "excludeParameterMetadata": "true",
        }
    )
    request = Request(
        f"{API_URL}?{query}",
        headers={"apikey": api_key, "accept": "application/json"},
    )
    with urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Met Office returned JSON that is not an object.")
    return data


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value is None:
        return "null"
    return str(value)


def print_table(data: dict[str, Any]) -> None:
    features = data.get("features")
    if not isinstance(features, list) or not features or not isinstance(features[0], dict):
        raise ValueError("Met Office response has no GeoJSON forecast feature.")

    properties = features[0].get("properties")
    if not isinstance(properties, dict):
        raise ValueError("Met Office forecast feature has no properties object.")

    print("Met Office response")
    for name, value in properties.items():
        if name != "timeSeries":
            print(f"{name}: {_format_value(value)}")

    time_series = properties.get("timeSeries")
    if not isinstance(time_series, list):
        raise ValueError("Met Office response has no timeSeries list.")

    print(f"\nHourly forecast records: {len(time_series)}")
    for index, record in enumerate(time_series, start=1):
        if not isinstance(record, dict):
            print(f"\nRecord {index}: {_format_value(record)}")
            continue
        print(f"\n--- Record {index}: {record.get('time', 'date unavailable')} ---")
        for name, value in record.items():
            if name != "time":
                print(f"{name}: {_format_value(value)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="output format (default: table)",
    )
    args = parser.parse_args()

    try:
        api_key = load_api_key()
        data = fetch_response(api_key)
        if args.format == "json":
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_table(data)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        print(f"Met Office API returned HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError, URLError, UnicodeError, ValueError) as exc:
        print(f"Met Office inspection failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
