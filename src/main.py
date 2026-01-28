"""HTTP front-end for waking services and proxying to configured apps.

This module implements a small Flask application that:

- Loads service configurations from YAML files via :class:`ServiceFactory`.
- Exposes a health endpoint at ``/health``.
- Routes all requests to a service determined by hostname and either redirects
    to the service URL if it's online or triggers a Wake-on-LAN packet.

Logging is performed via the project's ``logger`` instance.
"""

from urllib.parse import urlparse
import signal
import sys
import os
import uuid
from flask import (
        Flask, redirect,
        request, jsonify,
        render_template,
        make_response, g
)

from service import ServiceFactory
from logger import logger


# ===== CONFIG =====

def handle_exit(signum, frame):
    """Handle termination signals and exit gracefully.

    Args:
        signum: Signal number received.
        frame: Current stack frame (ignored).
    """
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)


ServiceFactory.load_all()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS']


# ======= APP ======

app = Flask(__name__, template_folder=TEMPLATES_DIR)
app.config['TEMPLATES_AUTO_RELOAD'] = True


@app.before_request
def before_request():
    """Per-request setup.

    - Refreshes service registry.
    - Assigns a short request id to ``g.request_id`` for logging.
    - Skips processing for the health endpoint.

    This function also logs an informational line containing the hostname,
    request method, path and client IP (honoring ``X-Forwarded-For`` if set).
    """

    url_path = urlparse(request.url).path
    if url_path == "/health":
        return

    ServiceFactory.refresh()

    g.request_id = str(uuid.uuid4())[:6]
    ip: str | None = request.headers.get('X-Forwarded-For', request.remote_addr)
    hostname = urlparse(request.url).hostname or request.host.split(':')[0]

    logger.info(f"[+] ({hostname}) : {request.method} {url_path} from {ip}")


@app.route('/health')
def health():
    """Simple healthcheck endpoint.

    Returns:
        A JSON object with ``status: ok`` when the service is healthy.
    """

    return jsonify({"status": "ok"})


@app.route('/', defaults={'path': ''}, methods=METHODS)
@app.route('/<path:path>', methods=METHODS)
def main(path):
    """Main catch-all route: determine service and either redirect or wake.

    Args:
        path: Path component captured by the route (unused for routing, passed
            to service checks).

    Returns:
        A Flask response object. Possible responses:
        - 404 if no service is registered for the request hostname.
        - 503 if the path is ignored for background requests.
        - 302 redirect to the service URL when the target is already online.
        - 202 plus a status page when a Wake-on-LAN packet was sent.
    """

    hostname = urlparse(request.url).hostname or request.host.split(':')[0]
    service = ServiceFactory.get_service(hostname)

    if not service:
        logger.warning(f"No service registered for hostname: {hostname}")
        return jsonify({"message": f"Service not found for {hostname}"}), 404

    try:

        if service.should_ignore(path):
            logger.info(f"Background request {path} ignored for waking")
            return service.respond("Server offline - background sync ignored", 503)

        if service.check_status():
            logger.info(f"Server online, redirecting to {service.cfg.APP_URL}")
            return redirect(service.cfg.APP_URL)

        service.wake(request)
        return service.respond("Waking up the server...", 202)

    except Exception as e:
        logger.exception(f"Internal error: {e}")
        return service.respond(f"Internal error: {str(e)}", 500)


@app.route('/preview/<name>')
def preview(name):
    """Render a template preview for a service template.

    If ``<name>.html`` exists in the templates directory it will be rendered,
    otherwise ``default.html`` will be rendered with ``service_name=<name>``.

    Args:
        name: Template name without extension.

    Returns:
        A Flask response containing the rendered template or a 500 error page on
        exception.
    """

    try:
        TEMPLATE_FILE = os.path.join(TEMPLATES_DIR, f"{name}.html")

        if os.path.exists(TEMPLATE_FILE):
            template = render_template(f"{name}.html")
        else:
            template = render_template(
                f"default.html",
                service_name=name,
            )

        return make_response(template)

    except Exception as e:
        logger.exception(f"Internal: {e}")
        return make_response(f"Internal error: {str(e)}", 500)


@app.after_request
def after_request(response):
    """Post-request hook to log response status.

    Args:
        response: Response instance returned by the view.

    Returns:
        The response.
    """

    if urlparse(request.url).path != "/health":
        logger.info(f"[-] Status: {response.status_code}")
    return response



if __name__ == "__main__":
    try:
        port = int(os.getenv("SERVER_PORT", "5000"))
        app.run(host="0.0.0.0", port=port, load_dotenv=True)
    except Exception as e:
        logger.error(f"Failed to start Flask app: {e}")


