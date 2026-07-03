# wake-on-http

**Wake-on-http** provides a small service that wakes offline servers (via Wake-on-LAN) when a request is made to one of their services through a reverse proxy (i use Nginx Proxy Manager). When a user tries to access a service on an offline server, this application receives the forwarded request, sends a WOL packet to the target machine, and displays a "Waking up..." status page. Once the service is online, the user is redirected to the actual application.

# Use Case

**Wake-on-http** is designed for homelabs, where energy consumption is important, and a low-power computer is available. In combination with a simple shutdown script (available on my GitHub) to power off the server when it’s not needed, this project can save you a lot in electricity bills.
In my homelab, I have an old PC serving as my workhorse server and a Raspberry Pi for lighter tasks. Over the last 6 months, my server used **24.97 kWh** in total. If I had run the server 24/7, it would have used at least **175 kWh** (idle power usage is ~40W). But with this project and a shutdown script running, that drops to **42 kWh**, combined with ~17 kWh for the Raspberry Pi, over the last 6 months, representing a significant power saving.

## Features

- **Automatic Wake-on-LAN**: Sends a Magic Packet to the configured MAC address when a service is accessed but offline.
- **Status Page**: Displays a loading page while the server is booting.
- **Configuration**: Simple YAML-based configuration for each service.
- **Preview Mode**: Preview startup templates without triggering WOL.

## Structure

```
wake-on-http/
├── services/             # YAML configuration files for each service
├── notifiers/            # YAML configuration files for each notification service
└── app/
    ├── src/              # Source code
    │   ├── main.py       # Main entrypoint
    │   ├── api.py        # Flask application entry point
    │   ├── service.py    # Service logic and registry
    │   └── ...
    ├── templates/        # HTML templates for the waking page, default provided
    └── tests/            # Unit tests
```

## Configuration

Services are defined in YAML files located in the `services/` directory. The filename (without extension) is used as the service ID.

Example `services/jellyfin.yml`:

```yaml
HOST_MAC: "00:11:22:33:44:55"         # MAC address of the host machine
HOST_IP: "192.168.1.10"               # IP address to check for connectivity
HOST_PORT: 8096                       # Port to check for connectivity (optional, internal port)
APP_URL: "http://jellyfin.local:8096" # The full URL of the service
NOTIFY:                               # Notification services to use
  - "server-wakes"
IGNORED_PATHS:                        # Paths that should not trigger a wake event
  - "/api/system/status"
```

To add a new service replace the values in the above file with the parameters of your service and optionally add a custom HTML template with the same filename (without extension) as the YML file.

Example Nginx Proxy Manager "custom nginx configuration" for Jellyfin:
```nginx
location / {
    proxy_connect_timeout 2s;
    proxy_read_timeout 2s;

    error_page 502 504 = @wol;
    proxy_pass http://192.168.0.101:8096;
}

location @wol {
    internal;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_pass http://192.168.0.102:5000;
}
```

## How it works

1. The Flask app receives a request (e.g., to `http://jellyfin.example.com`).
2. It looks up the service configuration based on the hostname.
3. It checks if the service (at `HOST_IP`) is online.
   - **If Online**: Redirects the user to `APP_URL`.
   - **If Offline**:
     - Sends a Wake-on-LAN packet to `HOST_MAC`.
     - Returns a 202 status code and renders the service's HTML template (or `default.html`).

## Templates

Place HTML templates in the `templates/` directory.
- `default.html`: Used if no specific template is found.
- `<service_name>.html`: Used for a specific service (e.g., `jellyfin.html` for `services/jellyfin.yml`).

## Development

### Prerequisites

- Python 3.11+
- Virtual environment

### Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running

```bash
python3 app/src/main.py
```

### Testing

Run the unit tests with:

```bash
pytest -v --cov=app.src --cov-report=html app/tests
```