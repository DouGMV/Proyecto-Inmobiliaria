"""Pruebas de los documentos de demostración y su comando (spec 005, §6)."""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.ia.datos_demo import DOCUMENTOS_DEMO
from apps.ia.models import DocumentoRAG, FragmentoRAG
from apps.ia.services import (
    actualizar_contenido_documento,
    responder_consulta_publica,
)

from .proveedor_falso import vector_eje

pytestmark = pytest.mark.django_db


def correr_comando() -> str:
    salida = StringIO()
    call_command("cargar_demo_ia", stdout=salida, stderr=salida)
    return salida.getvalue()


def test_con_llave_carga_e_indexa_los_cinco_documentos(settings, proveedor_falso):
    settings.IA_API_KEY = "clave-de-prueba"

    salida = correr_comando()

    assert DocumentoRAG.objects.count() == len(DOCUMENTOS_DEMO) == 5
    assert not DocumentoRAG.objects.filter(fecha_indexacion__isnull=True).exists()
    assert FragmentoRAG.objects.count() > 5
    assert "indexados: 5" in salida


def test_correrlo_dos_veces_no_duplica_ni_llama_a_gemini(settings, proveedor_falso):
    settings.IA_API_KEY = "clave-de-prueba"
    correr_comando()
    fragmentos = FragmentoRAG.objects.count()
    llamadas = len(proveedor_falso.llamadas_embeddings)

    salida = correr_comando()

    assert DocumentoRAG.objects.count() == 5
    assert FragmentoRAG.objects.count() == fragmentos
    assert len(proveedor_falso.llamadas_embeddings) == llamadas
    assert "creados: 0" in salida
    assert "indexados: 0" in salida


def test_un_documento_que_cambio_se_actualiza_y_se_reindexa_solo(
    settings, proveedor_falso
):
    settings.IA_API_KEY = "clave-de-prueba"
    correr_comando()
    # Simula que el archivo del repositorio cambió: la base tiene otro texto.
    documento = DocumentoRAG.objects.get(titulo="Manual de procesos de venta")
    documento.contenido_fuente = "## Texto viejo\nX"
    documento.save()

    salida = correr_comando()

    assert "actualizados: 1" in salida
    assert "indexados: 1" in salida
    documento.refresh_from_db()
    assert documento.version == 2


def test_sin_llave_carga_los_documentos_sin_indexar(settings, proveedor_falso):
    settings.IA_API_KEY = ""

    salida = correr_comando()

    assert DocumentoRAG.objects.count() == 5
    assert FragmentoRAG.objects.count() == 0
    assert proveedor_falso.llamadas_embeddings == []
    assert "IA_API_KEY no está configurada" in salida


def test_si_gemini_falla_el_comando_termina_sin_error(settings, proveedor_falso):
    settings.IA_API_KEY = "clave-de-prueba"
    proveedor_falso.falla = True

    salida = correr_comando()

    assert "No se pudo indexar con Gemini" in salida
    # Lo que quedó sin indexar se indexa la próxima vez.
    proveedor_falso.falla = False
    assert "indexados: 5" in correr_comando()


def test_si_un_documento_cambia_mientras_se_indexa_el_comando_no_falla(
    settings, proveedor_falso
):
    settings.IA_API_KEY = "clave-de-prueba"
    correr_comando()
    documento = DocumentoRAG.objects.get(titulo="Manual de procesos de venta")
    documento.contenido_fuente = "## Texto viejo\nX"
    documento.save()

    def otro_cambio():
        actualizar_contenido_documento(
            documento=DocumentoRAG.objects.get(pk=documento.pk),
            contenido_fuente="## Cambio concurrente\nY",
        )

    proveedor_falso.mientras_genera = otro_cambio

    salida = correr_comando()

    assert "No se indexó" in salida


class _VectoresPorSeccion(dict):
    """Da el mismo eje a la sección "Mascotas" de la política de
    arrendamientos y a la pregunta; el resto recibe el vector fijo del
    proveedor falso, que queda lejos de ese eje (distancia ~0.96 > 0.42)."""

    def get(self, texto, por_defecto=None):
        if texto.startswith("Política de arrendamientos · Mascotas") or (
            texto == "¿Aceptan mascotas en las casas rentadas?"
        ):
            return vector_eje(7)
        return por_defecto


def test_el_agente_cita_la_politica_de_arrendamientos(settings, proveedor_falso):
    """Serie II, inciso 4: el documento nuevo se ingiere con el comando de demo
    y la respuesta del agente lo cita como fuente."""
    settings.IA_API_KEY = "clave-de-prueba"
    proveedor_falso.vectores = _VectoresPorSeccion()
    correr_comando()

    documento = DocumentoRAG.objects.get(titulo="Política de arrendamientos")
    assert documento.tipo == "POLITICA"
    assert documento.fragmentos.filter(seccion="Mascotas").exists()

    resultado = responder_consulta_publica(
        pregunta="¿Aceptan mascotas en las casas rentadas?"
    )

    assert resultado.sin_informacion is False
    assert [(c.documento, c.seccion) for c in resultado.citas] == [
        ("Política de arrendamientos", "Mascotas")
    ]
