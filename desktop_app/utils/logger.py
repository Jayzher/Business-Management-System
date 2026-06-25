import logging
from logging.handlers import RotatingFileHandler

from .. import config

_FORMATTER = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 5


def setup_logger(name, log_file, level=logging.INFO):
    """Set up a named logger with a rotating file handler and console echo."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    log_file.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding='utf-8'
    )
    file_handler.setFormatter(_FORMATTER)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(_FORMATTER)
    logger.addHandler(console_handler)

    return logger


app_logger = setup_logger('desktop_app', config.LOGS_DIR / 'desktop_app.log')
server_logger = setup_logger('django_server', config.LOGS_DIR / 'django_server.log')
