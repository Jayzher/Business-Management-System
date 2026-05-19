"""
Django settings for inventory_system project.
"""

import os
import dj_database_url
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-(rjes1td=vi78qsiis1c_7wg%at12zyj0#)2gua8$y7-u_17az'
)

DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

_raw_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,192.168.1.7,10.0.2.2,.onrender.com')
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(',') if h.strip()]

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    # Third-party
    'channels',
    'rest_framework',
    'rest_framework_simplejwt',
    'django_filters',
    'corsheaders',
    'mptt',
    # Project apps
    'core',
    'accounts',
    'catalog',
    'partners',
    'warehouses',
    'inventory',
    'procurement',
    'sales',
    'qr',
    'reports',
    'audit',
    'pricing',
    'pos',
    'services',
    'cashflow',
    'sync',
    'theme',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # ── Environment routing: must come after SessionMiddleware ──
    'inventory_system.env_middleware.AppEnvironmentMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'theme.middleware.ModalFormMiddleware',
]

ROOT_URLCONF = 'inventory_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'builtins': ['theme.templatetags.custom_filters'],
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'theme.context_processors.sidebar_menu',
                'theme.context_processors.user_role_flags',
            ],
        },
    },
]

WSGI_APPLICATION = 'inventory_system.wsgi.application'
ASGI_APPLICATION = 'inventory_system.asgi.application'

# ---------------------------------------------------------------------------
# Channel Layer (Django Channels)
#
# Production: set REDIS_URL env var (e.g. redis://localhost:6379/0).
# Development fallback: in-memory channel layer (single-process only).
# ---------------------------------------------------------------------------
_REDIS_URL = os.environ.get('REDIS_URL', '')
if _REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [_REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# ---------------------------------------------------------------------------
# Neon PostgreSQL connection string
# ---------------------------------------------------------------------------
NEON_URL = (
    'postgresql://neondb_owner:npg_KhjsX3uB0mil'
    '@ep-raspy-hall-a1fl4lfx.ap-southeast-1.aws.neon.tech'
    '/neondb?sslmode=require'
)

# ---------------------------------------------------------------------------
# Pusher Channels — free hosted pub/sub for real-time sync events.
# ---------------------------------------------------------------------------
PUSHER_APP_ID  = os.environ.get('PUSHER_APP_ID',  '2138689')
PUSHER_KEY     = os.environ.get('PUSHER_KEY',     'f2314ae2921907f1b2f7')
PUSHER_SECRET  = os.environ.get('PUSHER_SECRET',  '3a325d3c3376facaa14b')
PUSHER_CLUSTER = os.environ.get('PUSHER_CLUSTER', 'ap1')

# ---------------------------------------------------------------------------
# Database Architecture
# ---------------------------------------------------------------------------
#
# Neon PostgreSQL = authoritative source of truth (all writes go here).
# Local SQLite    = fast read cache for page rendering.
#
# Modes (controlled by DATABASE_URL env var):
#   DATABASE_URL=sqlite          → Offline dev mode: SQLite-only, no Neon.
#   DATABASE_URL=<postgres-url>  → Production: Neon is default, SQLite is cache.
#   (unset)                      → Hybrid: Neon is default, SQLite is cache.
#
# The DB router sends reads to 'local_cache' and writes to 'default'.
# Signals mirror every write to local_cache synchronously after commit.
# ---------------------------------------------------------------------------

# Run a full Neon→SQLite sync once when the Django server process starts.
# Set NEON_INITIAL_SYNC=false to disable (e.g. CI, fast restarts).
NEON_INITIAL_SYNC = os.environ.get('NEON_INITIAL_SYNC', 'true').lower() in ('true', '1', 'yes')

# Timer-based interval sync (seconds). 0 = disabled (event-driven only).
NEON_SYNC_INTERVAL = int(os.environ.get('NEON_SYNC_INTERVAL', '0'))

_DATABASE_URL = os.environ.get('DATABASE_URL', '')
_OFFLINE_MODE = _DATABASE_URL == 'sqlite'

if _OFFLINE_MODE:
    # ── Offline dev: SQLite-only, no Neon dependency ──────────────────────
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(BASE_DIR / 'db.sqlite3'),
            'OPTIONS': {
                'timeout': 30,  # Wait up to 30s for locks (prevents "database is locked")
            },
        },
        'local_cache': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(BASE_DIR / 'db.sqlite3'),
            'OPTIONS': {
                'timeout': 30,
            },
        },
    }
    SYNC_MODE = 'offline'
else:
    # ── Normal mode: Local-first architecture ─────────────────────────────
    # Reads + Writes → local_cache (SQLite, instant)
    # Background worker pushes to Neon (PostgreSQL) asynchronously
    _neon_config = dj_database_url.parse(
        _DATABASE_URL or NEON_URL,
        conn_max_age=600,
        ssl_require=True,
    )
    DATABASES = {
        'default': _neon_config,
        'local_cache': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(BASE_DIR / 'db.sqlite3'),
            'OPTIONS': {
                'timeout': 30,  # Wait up to 30s for locks
            },
        },
    }
    SYNC_MODE = 'neon_primary'

# ---------------------------------------------------------------------------
# Test environment database
# Set TEST_DATABASE_URL env var to enable the environment toggle.
# ---------------------------------------------------------------------------
_TEST_DATABASE_URL = os.environ.get('TEST_DATABASE_URL', '')
if _TEST_DATABASE_URL:
    DATABASES['test_env'] = dj_database_url.config(
        default=_TEST_DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True,
    )

DATABASE_ROUTERS = ['inventory_system.db_router.AppEnvironmentRouter']

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ---------------------------------------------------------------------------
# REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
}

# ---------------------------------------------------------------------------
# CORS — allow mobile app connections
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = True

# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------
CSRF_TRUSTED_ORIGINS = os.environ.get(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    'http://192.168.1.7:8000,http://localhost:8000,http://127.0.0.1:8000'
).split(',')

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & Media files
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Production security settings (active when DEBUG=False)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ---------------------------------------------------------------------------
# QR Code settings
# ---------------------------------------------------------------------------
QR_CODE_DIR = MEDIA_ROOT / 'qrcodes'

# ---------------------------------------------------------------------------
# SQLite Performance: WAL mode + busy timeout
# ---------------------------------------------------------------------------
# WAL (Write-Ahead Logging) allows concurrent reads and writes on SQLite.
# Without WAL, the background sync worker would block user requests because
# SQLite's default journal mode only allows one writer at a time.
#
# With WAL:
#   - Multiple readers can read simultaneously (no blocking)
#   - One writer can write while readers are reading (no blocking)
#   - Multiple writers queue up with busy_timeout (instead of failing)
#
# This is set via the connection_created signal so it applies to every
# new SQLite connection (including those from background threads).
# ---------------------------------------------------------------------------
from django.db.backends.signals import connection_created


def _set_sqlite_pragmas(sender, connection, **kwargs):
    """Set performance PRAGMAs on every new SQLite connection."""
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA busy_timeout=30000;')  # 30s wait instead of failing
        cursor.execute('PRAGMA synchronous=NORMAL;')  # Faster writes, still safe with WAL
        cursor.execute('PRAGMA cache_size=-64000;')   # 64MB page cache
        cursor.execute('PRAGMA temp_store=MEMORY;')   # Temp tables in RAM


connection_created.connect(_set_sqlite_pragmas)
