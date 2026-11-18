"""Selectores de IA: consultas, filtros y agregaciones.

Nunca escriben en la base de datos.
"""

from django.db.models import Count, QuerySet
from pgvector.django import CosineDistance

from apps.catalogo.selectors import listar_propiedades, listar_unidades

from .models import DocumentoRAG, FragmentoRAG


def contar_inventario_disponible() -> dict[str, int]:
    """Bienes disponibles activos, sin contar edificios junto con sus unidades."""
    propiedades = (
        listar_propiedades()
        .filter(estado="DISPONIBLE", tipo__requiere_unidades=False)
        .count()
    )
    unidades = (
        listar_unidades()
        .filter(estado="DISPONIBLE", propiedad__tipo__requiere_unidades=True)
        .count()
    )
    return {
        "propiedades": propiedades,
        "unidades": unidades,
        "total": propiedades + unidades,
    }


def obtener_documento(*, documento_id: int) -> DocumentoRAG:
    """Lanza DocumentoRAG.DoesNotExist si no existe."""
    return DocumentoRAG.objects.get(pk=documento_id)


def obtener_documento_por_titulo(*, titulo: str) -> DocumentoRAG | None:
    return DocumentoRAG.objects.filter(titulo=titulo).first()


def buscar_fragmentos_similares(
    *, embedding: list[float], distancia_maxima: float, limite: int = 5
) -> list[FragmentoRAG]:
    """Los fragmentos más cercanos a la pregunta, del más al menos cercano.

    Solo de documentos activos (regla 4) y solo los que no pasan de
    distancia_maxima. La distancia de coseno va de 0 (mismo significado) a 2
    (opuesto); queda anotada en cada fragmento como .distancia.
    """
    return list(
        FragmentoRAG.objects.filter(documento__activo=True)
        .annotate(distancia=CosineDistance("embedding", embedding))
        .filter(distancia__lte=distancia_maxima)
        .select_related("documento")
        .order_by("distancia")[:limite]
    )


def listar_documentos_rag() -> QuerySet[DocumentoRAG]:
    """Los documentos activos del agente, por título, con cuántos fragmentos
    tiene cada uno en la base (spec 020, §5). El conteo va en la misma
    consulta, para no hacer una por documento."""
    return (
        DocumentoRAG.objects.filter(activo=True)
        .select_related("pais")
        .annotate(cantidad_fragmentos=Count("fragmentos"))
        .order_by("titulo", "id")
    )
