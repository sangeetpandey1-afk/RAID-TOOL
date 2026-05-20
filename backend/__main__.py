"""Entry point so ``python -m backend`` works."""
from .app import app, config
import logging

if __name__ == "__main__":
    log = logging.getLogger("startup")
    log.info("Listening on http://%s:%s  (debug=%s)",
             config.HOST, config.PORT, config.DEBUG)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG,
            threaded=True, use_reloader=False)
