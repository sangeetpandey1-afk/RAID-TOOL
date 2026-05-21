"""
Raid Management System — Flask entry point.

Usage:
    python -m backend.app

The application installs a global JSON error handler so the user **never**
sees an opaque "HTTP 500" again — every error returns a structured response
with traceback (in debug mode) and is logged to logs/server.log.
"""
from __future__ import annotations
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

from flask import Flask, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from . import config
from .database import close_connection, init_schema
from .utils import envelope_ok, envelope_error


# ----------------------------------------------------------------- logging
def _setup_logging() -> None:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)
    root.handlers.clear()

    # Console
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    root.addHandler(sh)

    # Rotating file
    fh = RotatingFileHandler(
        config.LOGS_DIR / "server.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(formatter)
    root.addHandler(fh)


# ------------------------------------------------------------------ factory
def create_app() -> Flask:
    _setup_logging()
    log = logging.getLogger(__name__)
    log.info("=== Raid Management System starting ===")
    log.info("Repo root: %s", config.ROOT_DIR)
    log.info("DB path:   %s", config.DB_PATH)

    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False  # keep हिंदी text readable
    app.config["JSON_SORT_KEYS"] = False
    CORS(app, resources={r"/api/*": {"origins": "*"}})  # Excel VBA needs CORS off

    # Initialize schema (idempotent)
    init_schema()

    # Register blueprints
    from .routes.health import bp as health_bp
    from .routes.master_data import bp as master_bp
    from .routes.consumer import bp as consumer_bp
    from .routes.case import bp as case_bp
    from .routes.document import bp as doc_bp
    from .routes.payment import bp as payment_bp
    from .routes.inquiry import bp as inquiry_bp
    from .routes.notice import bp as notice_bp
    from .routes.device_rate import bp as devrate_bp
    from .routes.upload import bp as upload_bp
    from .routes.mobile import bp as mobile_bp

    for bp in (health_bp, master_bp, consumer_bp, case_bp, doc_bp,
               payment_bp, inquiry_bp, notice_bp, devrate_bp,
               upload_bp, mobile_bp):
        app.register_blueprint(bp)

    # ----------------- error handlers (no more silent 500s) ----------
    @app.errorhandler(HTTPException)
    def _http_err(e: HTTPException):
        log.warning("HTTP %s on %s %s: %s",
                    e.code, request.method, request.path, e.description)
        return envelope_error(e.description or e.name, status=e.code or 500,
                              code=f"HTTP_{e.code}")

    @app.errorhandler(Exception)
    def _unhandled(e: Exception):
        tb = traceback.format_exc()
        log.error("UNHANDLED EXCEPTION on %s %s\n%s",
                  request.method, request.path, tb)
        return envelope_error(
            f"{type(e).__name__}: {e}",
            status=500,
            code="UNHANDLED",
            details=tb if config.DEBUG else None,
        )

    @app.teardown_appcontext
    def _teardown(exc):
        close_connection(exc)

    @app.route("/")
    def _root():
        return envelope_ok({
            "service": "Raid Management System",
            "version": "1.0.0",
            "docs": "/api/health",
        })

    log.info("App ready. Routes registered: %d", len(list(app.url_map.iter_rules())))
    return app


# Module-level app for `flask run` and `python -m backend.app`
app = create_app()


if __name__ == "__main__":
    log = logging.getLogger("startup")
    log.info("Listening on http://%s:%s  (debug=%s)",
             config.HOST, config.PORT, config.DEBUG)
    # threaded=True allows Excel VBA to fire multiple requests
    # use_reloader=False avoids watchdog log-spam in containerized envs
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG,
            threaded=True, use_reloader=False)
