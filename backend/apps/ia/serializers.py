"""Serializadores de IA: validan el formato de entrada y arman la salida.

Sin reglas de negocio ni acceso a la base de datos.
"""

from rest_framework import serializers

from apps.core.selectors import listar_paises
from apps.core.serializers import PaisResumenSerializer

from .enums import TipoDocumentoRAG
from .models import DocumentoRAG


class ConsultaAgenteSerializer(serializers.Serializer):
    # Regla 8: entre 3 y 500 caracteres. Los espacios de los extremos no
    # cuentan, así "   " no pasa como pregunta.
    pregunta = serializers.CharField(min_length=3, max_length=500, trim_whitespace=True)


class CitaSerializer(serializers.Serializer):
    numero = serializers.IntegerField()
    documento = serializers.CharField()
    seccion = serializers.CharField()
    tipo = serializers.CharField()
    extracto = serializers.CharField()


class RespuestaAgenteSerializer(serializers.Serializer):
    respuesta = serializers.CharField()
    sin_informacion = serializers.BooleanField()
    citas = CitaSerializer(many=True)
    # Serie II, inciso 9: consumo de la consulta. null = desconocido.
    tokens_entrada = serializers.IntegerField(allow_null=True)
    tokens_salida = serializers.IntegerField(allow_null=True)
    # Texto decimal exacto ("0.001080"), como los montos del resto de la API.
    costo_estimado_usd = serializers.DecimalField(
        max_digits=12, decimal_places=6, allow_null=True
    )


class DocumentoAgenteSerializer(serializers.ModelSerializer):
    """Un documento del agente en la lista y el detalle (spec 020, §5). Sin el
    texto completo: ninguna pantalla lo necesita."""

    pais = PaisResumenSerializer(allow_null=True)
    # Lo anota listar_documentos_rag: los de la última versión indexada.
    fragmentos = serializers.IntegerField(source="cantidad_fragmentos")

    class Meta:
        model = DocumentoRAG
        fields = [
            "id",
            "titulo",
            "tipo",
            "pais",
            "version",
            "estado_indexacion",
            "error_indexacion",
            "fecha_indexacion",
            "fragmentos",
            "actualizado_en",
        ]
        read_only_fields = fields


class SubirDocumentoAgenteSerializer(serializers.Serializer):
    """Entrada de la subida: multipart con el .md y sus datos (regla 1). El
    contenido lo revisa el servicio."""

    archivo = serializers.FileField()
    titulo = serializers.CharField(max_length=200)
    tipo = serializers.ChoiceField(choices=TipoDocumentoRAG.choices)
    # Vacío si aplica a todos los países.
    pais = serializers.PrimaryKeyRelatedField(
        queryset=listar_paises(), required=False, allow_null=True
    )


class ReemplazarDocumentoAgenteSerializer(serializers.Serializer):
    """Regla 2: solo el archivo. Título, tipo y país no cambian."""

    archivo = serializers.FileField()
