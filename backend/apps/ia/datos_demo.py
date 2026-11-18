"""Documentos de demostración del agente de IA (spec 005, §6).

Todo su contenido es ficticio: nunca se envían datos personales reales a la API
de Gemini (CLAUDE.md).
"""

from pathlib import Path

from apps.core.models import Pais

from .enums import TipoDocumentoRAG
from .selectors import obtener_documento_por_titulo
from .services import (
    actualizar_contenido_documento,
    crear_documento_rag,
    indexar_documento,
)

CARPETA_DOCUMENTOS = Path(__file__).resolve().parent / "documentos_demo"

# Archivo, título, tipo y código ISO del país (None si aplica a todos).
DOCUMENTOS_DEMO = [
    (
        "manual-visitas-demostracion.md",
        "Manual de visitas de demostración",
        TipoDocumentoRAG.MANUAL,
        None,
    ),
    (
        "politica-comercial.md",
        "Política comercial de la agencia",
        TipoDocumentoRAG.POLITICA,
        None,
    ),
    (
        "manual-procesos-venta.md",
        "Manual de procesos de venta",
        TipoDocumentoRAG.MANUAL,
        None,
    ),
    (
        "requisitos-compraventa-guatemala.md",
        "Requisitos legales de compraventa – Guatemala",
        TipoDocumentoRAG.LEGAL,
        "GTM",
    ),
    (
        "requisitos-compraventa-mexico.md",
        "Requisitos legales de compraventa – México",
        TipoDocumentoRAG.LEGAL,
        "MEX",
    ),
]


def cargar_demo_ia(*, indexar: bool) -> dict[str, int]:
    """Crea los documentos que faltan, actualiza los que cambiaron y, si
    indexar es True, indexa solo los pendientes.

    Es idempotente: corrida dos veces seguidas, la segunda no crea nada ni
    llama a Gemini, porque ningún documento queda pendiente. Un documento está
    pendiente si nunca se indexó o si su texto cambió después de indexarlo.
    """
    resumen = {"creados": 0, "actualizados": 0, "indexados": 0}
    for archivo, titulo, tipo, codigo_pais in DOCUMENTOS_DEMO:
        contenido = (CARPETA_DOCUMENTOS / archivo).read_text(encoding="utf-8")
        documento = obtener_documento_por_titulo(titulo=titulo)
        if documento is None:
            documento = crear_documento_rag(
                titulo=titulo,
                tipo=tipo,
                contenido_fuente=contenido,
                pais=_pais(codigo_pais),
            )
            resumen["creados"] += 1
        elif documento.contenido_fuente != contenido:
            actualizar_contenido_documento(
                documento=documento, contenido_fuente=contenido
            )
            resumen["actualizados"] += 1

        if indexar and documento.fecha_indexacion is None:
            indexar_documento(documento_id=documento.id)
            resumen["indexados"] += 1
    return resumen


def _pais(codigo_iso: str | None) -> Pais | None:
    """El país del documento, si ya existe (lo carga seed_demo). Si no, el
    documento queda sin país, que significa "aplica a todos"."""
    if codigo_iso is None:
        return None
    return Pais.objects.filter(codigo_iso=codigo_iso).first()
