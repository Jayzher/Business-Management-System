"""Desktop-mode Django settings overlay.

Imported from settings.py when DESKTOP_MODE=true. Reads absolute paths
from BMS_* env vars injected by desktop_app/utils/process_utils.py so
Django doesn't need to import the desktop_app package.
"""
import os
import sys
from pathlib import Path

# BASE_DIR for the bundled-asset case (templates, static collected by PyInstaller).
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    # settings_desktop.py -> inventory_system/ -> project root
    BASE_DIR = Path(__file__).resolve().parent.parent


def _env_path(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    if value:
        path = Path(value)
    else:
        path = fallback
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _env_dir(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    path = Path(value) if value else fallback
    path.mkdir(parents=True, exist_ok=True)
    return path


_DB_PATH = _env_path('BMS_DB_PATH', BASE_DIR / 'db.sqlite3')
_SESSIONS_DIR = _env_dir('BMS_SESSIONS_DIR', BASE_DIR / 'sessions')
_CACHE_DIR = _env_dir('BMS_CACHE_DIR', BASE_DIR / 'cache')
_LOGS_DIR = _env_dir('BMS_LOGS_DIR', BASE_DIR / 'logs')
_MEDIA_DIR = _env_dir('BMS_MEDIA_DIR', BASE_DIR / 'media')

DEBUG = False  # Desktop ships as a release build; keep tracebacks out of the webview.
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# Try local SQLite first; fall back to Neon on first login to cache credentials locally.
AUTHENTICATION_BACKENDS = ['accounts.backends.NeonFallbackBackend']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': str(_DB_PATH),
        'OPTIONS': {'timeout': 30},
    },
}

# Drop the Neon/local_cache router — only one DB exists in desktop mode.
DATABASE_ROUTERS = []
SYNC_MODE = 'offline'

# Persist sessions on disk so they survive across launches.
SESSION_ENGINE = 'django.contrib.sessions.backends.file'
SESSION_FILE_PATH = str(_SESSIONS_DIR)

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': str(_CACHE_DIR),
    },
}

MEDIA_ROOT = str(_MEDIA_DIR)
MEDIA_URL = '/media/'

# Disable optional services for offline-first desktop mode.
NEON_INITIAL_SYNC = False
NEON_SYNC_INTERVAL = 0

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

CORS_ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
        },
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(_LOGS_DIR / 'django.log'),
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['file', 'console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
