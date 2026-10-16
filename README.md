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

### Deploy to pi

scp -o BatchMode=yes 'metoffice_weather.py' pi@rpi-robot2:/home/pi/metoffice_weather.py; if ($LASTEXITCODE -eq 0) { ssh -o BatchMode=yes pi@rpi-robot2 'set -a; . /home/pi/.env; set +a; /home/pi/.virtualenvs/pimoroni/bin/python /home/pi/metoffice_weather.py --debug' }

### Local setup on Windows

Create an isolated virtual environment and install the dependencies needed for
the preview and API inspection scripts:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

In VS Code, select `.venv\Scripts\python.exe` with **Python: Select
Interpreter**. Then, in a PowerShell terminal, load the key and create a
preview:

```powershell
$env:METOFFICE_API_KEY = (Get-Content .env | Where-Object { $_ -match '^METOFFICE_API_KEY=' } | Select-Object -First 1) -replace '^METOFFICE_API_KEY=', ''
.\.venv\Scripts\python.exe .\metoffice_weather.py --preview .\dashboard-preview.png
```

`requirements.txt` contains the cross-platform API and image dependencies. The
Inky package is only needed on the Raspberry Pi to update the physical display;
XTide is optional and tide/sun/moon values are left blank when its `tide`
command is not installed.

### Display the dashboard

`metoffice_weather.py` fetches the Llandudno hourly forecast from the Met Office
Site-specific API, runs XTide for the local tide and sun/moon event times, and
draws the dashboard. XTide must be installed on the Pi with the Llandudno
station data available. On the Pi, using the Pimoroni environment:

The weather table shows six forecast columns at two-hour intervals, covering
the next 12 hours.

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

Tide heights/times and daily sun/moon event times are read from the `tide`
command. The tide row shows predicted heights and rising/falling arrows at the
forecast times; the next sun and moon events are listed chronologically. Wave
heights for the six forecast times are extracted from the Met Office Llandudno
North Shore beach forecast. Wave-height colours are black at 0m, blue below
0.5m, green below 1m, orange through 1.5m, and red above 1.5m. Energy-price
values remain placeholders.

### Inspect the API response

`metoffice_inspect.py` reads `.env` beside the script and prints the hourly API
response as a table by default, or as raw JSON:

```sh
python metoffice_inspect.py --format table
python metoffice_inspect.py --format json
```

The inspector uses only the Python standard library.

### Inspect beach wave heights

`metoffice_beach_waves.py` downloads the Llandudno North Shore forecast page
and extracts its hourly wave-height table as JSON. This webpage currently
includes the values in server-rendered HTML rather than exposing a separate
JSON endpoint, so the script converts that table into JSON:

```powershell
.\.venv\Scripts\python.exe .\metoffice_beach_waves.py --pretty
```

This script uses only the Python standard library and does not need the
Met Office API key.

## Files

- `metoffice_weather.py` — Inky dashboard renderer and Met Office client.
- `metoffice_inspect.py` — command-line hourly response inspector.
- `metoffice_beach_waves.py` — Llandudno beach wave-height forecast inspector.
- `DisplayTemplate_v1.png` — dashboard layout mockup.
- `.env.example` — safe environment-file template.
