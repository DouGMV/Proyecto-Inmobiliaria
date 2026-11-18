"""Pruebas del endpoint público del agente (spec 005, §5)."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.auditoria.models import LogAgenteIA
from apps.ia.models import DocumentoRAG, FragmentoRAG

from .proveedor_falso import vector_eje

pytestmark = pytest.mark.django_db

URL = "/api/v1/agente/consultas/"
PREGUNTA = "¿Cuánto dura una reserva?"


@pytest.fixture(autouse=True)
def limpiar_limite_de_peticiones():
    # El límite cuenta en la caché: sin limpiarla, una prueba heredaría las
    # peticiones de la anterior.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def cliente():
    return APIClient()


@pytest.fixture
def fragmento_reservas():
    documento = DocumentoRAG.objects.create(
        titulo="Política comercial", tipo="POLITICA", contenido_fuente="## A\nB"
    )
    return FragmentoRAG.objects.create(
        documento=documento,
        orden=0,
        seccion="Reservas",
        contenido="La reserva tiene una vigencia de 15 días.",
        tokens=10,
        embedding=vector_eje(0),
    )


def test_responde_con_citas_sin_token(cliente, proveedor_falso, fragmento_reservas):
    proveedor_falso.vectores[PREGUNTA] = vector_eje(0)

    respuesta = cliente.post(URL, {"pregunta": PREGUNTA}, format="json")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["sin_informacion"] is False
    assert datos["respuesta"] == "Respuesta de prueba [1]."
    assert datos["citas"] == [
        {
            "numero": 1,
            "documento": "Política comercial",
            "seccion": "Reservas",
            "tipo": "POLITICA",
            "extracto": "La reserva tiene una vigencia de 15 días.",
        }
    ]


def test_un_token_invalido_no_impide_consultar(
    cliente, proveedor_falso, fragmento_reservas
):
    cliente.credentials(HTTP_AUTHORIZATION="Bearer token-vencido")

    respuesta = cliente.post(URL, {"pregunta": PREGUNTA}, format="json")

    assert respuesta.status_code == 200


def test_sin_informacion_responde_200_con_la_marca(cliente, proveedor_falso):
    respuesta = cliente.post(URL, {"pregunta": PREGUNTA}, format="json")

    assert respuesta.status_code == 200
    assert respuesta.json()["sin_informacion"] is True
    assert respuesta.json()["citas"] == []


@pytest.mark.parametrize("pregunta", ["", "ab", "   ab   ", "x" * 501])
def test_una_pregunta_fuera_de_rango_responde_400(cliente, proveedor_falso, pregunta):
    respuesta = cliente.post(URL, {"pregunta": pregunta}, format="json")

    assert respuesta.status_code == 400
    assert respuesta.json()["error"]["codigo"] == "VALIDACION"
    assert proveedor_falso.llamadas_embeddings == []


def test_si_gemini_falla_responde_503(cliente, proveedor_falso):
    proveedor_falso.falla = True

    respuesta = cliente.post(URL, {"pregunta": PREGUNTA}, format="json")

    assert respuesta.status_code == 503
    assert respuesta.json()["error"]["codigo"] == "AGENTE_NO_DISPONIBLE"


def test_la_peticion_once_en_un_minuto_responde_429(cliente, proveedor_falso):
    for _ in range(10):
        assert (
            cliente.post(URL, {"pregunta": PREGUNTA}, format="json").status_code == 200
        )

    respuesta = cliente.post(URL, {"pregunta": PREGUNTA}, format="json")

    assert respuesta.status_code == 429
    assert respuesta.json()["error"]["codigo"] == "DEMASIADAS_PETICIONES"


def test_solo_acepta_post(cliente):
    assert cliente.get(URL).status_code == 405


def test_la_bitacora_guarda_la_ip_de_quien_pregunta(
    cliente, proveedor_falso, fragmento_reservas
):
    """Serie II, inciso 5: la vista calcula la IP y el servicio la registra."""
    proveedor_falso.vectores[PREGUNTA] = vector_eje(0)

    respuesta = cliente.post(
        URL, {"pregunta": PREGUNTA}, format="json", REMOTE_ADDR="190.56.12.34"
    )

    assert respuesta.status_code == 200
    assert LogAgenteIA.objects.get().ip == "190.56.12.34"


def test_una_consulta_fallida_tambien_guarda_la_ip(cliente, proveedor_falso):
    proveedor_falso.falla = True

    respuesta = cliente.post(
        URL, {"pregunta": PREGUNTA}, format="json", REMOTE_ADDR="190.56.12.34"
    )

    assert respuesta.status_code == 503
    registro = LogAgenteIA.objects.get()
    assert registro.exito is False
    assert registro.ip == "190.56.12.34"
