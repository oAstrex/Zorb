import os
from flask import Flask, redirect, url_for
from config import load_config, cfg
from qbittorrent_compat import qb_api
from worker import start_worker


def create_app() -> Flask:
    # Ensure config is loaded
    load_config()

    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "autostrm-secret-key")

    # Register qBittorrent-compatible API under /api/v2
    app.register_blueprint(qb_api, url_prefix="/api/v2")

    # Simple web UI
    @app.route("/")
    def index():
        return redirect(url_for("web_ui.dashboard"))

    # Web UI blueprint (defined inside qbittorrent_compat)
    from qbittorrent_compat import web_ui  # noqa: E402
    app.register_blueprint(web_ui, url_prefix="")

    return app


def main():
    app = create_app()
    # Start background worker
    start_worker()

    bind = cfg.AUTOSTRM_BIND
    port = int(cfg.AUTOSTRM_PORT)
    app.logger.info("Starting AutoStrm on %s:%s", bind, port)
    app.run(host=bind, port=port)


if __name__ == "__main__":
    main()