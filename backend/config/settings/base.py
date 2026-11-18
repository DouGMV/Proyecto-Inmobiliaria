"""
Configuración común a todos los entornos.

dev.py, test.py y prod.py importan este archivo y solo cambian lo que es
distinto en su entorno. Todo valor que dependa del entorno o sea secreto se
lee de variables de entorno; nunca se escribe aquí.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

# backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# En desarrollo las variables vienen del .env en la raíz del repositorio.
# En la integración continua y en producción no hay .env: las variables las
# define el entorno, y read_env no sobrescribe las que ya existen.
environ.Env.read_env(BASE_DIR.parent / ".env")


# ---------- Seguridad ----------

# Sin valor por defecto a propósito: si falta, Django no arranca. Es preferible
# a arrancar con una clave falsa (spec 001, §8).
SECRET_KEY = env("SECRET_KEY")

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])


# ---------- Aplicaciones ----------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    # Instalada como app para que sus mensajes de error salgan en español.
    "rest_framework_simplejwt",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
]

# Primero las transversales, que cualquier app puede importar, y luego los
# dominios del negocio (docs/arquitectura.md §3).
LOCAL_APPS = [
    "apps.core",
    "apps.usuarios",
    "apps.auditoria",
    "apps.catalogo",
    "apps.crm",
    "apps.ventas",
    "apps.arrendamientos",
    "apps.compras",
    "apps.construccion",
    "apps.reportes",
    "apps.ia",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Modelo de usuario propio (login por correo). Debe estar definido antes del
# primer migrate: cambiarlo después obliga a recrear la base de datos, porque
# las tablas de Django (admin, permisos) ya apuntarían al User estándar.
AUTH_USER_MODEL = "usuarios.Usuario"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Justo después de SecurityMiddleware: sirve los archivos estáticos antes de
    # que el resto de la cadena procese la petición (spec 002, §5.3).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Antes de CommonMiddleware: debe agregar las cabeceras de CORS incluso a
    # las respuestas que CommonMiddleware genera por su cuenta (redirecciones).
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ---------- Base de datos ----------

# Solo PostgreSQL, en todos los entornos (CLAUDE.md prohíbe SQLite).
# Sin valor por defecto, por la misma razón que SECRET_KEY.
DATABASES = {
    "default": env.db("DATABASE_URL"),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------- Contraseñas ----------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        # Mínimo de 10 caracteres (docs/arquitectura.md §9).
        "OPTIONS": {"min_length": 10},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ---------- Idioma y zona horaria ----------

LANGUAGE_CODE = "es"

# Zona en que se muestran las fechas en el panel. Las fechas se guardan
# siempre en UTC gracias a USE_TZ.
TIME_ZONE = "America/Guatemala"

USE_I18N = True

USE_TZ = True


# ---------- Archivos estáticos ----------

STATIC_URL = "static/"

# Destino de collectstatic. Cómo se sirven en producción lo decide la spec 002.
STATIC_ROOT = BASE_DIR / "staticfiles"


# ---------- Archivos subidos (spec 011) ----------

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Dónde se guardan los documentos oficiales. "local" en desarrollo y pruebas;
# "s3" en producción, contra el bucket privado de Supabase (spec 011, §6).
STORAGE_BACKEND = env("STORAGE_BACKEND", default="local")
if STORAGE_BACKEND not in {"local", "s3"}:
    raise ImproperlyConfigured(
        f"STORAGE_BACKEND desconocido: {STORAGE_BACKEND!r}. Use 'local' o 's3'."
    )

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Se declara también aquí para no perderlo al definir STORAGES: en
    # producción prod.py lo cambia por el de WhiteNoise (spec 002, §5.3).
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

if STORAGE_BACKEND == "s3":
    # Supabase Storage habla el protocolo S3, así que se usa el backend estándar
    # de django-storages en vez de escribir uno propio (spec 011, §10).
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "endpoint_url": env("STORAGE_ENDPOINT_URL"),
            "bucket_name": env("STORAGE_BUCKET"),
            "access_key": env("STORAGE_ACCESS_KEY"),
            "secret_key": env("STORAGE_SECRET_KEY"),
            "region_name": env("STORAGE_REGION"),
            # El bucket es privado (regla 10): sin ACL pública, y cada descarga
            # pide una URL firmada que vence a los 5 minutos.
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 300,
            # Supabase no publica un subdominio por bucket: la ruta lleva el
            # nombre del bucket en vez del estilo bucket.host.
            "addressing_style": "path",
            "signature_version": "s3v4",
            # El nombre del archivo ya es un uuid (regla 8); si se repitiera,
            # es mejor fallar que pisar el de otro.
            "file_overwrite": False,
        },
    }


# ---------- API (Django REST Framework) ----------

REST_FRAMEWORK = {
    # Solo JWT. Se declara explícitamente para no heredar el valor por defecto
    # de DRF, que activaría autenticación por sesión y básica.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # Cerrado por defecto: todo endpoint exige autenticación salvo que diga
    # explícitamente lo contrario (como /health/). Olvidar un permiso deja el
    # endpoint cerrado, no abierto.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # Paginación obligatoria en todo listado, de 25 en 25 (arquitectura.md §4).
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    # Los listados se filtran con la clase filterset_class que declara cada
    # vista (filters.py de cada app).
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    # Toda respuesta de error sale en el formato uniforme.
    "EXCEPTION_HANDLER": "apps.core.manejador_errores.manejar_excepcion",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Límite de peticiones por IP (arquitectura.md §9). Solo lo usan las vistas
    # que declaran su throttle_scope. Login y renovación tienen límites
    # separados: detrás de una misma IP pública (la red de la universidad en la
    # defensa) entran varias personas a la vez, y renovar el token no debe
    # gastar los intentos de login de nadie (spec 001, §5).
    "DEFAULT_THROTTLE_RATES": {
        "login": "30/min",
        "agente": "10/min",
        "renovacion": "60/min",
    },
    # Cuántos proxies propios hay delante de Django. Define qué IP es la real:
    # 0 (desarrollo) ignora X-Forwarded-For, que cualquier cliente puede
    # inventar; en producción (Render) hay tres y se configura NUM_PROXIES=3
    # (spec 002, §8).
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_TOKEN_MINUTES", default=30)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_DAYS", default=7)
    ),
    # El último acceso lo actualiza registrar_acceso de forma explícita, junto
    # con su registro de auditoría (spec 001, §6).
    "UPDATE_LAST_LOGIN": False,
}


# ---------- Caché ----------

# En PostgreSQL y no en memoria: la usa el límite de peticiones, y en
# producción gunicorn corre varios procesos. Con caché en memoria cada proceso
# contaría por separado y el límite real se multiplicaría. La tabla la crea la
# migración core.0002, así que basta con correr migrate.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_django",
    }
}

# Documentación automática en /api/docs/.
SPECTACULAR_SETTINGS = {
    "TITLE": "API Inmobiliaria",
    "DESCRIPTION": "ERP inmobiliario: proyecto final de Programación Comercial.",
    "VERSION": "1.0.0",
    # El esquema se sirve en /api/schema/; no hace falta repetirlo dentro de sí.
    "SERVE_INCLUDE_SCHEMA": False,
    # Nombre de los conjuntos de opciones que aparecen en más de un campo.
    "ENUM_NAME_OVERRIDES": {
        "EstadoSaludEnum": "apps.core.serializers.ESTADOS_SALUD",
        "EstadoPropiedadEnum": "apps.catalogo.enums.EstadoPropiedad",
        "TipoDocumentoEnum": "apps.catalogo.enums.TipoDocumento",
        "TipoClienteEnum": "apps.crm.enums.TipoCliente",
        "TipoProveedorEnum": "apps.compras.enums.TipoProveedor",
        "EstadoCotizacionEnum": "apps.crm.enums.EstadoCotizacion",
        "EstadoContratoEnum": "apps.ventas.enums.EstadoContrato",
        "EstadoCuotaEnum": "apps.ventas.enums.EstadoCuota",
        "EstadoArrendamientoEnum": "apps.arrendamientos.enums.EstadoArrendamiento",
        "EstadoPagoRentaEnum": "apps.arrendamientos.enums.EstadoPagoRenta",
        "TipoDocumentoRAGEnum": "apps.ia.enums.TipoDocumentoRAG",
        "EstadoIndexacionEnum": "apps.ia.enums.EstadoIndexacion",
        "EstadoContratoCompraEnum": "apps.compras.enums.EstadoContratoCompra",
        "EstadoProyectoEnum": "apps.construccion.enums.EstadoProyecto",
        "TipoPagoConstructoraEnum": "apps.construccion.enums.TipoPagoConstructora",
        "EstadoPagoConstructoraEnum": "apps.construccion.enums.EstadoPago",
    },
}


# ---------- CORS ----------

# Solo el frontend puede llamar a la API desde un navegador
# (arquitectura.md §9). Vacío por defecto: ningún otro origen.
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
# Permite al frontend leer el nombre de las descargas autenticadas (spec 016).
CORS_EXPOSE_HEADERS = ["Content-Disposition"]


# ---------- Celery (spec 002, §5.5) ----------

# RabbitMQ como broker. En desarrollo la URL viene del .env (el RabbitMQ de
# docker compose); en producción prod.py la exige sin valor por defecto.
CELERY_BROKER_URL = env("RABBITMQ_URL", default="amqp://localhost:5672//")

# Sin backend de resultados (docs/arquitectura.md §6): nadie consulta lo que
# devuelve una tarea, así que no se guarda.
CELERY_TASK_IGNORE_RESULT = True

CELERY_TIMEZONE = TIME_ZONE

# Ajustes para la cuota gratuita de CloudAMQP (20 conexiones, 1 millón de
# mensajes al mes): una sola conexión reutilizada para publicar, y el worker sin
# eventos de monitoreo, que serían mensajes extra que nadie lee.
CELERY_BROKER_POOL_LIMIT = 1
CELERY_WORKER_SEND_TASK_EVENTS = False

# Si RabbitMQ no está listo cuando arranca el worker, reintenta en lugar de
# terminar: en Render, el contenedor puede despertar antes que la conexión.
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Colas por flujo (arquitectura §6). Las tareas de ia van a "documentos"; las
# demás, como el diagnóstico de core, a la cola por defecto ("celery"). El
# worker debe consumir las dos (scripts/iniciar.sh, spec 020).
CELERY_TASK_ROUTES = {"ia.*": {"queue": "documentos"}}
# ---------- Agente de IA (spec 005) ----------

# La llave es opcional: sin ella el agente responde 503 y el resto del sistema
# funciona igual. Así nadie necesita una llave de Gemini para correr las
# pruebas, que usan un proveedor falso.
IA_PROVEEDOR = env("IA_PROVEEDOR", default="gemini")
IA_API_KEY = env("IA_API_KEY", default="")
IA_MODELO = env("IA_MODELO", default="gemini-3.5-flash-lite")
IA_MODELO_EMBEDDINGS = env("IA_MODELO_EMBEDDINGS", default="gemini-embedding-001")
# Debe coincidir con DIMENSION_EMBEDDINGS de apps/ia/models.py.
IA_DIMENSION_EMBEDDINGS = env.int("IA_DIMENSION_EMBEDDINGS", default=768)
IA_MAX_TOKENS_RESPUESTA = env.int("IA_MAX_TOKENS_RESPUESTA", default=1024)
# Distancia de coseno máxima para usar un fragmento (0 = mismo significado).
# 0.42: en la prueba real del 2026-10-31 las preguntas relevantes quedaron
# entre 0.19 y 0.38 y las ajenas desde 0.47.
IA_DISTANCIA_MAXIMA = env.float("IA_DISTANCIA_MAXIMA", default=0.42)
# Precio en USD por millón de tokens del IA_MODELO, para estimar el costo de
# cada consulta (Serie II, inciso 9). Valores de la API de Gemini para
# gemini-3.5-flash-lite en el plan de pago estándar: 0.30 la entrada y 2.50 la
# salida (la salida incluye los tokens de razonamiento). Si cambia el modelo o
# el precio, se cambian aquí o en el entorno, sin tocar código. Decimal y no
# float: es dinero.
IA_PRECIO_ENTRADA_USD_MILLON = Decimal(
    env("IA_PRECIO_ENTRADA_USD_MILLON", default="0.30")
)
IA_PRECIO_SALIDA_USD_MILLON = Decimal(
    env("IA_PRECIO_SALIDA_USD_MILLON", default="2.50")
)
