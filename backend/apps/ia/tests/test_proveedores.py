"""Pruebas del proveedor de IA (spec 005, incremento 1).

Ninguna llama a la red: el cliente de Gemini se reemplaza por uno falso y las
esperas entre reintentos se anotan en lugar de dormir.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.ia.proveedores import gemini
from apps.ia.proveedores.base import (
    Herramienta,
    Mensaje,
    ProveedorIANoDisponible,
    RolMensaje,
    TareaEmbedding,
)
from apps.ia.proveedores.fabrica import obtener_proveedor
from apps.ia.proveedores.gemini import ProveedorGemini

DIMENSION = 768


class ModelosFalsos:
    """Imita client.models: devuelve o lanza las respuestas en orden."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def _siguiente(self, kwargs):
        self.llamadas.append(kwargs)
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta(kwargs) if callable(respuesta) else respuesta

    def generate_content(self, **kwargs):
        return self._siguiente(kwargs)

    def embed_content(self, **kwargs):
        return self._siguiente(kwargs)


def crear_proveedor(respuestas):
    modelos = ModelosFalsos(respuestas)
    esperas = []
    proveedor = ProveedorGemini(
        api_key="clave-de-prueba",
        modelo="modelo-de-prueba",
        modelo_embeddings="embeddings-de-prueba",
        dimension_embeddings=DIMENSION,
        max_tokens_respuesta=256,
        cliente=SimpleNamespace(models=modelos),
        dormir=esperas.append,
    )
    return proveedor, modelos, esperas


def respuesta_texto(texto="Hola"):
    return SimpleNamespace(
        text=texto,
        usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=3),
    )


def respuesta_embeddings(kwargs):
    """Un vector por cada texto recibido, como hace Gemini."""
    return SimpleNamespace(
        embeddings=[
            SimpleNamespace(values=[0.1] * DIMENSION) for _ in kwargs["contents"]
        ]
    )


def error_gemini(codigo):
    # Se usa el módulo del proveedor para no importar el SDK fuera de
    # proveedores/, ni siquiera en las pruebas.
    return gemini.errors.APIError(
        codigo, {"error": {"code": codigo, "message": "de prueba", "status": "X"}}
    )


# ---------- Fábrica ----------


def test_la_fabrica_entrega_el_proveedor_de_gemini(settings):
    settings.IA_PROVEEDOR = "gemini"
    settings.IA_API_KEY = "clave-de-prueba"
    assert isinstance(obtener_proveedor(), ProveedorGemini)


def test_sin_llave_el_proveedor_no_esta_disponible(settings):
    settings.IA_API_KEY = ""
    with pytest.raises(ProveedorIANoDisponible):
        obtener_proveedor()


def test_un_proveedor_desconocido_es_un_error_de_configuracion(settings):
    settings.IA_PROVEEDOR = "otro"
    settings.IA_API_KEY = "clave-de-prueba"
    with pytest.raises(ImproperlyConfigured):
        obtener_proveedor()


# ---------- Respuestas ----------


def test_generar_respuesta_separa_las_instrucciones_y_devuelve_los_tokens():
    proveedor, modelos, _ = crear_proveedor([respuesta_texto("Hola")])

    resultado = proveedor.generar_respuesta(
        mensajes=[
            Mensaje(RolMensaje.SISTEMA, "Responde en español."),
            Mensaje(RolMensaje.USUARIO, "Saluda"),
        ]
    )

    assert resultado.texto == "Hola"
    assert resultado.modelo == "modelo-de-prueba"
    assert (resultado.tokens_entrada, resultado.tokens_salida) == (12, 3)
    llamada = modelos.llamadas[0]
    assert llamada["model"] == "modelo-de-prueba"
    assert llamada["config"].system_instruction == "Responde en español."
    assert llamada["config"].max_output_tokens == 256
    assert [c.role for c in llamada["contents"]] == ["user"]


def respuesta_llamada(nombre="contar", argumentos=None):
    llamada = SimpleNamespace(name=nombre, args=argumentos or {})
    return SimpleNamespace(
        function_calls=[llamada],
        candidates=[
            SimpleNamespace(
                content=gemini.types.Content(
                    role="model",
                    parts=[
                        gemini.types.Part.from_function_call(
                            name=nombre, args=argumentos or {}
                        )
                    ],
                )
            )
        ],
        usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=3),
    )


def test_herramienta_envia_resultado_real_al_modelo_y_acumula_tokens():
    proveedor, modelos, _ = crear_proveedor(
        [respuesta_llamada(), respuesta_texto("Hay 2.")]
    )
    ejecuciones = []

    def contar():
        ejecuciones.append(True)
        return {"total": 2}

    resultado = proveedor.generar_respuesta(
        mensajes=[Mensaje(RolMensaje.USUARIO, "Cuenta el inventario")],
        herramientas=[
            Herramienta(
                "contar", "Cuenta bienes", {"type": "object", "properties": {}}, contar
            )
        ],
    )
    assert ejecuciones == [True]
    assert resultado.texto == "Hay 2."
    assert (resultado.tokens_entrada, resultado.tokens_salida) == (24, 6)
    contenido = modelos.llamadas[1]["contents"][-1]
    assert contenido.role == "user"
    assert contenido.parts[0].function_response.response == {"total": 2}


@pytest.mark.parametrize(
    "nombre,argumentos", [("no_autorizada", {}), ("contar", {"extra": 1})]
)
def test_rechaza_herramienta_o_argumentos_no_autorizados(nombre, argumentos):
    proveedor, _, _ = crear_proveedor([respuesta_llamada(nombre, argumentos)])
    ejecuciones = []

    def contar():
        ejecuciones.append(True)
        return {"total": 2}

    with pytest.raises(ProveedorIANoDisponible):
        proveedor.generar_respuesta(
            mensajes=[Mensaje(RolMensaje.USUARIO, "Cuenta")],
            herramientas=[
                Herramienta(
                    "contar", "Cuenta", {"type": "object", "properties": {}}, contar
                )
            ],
        )
    assert ejecuciones == []


def test_limita_los_intercambios_de_herramientas():
    proveedor, modelos, _ = crear_proveedor([respuesta_llamada() for _ in range(3)])
    with pytest.raises(ProveedorIANoDisponible):
        proveedor.generar_respuesta(
            mensajes=[Mensaje(RolMensaje.USUARIO, "Cuenta")],
            herramientas=[
                Herramienta(
                    "contar",
                    "Cuenta",
                    {"type": "object", "properties": {}},
                    lambda: {"total": 0},
                )
            ],
        )
    assert len(modelos.llamadas) == 3


# ---------- Embeddings ----------


def test_un_embedding_pide_la_dimension_y_la_tarea():
    proveedor, modelos, _ = crear_proveedor([respuesta_embeddings])

    vector = proveedor.generar_embedding(
        texto="casa en venta", tarea=TareaEmbedding.CONSULTA
    )

    assert len(vector) == DIMENSION
    configuracion = modelos.llamadas[0]["config"]
    assert configuracion.output_dimensionality == DIMENSION
    assert configuracion.task_type == "RETRIEVAL_QUERY"


def test_los_embeddings_se_piden_en_lotes_de_cien():
    proveedor, modelos, _ = crear_proveedor([respuesta_embeddings] * 3)

    vectores = proveedor.generar_embeddings_lote(
        textos=[f"texto {i}" for i in range(250)], tarea=TareaEmbedding.DOCUMENTO
    )

    assert len(vectores) == 250
    assert [len(llamada["contents"]) for llamada in modelos.llamadas] == [100, 100, 50]
    assert modelos.llamadas[0]["config"].task_type == "RETRIEVAL_DOCUMENT"


def test_sin_textos_no_llama_a_gemini():
    proveedor, modelos, _ = crear_proveedor([])
    assert (
        proveedor.generar_embeddings_lote(textos=[], tarea=TareaEmbedding.DOCUMENTO)
        == []
    )
    assert modelos.llamadas == []


# ---------- Reintentos (regla 9) ----------


@pytest.mark.parametrize("codigo", [429, 500, 503, 504])
def test_un_error_pasajero_se_reintenta_con_espera_creciente(codigo):
    proveedor, modelos, esperas = crear_proveedor(
        [error_gemini(codigo), error_gemini(codigo), respuesta_texto("Ya")]
    )

    resultado = proveedor.generar_respuesta(
        mensajes=[Mensaje(RolMensaje.USUARIO, "Hola")]
    )

    assert resultado.texto == "Ya"
    assert len(modelos.llamadas) == 3
    assert esperas == [1, 2]


@pytest.mark.parametrize(
    "falla_de_red",
    [
        httpx.ConnectError("conexión rechazada"),
        httpx.ReadError("conexión cortada"),
        httpx.RemoteProtocolError("respuesta incompleta"),
    ],
)
def test_una_falla_de_red_se_reintenta(falla_de_red):
    """Observación de la revisión del PR #62: antes daban 500."""
    proveedor, _, esperas = crear_proveedor([falla_de_red, respuesta_texto("Ya")])

    resultado = proveedor.generar_respuesta(
        mensajes=[Mensaje(RolMensaje.USUARIO, "Hola")]
    )

    assert resultado.texto == "Ya"
    assert esperas == [1]


def test_una_falla_de_red_que_no_se_recupera_no_esta_disponible():
    proveedor, _, _ = crear_proveedor([httpx.ConnectError("sin red")] * 3)

    with pytest.raises(ProveedorIANoDisponible):
        proveedor.generar_respuesta(mensajes=[Mensaje(RolMensaje.USUARIO, "Hola")])


def test_sin_metricas_los_tokens_son_desconocidos():
    """None y no 0: el consumo no se conoce (contrato con la spec 015)."""
    sin_uso = SimpleNamespace(text="Hola", usage_metadata=None)
    proveedor, _, _ = crear_proveedor([sin_uso])

    resultado = proveedor.generar_respuesta(
        mensajes=[Mensaje(RolMensaje.USUARIO, "Hola")]
    )

    assert (resultado.tokens_entrada, resultado.tokens_salida) == (None, None)


@pytest.mark.parametrize(
    "embeddings",
    [
        None,
        [],
        [SimpleNamespace(values=None)],
        [SimpleNamespace(values=[])],
    ],
)
def test_una_respuesta_de_embeddings_incompleta_no_esta_disponible(embeddings):
    """Antes daba IndexError o TypeError (500)."""
    proveedor, _, _ = crear_proveedor([SimpleNamespace(embeddings=embeddings)])

    with pytest.raises(ProveedorIANoDisponible):
        proveedor.generar_embedding(texto="casa", tarea=TareaEmbedding.CONSULTA)


def test_menos_vectores_que_textos_no_esta_disponible():
    un_vector = SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1] * DIMENSION)])
    proveedor, _, _ = crear_proveedor([un_vector])

    with pytest.raises(ProveedorIANoDisponible):
        proveedor.generar_embeddings_lote(
            textos=["uno", "dos"], tarea=TareaEmbedding.DOCUMENTO
        )


def test_un_tiempo_agotado_tambien_se_reintenta():
    proveedor, _, esperas = crear_proveedor(
        [httpx.ReadTimeout("sin respuesta"), respuesta_texto("Ya")]
    )
    resultado = proveedor.generar_respuesta(
        mensajes=[Mensaje(RolMensaje.USUARIO, "Hola")]
    )
    assert resultado.texto == "Ya"
    assert esperas == [1]


def test_despues_de_tres_fallos_el_proveedor_no_esta_disponible():
    proveedor, modelos, esperas = crear_proveedor([error_gemini(503)] * 3)

    with pytest.raises(ProveedorIANoDisponible):
        proveedor.generar_respuesta(mensajes=[Mensaje(RolMensaje.USUARIO, "Hola")])

    assert len(modelos.llamadas) == 3
    assert esperas == [1, 2]


def test_un_error_que_no_es_pasajero_no_se_reintenta():
    proveedor, modelos, esperas = crear_proveedor([error_gemini(400)])

    with pytest.raises(ProveedorIANoDisponible):
        proveedor.generar_respuesta(mensajes=[Mensaje(RolMensaje.USUARIO, "Hola")])

    assert len(modelos.llamadas) == 1
    assert esperas == []


# ---------- Regla de CLAUDE.md ----------


def test_el_sdk_de_gemini_solo_se_importa_en_proveedores():
    carpeta_apps = Path(__file__).resolve().parents[2]
    importa_google = re.compile(r"^\s*(from|import)\s+google\b", re.MULTILINE)

    infractores = [
        str(ruta.relative_to(carpeta_apps))
        for ruta in carpeta_apps.rglob("*.py")
        if "proveedores" not in ruta.parts
        and importa_google.search(ruta.read_text(encoding="utf-8"))
    ]

    assert infractores == []
