"""Herramienta de inventario: datos del catálogo, ejecución y auditoría."""

import pytest

from apps.auditoria.models import LogAgenteIA
from apps.catalogo.tests.factories import PropiedadFactory, UnidadFactory
from apps.ia.exceptions import AgenteNoDisponible
from apps.ia.proveedores.base import ProveedorIANoDisponible, RespuestaIA
from apps.ia.selectors import contar_inventario_disponible
from apps.ia.services import responder_consulta_publica

pytestmark = pytest.mark.django_db

PREGUNTA = "¿Cuántos bienes disponibles hay actualmente en inventario?"


def test_cuenta_bienes_activos_sin_duplicar_edificios():
    PropiedadFactory(estado="DISPONIBLE")
    unidad = UnidadFactory(estado="DISPONIBLE")
    unidad.propiedad.estado = "DISPONIBLE"
    unidad.propiedad.save()
    PropiedadFactory(estado="VENDIDA")
    PropiedadFactory(estado="DISPONIBLE", activo=False)
    UnidadFactory(estado="DISPONIBLE", activo=False)
    UnidadFactory(estado="DISPONIBLE", propiedad=PropiedadFactory(activo=False))
    assert contar_inventario_disponible() == {
        "propiedades": 1,
        "unidades": 1,
        "total": 2,
    }


def test_inventario_vacio_devuelve_cero():
    assert contar_inventario_disponible() == {
        "propiedades": 0,
        "unidades": 0,
        "total": 0,
    }


def test_el_agente_ejecuta_herramienta_y_registra_resultado(
    proveedor_falso, monkeypatch
):
    PropiedadFactory(estado="DISPONIBLE")

    def generar(*, mensajes, herramientas):
        dato = herramientas[0].ejecutar()
        return RespuestaIA(f"Hay {dato['total']} bien disponible.", "falso", 20, 10)

    monkeypatch.setattr(proveedor_falso, "generar_respuesta", generar)
    respuesta = responder_consulta_publica(pregunta=PREGUNTA, ip="127.0.0.1")
    assert respuesta.respuesta == "Hay 1 bien disponible."
    registro = LogAgenteIA.objects.get()
    assert registro.herramientas_invocadas == [
        {
            "nombre": "contar_inventario_disponible",
            "argumentos": {},
            "resultado": {"propiedades": 1, "unidades": 0, "total": 1},
        }
    ]
    assert registro.ip == "127.0.0.1"
    assert registro.tokens_entrada == 20
    assert proveedor_falso.llamadas_embeddings == []


def test_sin_ejecucion_no_se_acepta_un_conteo_inventado(proveedor_falso):
    with pytest.raises(AgenteNoDisponible):
        responder_consulta_publica(pregunta=PREGUNTA)
    registro = LogAgenteIA.objects.get()
    assert registro.exito is False
    assert registro.herramientas_invocadas == []


def test_fallo_posterior_conserva_la_invocacion(proveedor_falso, monkeypatch):
    def generar(*, mensajes, herramientas):
        herramientas[0].ejecutar()
        raise ProveedorIANoDisponible("Proveedor no disponible")

    monkeypatch.setattr(proveedor_falso, "generar_respuesta", generar)
    with pytest.raises(AgenteNoDisponible):
        responder_consulta_publica(pregunta=PREGUNTA)
    registro = LogAgenteIA.objects.get()
    assert registro.exito is False
    assert registro.herramientas_invocadas[0]["resultado"]["total"] == 0
