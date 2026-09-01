"""
Django settings for lolburger project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(nome, padrao):
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in ('1', 'true', 'yes', 'on', 'sim')


def _env_list(nome, padrao):
    valor = os.environ.get(nome)
    if not valor:
        return list(padrao)
    return [item.strip() for item in valor.split(',') if item.strip()]


# ---------------------------------------------------------------------------
# Segurança / ambiente
# ---------------------------------------------------------------------------
# Em produção defina LOLBURGUER_SECRET_KEY e LOLBURGUER_DEBUG=False no ambiente.
SECRET_KEY = os.environ.get(
    'LOLBURGUER_SECRET_KEY',
    'django-insecure-lhxj#^j$+^if18u3tt1_gae0k35v-h1h(k+g2-be_&%q50=*t0',
)

DEBUG = _env_bool('LOLBURGUER_DEBUG', True)

# Com DEBUG ligado libera tudo (uso local). Sem DEBUG exige a lista explícita.
if DEBUG:
    ALLOWED_HOSTS = _env_list('LOLBURGUER_ALLOWED_HOSTS', ['*'])
else:
    ALLOWED_HOSTS = _env_list('LOLBURGUER_ALLOWED_HOSTS', ['localhost', '127.0.0.1'])

CSRF_TRUSTED_ORIGINS = _env_list('LOLBURGUER_CSRF_TRUSTED_ORIGINS', [])


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'produtos',
    'estoque',
    'vendas',
    'relatorios',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.UsuarioAtualMiddleware',
]

ROOT_URLCONF = 'lolburger.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'lolburger.wsgi.application'


# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('LOLBURGUER_DB_PATH', str(BASE_DIR / 'db.sqlite3')),
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

DECIMAL_SEPARATOR = ','
USE_THOUSAND_SEPARATOR = True
THOUSAND_SEPARATOR = '.'


# Static / media

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        # Sem manifest: não quebra se o collectstatic ainda não rodou.
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

AUTH_USER_MODEL = 'core.Usuario'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# Endurecimento aplicado só fora do modo DEBUG
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SESSION_COOKIE_HTTPONLY = True
    X_FRAME_OPTIONS = 'DENY'
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SAMESITE = 'Lax'

    # HTTPS: ligue só se o sistema for servido atrás de TLS.
    if _env_bool('LOLBURGUER_HTTPS', False):
        SECURE_SSL_REDIRECT = True
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
