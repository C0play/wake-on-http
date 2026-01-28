# wake-on-http

**Wake-on-http** provides a small service that wakes offline servers (via Wake-on-LAN) when a request is made to one of their services through a reverse proxy (like Nginx Proxy Manager). When a user tries to access a service on an offline server, this application receives the forwarded request, sends a WOL packet to the target machine, and displays a "Waking up..." status page. Once the service is online, the user is redirected to the actual application.

## Features

- **Automatic Wake-on-LAN**: Sends a Magic Packet to the configured MAC address when a service is accessed but offline.
- **Status Page**: Displays a loading page while the server is booting.
- **Configuration**: Simple YAML-based configuration for each service.
- **Preview Mode**: Preview startup templates without triggering WOL.

## Structure

```
wake-on-http/
├── configs/          # YAML configuration files for each service
├── templates/        # HTML templates for the waking page, default provided
├── src/              # Source code
│   ├── main.py       # Flask application entry point
│   ├── service.py    # Service logic and registry
│   └── ...
└── tests/            # Unit tests
```

## Configuration

Services are defined in YAML files located in the `configs/` directory. The filename (without extension) is used as the service ID.

Example `configs/jellyfin.yml`:

```yaml
HOST_MAC: "00:11:22:33:44:55"         # MAC address of the host machine
HOST_IP: "192.168.1.10"               # IP address to check for connectivity
HOST_PORT: 8096                       # Port to check for connectivity (optional, internal port)
APP_URL: "http://jellyfin.local:8096" # The full URL of the service
IGNORED_PATHS:                        # Paths that should not trigger a wake event
  - "/api/system/status"
```

To add a new service replace the values in the above file with the parameters of your service and optionally add a custom HTML template with the same filename (without extension) as the YML file.

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
- `<service_name>.html`: Used for a specific service (e.g., `jellyfin.html` for `configs/jellyfin.yml`).

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
python3 src/main.py
```

### Testing

Run the unit tests with:

```bash
python3 -m unittest tests/test_app.py
```