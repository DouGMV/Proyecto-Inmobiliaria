"""Pruebas de los documentos de demostración y su comando (spec 005, §6)."""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.ia.datos_demo import DOCUMENTOS_DEMO
from apps.ia.models import DocumentoRAG, FragmentoRAG
from apps.ia.services import actualizar_contenido_documento

pytestmark = pytest.mark.django_db


def correr_comando() -> str:
    salida = StringIO()
    call_command("cargar_demo_ia", stdout=salida, stderr=salida)
    return salida.getvalue()


def test_con_llave_carga_e_indexa_los_documentos(settings, proveedor_falso):
    settings.IA_API_KEY = "clave-de-prueba"

    salida = correr_comando()

    assert DocumentoRAG.objects.count() == len(DOCUMENTOS_DEMO) == 5
    assert DocumentoRAG.objects.filter(
        titulo="Manual de visitas de demostración"
    ).exists()
    assert not DocumentoRAG.objects.filter(fecha_indexacion__isnull=True).exists()
    assert FragmentoRAG.objects.count() > 4
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
