"""Vistas de IA: reciben la petición, delegan en un servicio o selector y
devuelven la respuesta.

Sin reglas de negocio ni consultas directas a los modelos.
"""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.generics import (
    GenericAPIView,
    ListCreateAPIView,
    RetrieveDestroyAPIView,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.http import obtener_ip_cliente
from apps.usuarios.enums import NombreRol
from apps.usuarios.permissions import TieneRol

from .filters import DocumentoRAGFilter
from .selectors import listar_documentos_rag
from .serializers import (
    ConsultaAgenteSerializer,
    DocumentoAgenteSerializer,
    ReemplazarDocumentoAgenteSerializer,
    RespuestaAgenteSerializer,
    SubirDocumentoAgenteSerializer,
)
from .services import (
    desactivar_documento_rag,
    reemplazar_documento_rag,
    reindexar_documento_rag,
    responder_consulta_publica,
    subir_documento_rag,
)

# Spec 020, regla 14: los mismos roles leen y escriben. Se declaran también
# para GET: sin eso, TieneRol dejaría leer a cualquier usuario autenticado.
ADMINISTRACION_Y_GERENCIA = [NombreRol.ADMINISTRADOR, NombreRol.GERENTE]
TODOS_LOS_METODOS = {
    metodo: ADMINISTRACION_Y_GERENCIA for metodo in ("GET", "POST", "PATCH", "DELETE")
}


class ConsultaAgenteView(APIView):
    """POST /api/v1/agente/consultas/: el agente público (spec 005, §5).

    Público a propósito: lo usa cualquier visitante del sitio. Por eso lleva
    límite de peticiones por IP, que además protege la cuota de Gemini.
    """

    # Sin autenticación: un token vencido de un usuario no debe convertir una
    # consulta pública en un 401.
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agente"

    @extend_schema(
        request=ConsultaAgenteSerializer,
        responses=RespuestaAgenteSerializer,
        summary="Preguntar al agente de IA",
    )
    def post(self, request):
        entrada = ConsultaAgenteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        resultado = responder_consulta_publica(
            pregunta=entrada.validated_data["pregunta"],
            ip=obtener_ip_cliente(request),
        )
        return Response(RespuestaAgenteSerializer(resultado).data)


def _respuesta(documento_id: int, *, status: int = 200) -> Response:
    """El documento vuelto a leer con el selector, que anota sus fragmentos."""
    documento = listar_documentos_rag().get(pk=documento_id)
    return Response(DocumentoAgenteSerializer(documento).data, status=status)


class DocumentosAgenteView(ListCreateAPIView):
    """GET y POST /api/v1/documentos-agente/ (spec 020). POST multipart: sube un
    .md y encola su indexación; responde 201 con el documento PENDIENTE."""

    serializer_class = DocumentoAgenteSerializer
    filterset_class = DocumentoRAGFilter
    permission_classes = [TieneRol]
    roles_por_metodo = TODOS_LOS_METODOS

    def get_queryset(self):
        return listar_documentos_rag()

    @extend_schema(
        request={"multipart/form-data": SubirDocumentoAgenteSerializer},
        responses={201: DocumentoAgenteSerializer},
        summary="Subir un documento del agente",
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        entrada = SubirDocumentoAgenteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        documento = subir_documento_rag(
            archivo=datos["archivo"],
            titulo=datos["titulo"],
            tipo=datos["tipo"],
            pais=datos.get("pais"),
            autor=request.user,
            ip=obtener_ip_cliente(request),
        )
        return _respuesta(documento.id, status=201)


class DocumentoAgenteDetalleView(RetrieveDestroyAPIView):
    """GET, PATCH y DELETE /api/v1/documentos-agente/{id}/. PATCH multipart
    reemplaza el archivo (regla 2); DELETE desactiva (regla 13)."""

    serializer_class = DocumentoAgenteSerializer
    permission_classes = [TieneRol]
    roles_por_metodo = TODOS_LOS_METODOS
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return listar_documentos_rag()

    @extend_schema(
        request={"multipart/form-data": ReemplazarDocumentoAgenteSerializer},
        responses={200: DocumentoAgenteSerializer},
        summary="Reemplazar el archivo de un documento del agente",
    )
    def patch(self, request: Request, *args, **kwargs) -> Response:
        documento = self.get_object()
        entrada = ReemplazarDocumentoAgenteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        reemplazar_documento_rag(
            documento=documento,
            archivo=entrada.validated_data["archivo"],
            autor=request.user,
            ip=obtener_ip_cliente(request),
        )
        return _respuesta(documento.id)

    def perform_destroy(self, instance):
        desactivar_documento_rag(
            documento=instance,
            autor=self.request.user,
            ip=obtener_ip_cliente(self.request),
        )


class ReindexarDocumentoAgenteView(GenericAPIView):
    """POST /api/v1/documentos-agente/{id}/reindexar/ (regla 12). 202: solo
    encola, la indexación la hace el worker."""

    serializer_class = DocumentoAgenteSerializer
    permission_classes = [TieneRol]
    roles_por_metodo = {"POST": ADMINISTRACION_Y_GERENCIA}

    def get_queryset(self):
        return listar_documentos_rag()

    @extend_schema(
        request=None,
        responses={202: DocumentoAgenteSerializer},
        summary="Volver a encolar la indexación de un documento",
    )
    def post(self, request: Request, pk: int) -> Response:
        documento = get_object_or_404(self.get_queryset(), pk=pk)
        reindexar_documento_rag(
            documento=documento,
            autor=request.user,
            ip=obtener_ip_cliente(request),
        )
        return _respuesta(documento.id, status=202)
