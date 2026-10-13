# InkyDisplay2026

Code for a 600x448 Inky Impression 5.7-inch, seven-colour e-ink display on a
Raspberry Pi.

## Met Office API key

Create a local `.env` file containing your Met Office DataHub API key:

```text
METOFFICE_API_KEY=your_api_key
```

`.env` is ignored by Git. Never commit or publish it. Use `.env.example` as a
safe template.

## Scripts

### Display the dashboard

`metoffice_weather.py` fetches the Llandudno hourly forecast from the Met Office
Site-specific API and draws the dashboard. On the Pi, using the Pimoroni
environment:

```sh
set -a
. /home/pi/.env
set +a
/home/pi/.virtualenvs/pimoroni/bin/python /home/pi/metoffice_weather.py
```

To save a PNG instead of updating the e-ink panel:

```sh
python metoffice_weather.py --preview dashboard.png
```

The dashboard's tide, wave, sun/moon and energy-price sections are placeholders
until data sources for them are configured.

### Inspect the API response

`metoffice_inspect.py` reads `.env` beside the script and prints the hourly API
response as a table by default, or as raw JSON:

```sh
python metoffice_inspect.py --format table
python metoffice_inspect.py --format json
```

The inspector uses only the Python standard library.

## Files

- `metoffice_weather.py` — Inky dashboard renderer and Met Office client.
- `metoffice_inspect.py` — command-line hourly response inspector.
- `DisplayTemplate_v1.png` — dashboard layout mockup.
- `.env.example` — safe environment-file template.
