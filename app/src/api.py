"""HTTP front-end for waking services and proxying to configured apps.

This module implements a small Flask application that:

- Loads service configurations from YAML files via :class:`ServiceFactory`.
- Exposes a health endpoint at ``/health``.
- Routes all requests to a service determined by it's network location 
  (or netloc + path) and either redirects to the service URL if it's
  online or sends a Wake-on-LAN packet.

Logging is performed via the project's ``logger`` instance.
"""

import signal
import sys
import os
import uuid
import time

from typing import Any
from urllib.parse import urlparse

from gunicorn.app.base import BaseApplication
from flask_cors import cross_origin
from flask import (
        Flask,
        redirect,
        Response,
        jsonify,
        render_template,
        make_response,
        request,
        g,
)

from .utils import check_status, get_identifier
from .service import ServiceFactory
from .notify import NotificationServiceRegistry
from .logger import logger



class Api(BaseApplication):

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


    def __init__(self, direct_netloc: str, port: int, options: dict = {}) -> None:
        
        self.options = options
        self.port = port
        self.direct_netloc = direct_netloc

        self.app = self.__get_app()

        super().__init__()

        signal.signal(signal.SIGTERM, Api.__handle_exit)
        signal.signal(signal.SIGINT, Api.__handle_exit)

        ServiceFactory.load_all()
        NotificationServiceRegistry.load_all()



    def __get_app(self) -> Flask:

        app = Flask(__name__, template_folder = self.TEMPLATES_DIR)

        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.config['SERVER_NAME'] = self.direct_netloc
        app.url_map.host_matching = True

        self.__register_routes(app)
        self.__register_middleware(app)

        return app



    def __register_routes(self, app: Flask):

        @app.route("/preview/<name>", host=self.direct_netloc)
        def handle_preview(name):
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
                TEMPLATE_FILE = os.path.join(self.TEMPLATES_DIR, f"{name}.html")

                if os.path.exists(TEMPLATE_FILE):
                    template = render_template(f"{name}.html")
                else:
                    template = render_template(
                        "default.html",
                        service_name=name,
                    )

                return make_response(template)

            except Exception as e:
                logger.exception(f"Internal: {e}")
                return make_response(f"Internal error: {str(e)}", 500)


        @app.route("/online/", host=self.direct_netloc)
        @cross_origin()
        def handle_online_callback():

            url = request.args.get("url", None)
            if not url:
                return jsonify({"message": f"You must specify the request url"}), 400

            identifier = get_identifier(self.direct_netloc, url)
            if not identifier:
                return jsonify({"message": f"Could not determine network location from {url}"}), 400

            service = ServiceFactory.get_service(identifier)
            if not service:
                logger.error(f"(/online) No service registered for identifier: {identifier}")
                return jsonify({"message": f"Service not found for identifier: {identifier}"}), 404

            def wait():
                logger.info(f"(/online) Waiting for service '{service.filename}' to start.")
                wait_time = 10
                tries = service.cfg.TIMEOUT / wait_time
                try:
                    while tries > 0 and not check_status(service.cfg):
                        yield 'event: online\ndata: {"online": false}\n\n'
                        tries -= 1
                        time.sleep(wait_time)

                    if tries <= 0:
                        yield 'event: error\ndata: {"msg": "timeout exceeded"}\n\n'
                        logger.warning(f"(/online) Service '{service.filename}' start timed out.")
                    else:
                        logger.info(f"(/online) Service '{service.filename}' started.")
                        yield 'event: online\ndata: {"online": true}\n\n'
                except GeneratorExit:
                    logger.info("(/online) Client closed.")

            return Response(
                wait(),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )


        @app.route("/health", host=f"127.0.0.1:{self.port}")
        def handle_health():
            """Simple healthcheck endpoint.

            Returns:
                A JSON object with ``status: ok`` when the service is healthy.
            """
            return jsonify({"status": "ok"})


        @app.route('/', defaults={'path': ''}, host='<host>')
        @app.route('/<path:path>', host='<host>')
        def main(host, path):
            """Main catch-all route.

            Args:
                path: Path component captured by the route (unused for routing, passed
                    to service checks).

            Returns:
                A Flask response object. Possible responses:
                - 404 if no service is registered for the request identifier.
                - 503 if the path is ignored for background requests.
                - 302 redirect to the service URL when the target is already online.
                - 202 plus a status page when a Wake-on-LAN packet was sent.
            """

            ip: str = request.headers.get('X-Forwarded-For', request.remote_addr) or "unknown"

            identifier = get_identifier(self.direct_netloc, request.url)
            if not identifier:
                logger.warning(f"Could not determine network location from {request.url}")
                return jsonify({"message": f"Could not determine network location from {request.url}"}), 400
            
            logger.info(f"Getting service {identifier}")
            service = ServiceFactory.get_service(identifier)
            if not service:
                logger.warning(f"No service registered for identifier: {identifier}")
                return jsonify({"message": f"Service not found for identifier: {identifier}"}), 404

            logger.debug(f"Retrieved service {service.cfg.file_metadata.path} for {identifier}")
            try:

                if service.should_ignore(path):
                    logger.info(f"Requested path '{path}' ignored for waking")
                    return service.respond("Server offline - background sync ignored", self.direct_netloc, 503)

                if service.check_status():
                    logger.info(f"Server online, redirecting to {request.url}")
                    return redirect(request.url)

                service.wake(identifier, ip)
                return service.respond("Waking up the server...", self.direct_netloc, 202)

            except Exception as e:
                logger.exception(f"Internal error: {e}")
                return service.respond(f"Internal error: {str(e)}", self.direct_netloc, 500)



    def __register_middleware(self, app: Flask):

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



    def load(self) -> Any:
        return self.app



    def load_config(self):
        config = {key: value for key, value in self.options.items()
                  if key in self.cfg.settings and value is not None}
        for key, value in config.items():
            self.cfg.set(key.lower(), value)



    @staticmethod
    def __handle_exit(signum, frame):
        """Handle termination signals and exit gracefully.

        Args:
            signum: Signal number received.
            frame: Current stack frame (ignored).
        """
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        sys.exit(0)
