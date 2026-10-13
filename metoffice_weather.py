#!/usr/bin/env python3
"""Fetch the Met Office forecast for Llandudno and show it on an Inky display.

Set METOFFICE_API_KEY to an API key for the Met Office Weather DataHub's
Site-specific API before running this script.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont


API_URL = "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/hourly"
LATITUDE = 53.323
LONGITUDE = -3.827
LOCATION = "LLANDUDNO"
DEFAULT_RESOLUTION = (600, 448)
LOGGER = logging.getLogger("metoffice_weather")
INK_BLACK = (0, 0, 0)
INK_WHITE = (255, 255, 255)
INK_GREEN = (0, 255, 0)
INK_BLUE = (0, 0, 255)
INK_RED = (255, 0, 0)
INK_YELLOW = (255, 255, 0)
INK_ORANGE = (255, 140, 0)


class WeatherError(RuntimeError):
    """Raised when the Met Office response is missing usable forecast data."""


def fetch_forecast(api_key: str) -> tuple[str, list[dict[str, Any]]]:
    LOGGER.info(
        "Requesting hourly forecast for %s (%.3f, %.3f) from %s",
        LOCATION.title(),
        LATITUDE,
        LONGITUDE,
        API_URL,
    )
    response = requests.get(
        API_URL,
        params={
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "includeLocationName": "true",
            "excludeParameterMetadata": "true",
        },
        headers={"apikey": api_key, "accept": "application/json"},
        timeout=20,
    )
    LOGGER.info("Met Office API returned HTTP %d", response.status_code)
    if response.status_code in (401, 403):
        raise WeatherError(
            "Met Office rejected the API key. Check that it is valid and "
            "subscribed to the Site-specific API."
        )
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, dict):
        raise WeatherError("Met Office returned an unexpected response.")
    features = data.get("features")
    feature = features[0] if isinstance(features, list) and features else data
    properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
    time_series = properties.get("timeSeries")
    if not isinstance(time_series, list) or not time_series:
        LOGGER.error(
            "No hourly forecast found; response keys=%s, properties keys=%s",
            sorted(data.keys()),
            sorted(properties.keys()) if isinstance(properties, dict) else [],
        )
        raise WeatherError("Met Office response contained no hourly forecast.")

    location = properties.get("location", {})
    location_name = (
        location.get("name")
        if isinstance(location, dict)
        else properties.get("locationName")
    )
    LOGGER.info(
        "Received %d hourly forecast records for %s (model run %s)",
        len(time_series),
        location_name or LOCATION.title(),
        properties.get("modelRunDate", "unknown"),
    )
    LOGGER.debug("Forecast response property keys: %s", sorted(properties.keys()))
    LOGGER.debug("First forecast record fields: %s", sorted(time_series[0].keys()))
    return str(location_name or LOCATION.title()), time_series


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    font_path = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        return ImageFont.load_default()


def _parse_local_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _dashboard_times(
    forecast: list[dict[str, Any]], now: datetime
) -> list[tuple[datetime, dict[str, Any] | None]]:
    local_now = now.astimezone()
    first_hour = local_now.replace(minute=0, second=0, microsecond=0)
    if local_now.minute or local_now.second or local_now.microsecond:
        first_hour += timedelta(hours=1)
    first_hour += timedelta(hours=(-first_hour.hour) % 3)

    parsed = [
        (local_time, record)
        for record in forecast
        if (local_time := _parse_local_time(record.get("time"))) is not None
    ]
    parsed.sort(key=lambda item: item[0])

    slots: list[tuple[datetime, dict[str, Any] | None]] = []
    for index in range(8):
        target = first_hour + timedelta(hours=3 * index)
        closest = min(
            parsed,
            key=lambda item: abs((item[0] - target).total_seconds()),
            default=None,
        )
        record = None
        if closest is not None and abs((closest[0] - target).total_seconds()) <= 1800:
            record = closest[1]
        slots.append((target, record))
    return slots


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _wind_arrow(value: Any) -> str:
    try:
        degrees = (float(value) + 180) % 360
    except (TypeError, ValueError):
        return ""
    arrows = ("↑", "↗", "→", "↘", "↓", "↙", "←", "↖")
    return arrows[round(degrees / 45) % len(arrows)]


def _temperature_color(value: float) -> tuple[int, int, int]:
    if value < 10:
        return INK_BLUE
    if value < 20:
        return INK_GREEN
    if value <= 25:
        return INK_ORANGE
    return INK_RED


def _humidity_color(value: float) -> tuple[int, int, int]:
    if value > 90:
        return INK_BLUE
    if value >= 75:
        return INK_GREEN
    if value >= 60:
        return INK_ORANGE
    return INK_RED


def _wind_color(value_mph: float) -> tuple[int, int, int]:
    return _temperature_color(value_mph)


def _slot_value(record: dict[str, Any] | None, field: str) -> float | None:
    if record is None:
        return None
    try:
        return float(record[field])
    except (KeyError, TypeError, ValueError):
        return None


def _dashboard_rows(
    slots: list[tuple[datetime, dict[str, Any] | None]],
) -> list[
    tuple[str, list[str], tuple[int, int, int], list[tuple[int, int, int]]]
]:
    rows: list[
        tuple[str, list[str], tuple[int, int, int], list[tuple[int, int, int]]]
    ] = []
    definitions = (
        ("Temperature °C", "screenTemperature", lambda v: f"{v:.0f}"),
        ("Feels like °C", "feelsLikeTemperature", lambda v: f"{v:.0f}"),
        ("Wind gust mph", "max10mWindGust", None),
        ("Rain", "probOfPrecipitation", None),
        ("Humidity %", "screenRelativeHumidity", lambda v: f"{v:.0f}"),
    )
    for label, field, formatter in definitions:
        values: list[str] = []
        value_colors: list[tuple[int, int, int]] = []
        for _, record in slots:
            value = _slot_value(record, field)
            if value is None:
                values.append("")
                value_colors.append(INK_BLACK)
            elif field == "max10mWindGust":
                arrow = _wind_arrow(
                    record.get("windDirectionFrom10m") if record else None
                )
                gust_mph = value * 2.2369362921
                values.append(f"{arrow} {round(gust_mph)}".strip())
                value_colors.append(_wind_color(gust_mph))
            elif field == "probOfPrecipitation":
                values.append("<5%" if value < 5 else f"{round(value):.0f}%")
                value_colors.append(INK_BLUE)
            else:
                assert formatter is not None
                values.append(formatter(value))
                if field == "screenRelativeHumidity":
                    value_colors.append(_humidity_color(value))
                else:
                    value_colors.append(_temperature_color(value))
        rows.append((label, values, INK_BLACK, value_colors))

    rows.append(("Tide", [""] * len(slots), INK_BLUE, [INK_BLACK] * len(slots)))
    rows.append(
        ("Wave height m", [""] * len(slots), INK_GREEN, [INK_BLACK] * len(slots))
    )
    return rows


def render_forecast(
    location: str,
    forecast: list[dict[str, Any]],
    resolution: tuple[int, int] = DEFAULT_RESOLUTION,
    now: datetime | None = None,
) -> Image.Image:
    width, height = resolution
    image = Image.new("RGB", resolution, "white")
    draw = ImageDraw.Draw(image)
    scale = min(width / 600, height / 448)
    now = (now or datetime.now().astimezone()).astimezone()

    def font_size(size: int, bold: bool = False) -> ImageFont.ImageFont:
        return _font(max(10, round(size * scale)), bold)

    margin = round(8 * scale)
    label_width = round(128 * scale)
    black = INK_BLACK
    gray = (85, 85, 85)
    draw.rectangle((0, 0, width, round(40 * scale)), fill=black)
    draw.text(
        (margin, round(15 * scale)),
        f"{location} - {now.strftime('%A')} {_ordinal(now.day)} "
        f"{now.strftime('%b %Y')}",
        fill="white",
        font=font_size(16, bold=True),
    )
    draw.text(
        (width - margin, round(21 * scale)),
        f"Last updated {now:%H:%M}",
        fill="white",
        font=font_size(14, bold=True),
        anchor="ra",
    )

    slots = _dashboard_times(forecast, now)
    rows = _dashboard_rows(slots)
    LOGGER.debug(
        "Dashboard time slots: %s",
        [slot.strftime("%Y-%m-%d %H:%M %Z") for slot, _ in slots],
    )
    table_top = round(62 * scale)
    header_bottom = round(81 * scale)
    table_bottom = round(320 * scale)
    footer_tides_bottom = round(358 * scale)
    footer_sun_bottom = round(397 * scale)
    row_height = (table_bottom - header_bottom) // len(rows)
    column_width = (width - label_width - margin) / len(slots)

    draw.line((0, round(40 * scale), width, round(40 * scale)), fill=black)
    first_slot_date = slots[0][0].date()
    date_label = "TODAY" if first_slot_date == now.date() else "NEXT DAY"
    draw.text(
        (margin, table_top),
        date_label,
        fill=gray,
        font=font_size(11, bold=True),
        anchor="lm",
    )
    for index, (slot_time, _) in enumerate(slots):
        x = label_width + (index + 0.5) * column_width
        draw.text(
            (x, table_top),
            slot_time.strftime("%H:%M"),
            fill=black,
            font=font_size(13),
            anchor="mm",
        )
        if index < len(slots) - 1:
            next_time = slots[index + 1][0]
            if next_time.date() != slot_time.date():
                draw.line(
                    (
                        label_width + (index + 1) * column_width,
                        table_top + round(10 * scale),
                        label_width + (index + 1) * column_width,
                        table_bottom,
                    ),
                    fill=INK_ORANGE,
                    width=max(1, round(2 * scale)),
                )

    draw.line((0, header_bottom, width, header_bottom), fill=black, width=1)
    row_font = font_size(13, bold=True)
    for row_index, (label, values, label_color, value_colors) in enumerate(rows):
        y = header_bottom + row_index * row_height
        draw.text(
            (margin, y + row_height / 2),
            label,
            fill=label_color,
            font=row_font,
            anchor="lm",
        )
        for column_index, (value, value_color) in enumerate(
            zip(values, value_colors)
        ):
            if value:
                x = label_width + (column_index + 0.5) * column_width
                draw.text(
                    (x, y + row_height / 2),
                    value,
                    fill=value_color,
                    font=row_font,
                    anchor="mm",
                )
        draw.line(
            (0, y + row_height, width, y + row_height),
            fill=(175, 175, 175),
            width=1,
        )

    footer_font = row_font
    footer_small = row_font
    draw.line((0, table_bottom, width, table_bottom), fill=black, width=1)
    draw.text(
        (margin, table_bottom + round(14 * scale)),
        "Next 4 tides:  --  --  --  --",
        fill=black,
        font=footer_font,
        anchor="lm",
    )
    draw.line((0, footer_tides_bottom, width, footer_tides_bottom), fill=black)
    draw.text(
        (margin, footer_tides_bottom + round(14 * scale)),
        "Sun / moon:  Sunset --   Moonrise --   Sunrise --",
        fill=black,
        font=footer_font,
        anchor="lm",
    )
    draw.line((0, footer_sun_bottom, width, footer_sun_bottom), fill=black)
    draw.text(
        (margin, footer_sun_bottom + round(11 * scale)),
        "Electricity today: -- p/kWh",
        fill=INK_ORANGE,
        font=footer_small,
        anchor="lm",
    )
    draw.text(
        (width / 2 + round(6 * scale), footer_sun_bottom + round(11 * scale)),
        "Tomorrow: -- p/kWh",
        fill=INK_ORANGE,
        font=footer_small,
        anchor="lm",
    )
    draw.text(
        (margin, footer_sun_bottom + round(31 * scale)),
        "Gas today: -- p/kWh",
        fill=INK_BLUE,
        font=footer_small,
        anchor="lm",
    )
    draw.text(
        (width / 2 + round(6 * scale), footer_sun_bottom + round(31 * scale)),
        "Tomorrow: -- p/kWh",
        fill=INK_BLUE,
        font=footer_small,
        anchor="lm",
    )
    return image


def show_image(image: Image.Image) -> None:
    from inky.auto import auto

    display = auto()
    if display.resolution != image.size:
        image = image.resize(display.resolution)
    display.set_image(image)
    display.show()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preview",
        metavar="FILE",
        help="save a PNG preview instead of updating the Inky display",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="log API response metadata and forecast field names",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.debug:
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    api_key = os.environ.get("METOFFICE_API_KEY")
    if not api_key:
        parser.error("set METOFFICE_API_KEY to your Met Office DataHub API key")

    try:
        location, forecast = fetch_forecast(api_key)
        image = render_forecast(location, forecast)
        if args.preview:
            image.save(args.preview)
            LOGGER.info("Saved preview to %s", args.preview)
        else:
            show_image(image)
            LOGGER.info("Updated Inky display with the %s forecast.", location)
    except (requests.RequestException, ValueError, WeatherError) as exc:
        LOGGER.exception("Weather update failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
