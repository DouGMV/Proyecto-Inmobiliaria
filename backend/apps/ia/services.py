"""Servicios de IA: escrituras con reglas de negocio, transacciones y
auditoría.

No conocen request ni hablan HTTP.
"""

import re
import time
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from apps.auditoria.enums import AccionAuditoria, ModoAgente
from apps.auditoria.services import registrar_auditoria, registrar_consulta_agente
from apps.core.models import Pais

from . import selectors
from .enums import EstadoIndexacion, TipoDocumentoRAG
from .exceptions import (
    AgenteNoDisponible,
    ArchivoRAGNoPermitido,
    DocumentoModificadoDuranteIndexacion,
    DocumentoRAGDuplicado,
    EmbeddingConDimensionIncorrecta,
)
from .instrucciones import (
    INSTRUCCIONES_SISTEMA,
    MENSAJE_SIN_INFORMACION,
    armar_mensaje_usuario,
)
from .models import DIMENSION_EMBEDDINGS, DocumentoRAG, FragmentoRAG
from .proveedores.base import (
    Mensaje,
    ProveedorIANoDisponible,
    RolMensaje,
    TareaEmbedding,
)
from .proveedores.fabrica import obtener_proveedor
from .troceo import estimar_tokens, trocear_markdown

ENTIDAD_DOCUMENTO = "ia_documento_rag"

# Cuántos fragmentos se le entregan al modelo por pregunta. Cinco de hasta
# 1,500 caracteres son unos 2,000 tokens: suficiente contexto sin gastar de más.
FRAGMENTOS_POR_CONSULTA = 5

# Largo del extracto de cada cita, para que la pantalla muestre la fuente.
LARGO_EXTRACTO = 200

# Marcadores de cita en la respuesta del modelo: [1], [2]...
_MARCADOR_CITA = re.compile(r"\[(\d+)\]")


@dataclass(frozen=True)
class Cita:
    numero: int
    documento: str
    seccion: str
    tipo: str
    extracto: str


@dataclass(frozen=True)
class RespuestaAgente:
    respuesta: str
    sin_informacion: bool
    citas: list[Cita]


def crear_documento_rag(
    *,
    titulo: str,
    tipo: TipoDocumentoRAG,
    contenido_fuente: str,
    pais: Pais | None = None,
    autor: AbstractBaseUser | None = None,
    ip: str | None = None,
) -> DocumentoRAG:
    """Crea el documento sin indexar (PENDIENTE) y lo audita. Indexar es un
    paso aparte."""
    with transaction.atomic():
        if selectors.obtener_documento_por_titulo(titulo=titulo) is not None:
            raise DocumentoRAGDuplicado(titulo)
        documento = DocumentoRAG.objects.create(
            titulo=titulo,
            tipo=tipo,
            contenido_fuente=contenido_fuente,
            pais=pais,
            creado_por=autor,
            actualizado_por=autor,
        )
        registrar_auditoria(
            usuario=autor,
            entidad=ENTIDAD_DOCUMENTO,
            entidad_id=documento.id,
            accion=AccionAuditoria.CREAR,
            valores_nuevos={
                "titulo": titulo,
                "tipo": tipo,
                "pais": pais.nombre if pais else None,
                "version": documento.version,
            },
            ip=ip,
        )
    return documento


def actualizar_contenido_documento(
    *,
    documento: DocumentoRAG,
    contenido_fuente: str,
    autor: AbstractBaseUser | None = None,
    ip: str | None = None,
) -> DocumentoRAG:
    """Si el texto cambió, sube la versión y lo audita. Si no, no hace nada.

    No reindexa: quien llama decide cuándo, porque indexar llama a la red.
    Sí borra la fecha de indexación y deja el documento PENDIENTE (spec 020,
    regla 11): los fragmentos ya no corresponden al texto.

    Compara y calcula la versión sobre la fila recién bloqueada, no sobre el
    objeto recibido: si ese objeto es antiguo, su versión ya no es la de la
    base y repetiría un número que la indexación usa para detectar cambios
    (revisión del PR #62). El objeto recibido se actualiza con el resultado.
    """
    with transaction.atomic():
        # Bloquea la fila: si una indexación está guardando en este momento,
        # espera a que termine y lee la versión que dejó.
        actual = DocumentoRAG.objects.select_for_update().get(pk=documento.pk)
        if actual.contenido_fuente != contenido_fuente:
            version_anterior = actual.version
            actual.contenido_fuente = contenido_fuente
            actual.version = version_anterior + 1
            actual.fecha_indexacion = None
            actual.estado_indexacion = EstadoIndexacion.PENDIENTE
            actual.error_indexacion = ""
            actual.actualizado_por = autor
            actual.save(
                update_fields=[
                    "contenido_fuente",
                    "version",
                    "fecha_indexacion",
                    "estado_indexacion",
                    "error_indexacion",
                    "actualizado_por",
                    "actualizado_en",
                ]
            )
            registrar_auditoria(
                usuario=autor,
                entidad=ENTIDAD_DOCUMENTO,
                entidad_id=actual.id,
                accion=AccionAuditoria.ACTUALIZAR,
                valores_anteriores={"version": version_anterior},
                valores_nuevos={"version": actual.version},
                ip=ip,
            )

    # Quien llamó sigue usando su objeto (cargar_demo_ia revisa después su
    # fecha de indexación): se deja igual a la fila guardada.
    for campo in (
        "contenido_fuente",
        "version",
        "fecha_indexacion",
        "estado_indexacion",
        "error_indexacion",
    ):
        setattr(documento, campo, getattr(actual, campo))
    return actual


def indexar_documento(*, documento_id: int) -> int:
    """Trocea el documento, pide los vectores y reemplaza sus fragmentos.

    Devuelve cuántos fragmentos quedaron. Recibe solo un id para que la tarea
    de Celery de la ingesta por cola (#25) la pueda llamar tal cual.

    Los vectores se piden ANTES de abrir la transacción: es una llamada de red
    que puede tardar segundos y no debe mantener filas bloqueadas. Si el
    proveedor falla, se lanza ProveedorIANoDisponible y los fragmentos
    anteriores quedan intactos (regla 7).

    Como los vectores se piden fuera de la transacción, el texto puede cambiar
    mientras llegan. Por eso se anota la versión leída y, ya con la fila
    bloqueada, se compara con la actual: si cambió, no se guarda nada y se
    lanza DocumentoModificadoDuranteIndexacion (revisión del PR #62).
    """
    documento = selectors.obtener_documento(documento_id=documento_id)
    version_leida = documento.version
    trozos = trocear_markdown(documento.contenido_fuente)

    vectores: list[list[float]] = []
    if trozos:
        # Se vectoriza con el título y la sección delante: "Requisitos ·
        # Documentos del comprador" ayuda a encontrar un párrafo que por sí
        # solo no menciona de qué trata. En la base se guarda solo el texto.
        vectores = obtener_proveedor().generar_embeddings_lote(
            textos=[
                f"{documento.titulo} · {t.seccion}\n\n{t.contenido}" for t in trozos
            ],
            tarea=TareaEmbedding.DOCUMENTO,
        )
    _verificar_vectores(vectores, cantidad=len(trozos))

    with transaction.atomic():
        documento = DocumentoRAG.objects.select_for_update().get(pk=documento_id)
        if documento.version != version_leida:
            raise DocumentoModificadoDuranteIndexacion(
                f"El documento {documento.titulo!r} pasó de la versión "
                f"{version_leida} a la {documento.version} mientras se indexaba."
            )
        fragmentos_anteriores = documento.fragmentos.count()
        documento.fragmentos.all().delete()
        FragmentoRAG.objects.bulk_create(
            FragmentoRAG(
                documento=documento,
                orden=orden,
                seccion=trozo.seccion[:255],
                contenido=trozo.contenido,
                tokens=estimar_tokens(trozo.contenido),
                embedding=vector,
            )
            for orden, (trozo, vector) in enumerate(zip(trozos, vectores, strict=True))
        )
        documento.fecha_indexacion = timezone.now()
        # Spec 020, §6: la única línea que la cola le agrega a la indexación.
        documento.estado_indexacion = EstadoIndexacion.INDEXADO
        documento.error_indexacion = ""
        documento.save(
            update_fields=[
                "fecha_indexacion",
                "estado_indexacion",
                "error_indexacion",
                "actualizado_en",
            ]
        )
        registrar_auditoria(
            usuario=None,
            entidad=ENTIDAD_DOCUMENTO,
            entidad_id=documento.id,
            accion=AccionAuditoria.ACTUALIZAR,
            valores_anteriores={"fragmentos": fragmentos_anteriores},
            valores_nuevos={"fragmentos": len(trozos), "version": documento.version},
        )
    return len(trozos)


def _verificar_vectores(vectores: list[list[float]], *, cantidad: int) -> None:
    if len(vectores) != cantidad:
        raise EmbeddingConDimensionIncorrecta(
            f"Se pidieron {cantidad} vectores y el proveedor devolvió {len(vectores)}."
        )
    for vector in vectores:
        if len(vector) != DIMENSION_EMBEDDINGS:
            raise EmbeddingConDimensionIncorrecta(
                f"El proveedor devolvió vectores de {len(vector)} valores y el "
                f"campo guarda {DIMENSION_EMBEDDINGS}. Revise IA_DIMENSION_EMBEDDINGS."
            )


# ---------- Ingesta por la cola (spec 020) ----------

# Regla 1: unas 50 páginas de texto. Acota también los vectores que se piden a
# Gemini por documento.
TAMANO_MAXIMO_MARKDOWN = 200 * 1024


def _leer_markdown(archivo) -> str:
    """Regla 1: un .md en UTF-8, no vacío y de hasta 200 KB."""
    if not archivo.name.lower().endswith(".md"):
        raise ArchivoRAGNoPermitido(motivo="Solo se aceptan archivos Markdown (.md).")
    if archivo.size > TAMANO_MAXIMO_MARKDOWN:
        raise ArchivoRAGNoPermitido(motivo="El archivo pesa más de 200 KB.")
    try:
        texto = archivo.read().decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArchivoRAGNoPermitido(
            motivo="El archivo no es texto en UTF-8."
        ) from error
    if not texto.strip():
        raise ArchivoRAGNoPermitido(motivo="El archivo está vacío.")
    return texto


def encolar_indexacion(*, documento_id: int) -> None:
    """Encola la indexación cuando la transacción se confirme (regla 4).

    Si se encolara antes del commit, el worker podría buscar un documento que
    todavía no existe en la base; y si la transacción se revierte, no queda un
    mensaje huérfano. Fuera de una transacción, on_commit encola de inmediato.

    La tarea se importa aquí y no arriba: tasks.py importa este módulo, y
    importarla arriba haría un ciclo.
    """
    from .tasks import indexar_documento_tarea

    transaction.on_commit(lambda: indexar_documento_tarea.delay(documento_id))


def subir_documento_rag(
    *,
    archivo,
    titulo: str,
    tipo: TipoDocumentoRAG,
    pais: Pais | None,
    autor: AbstractBaseUser,
    ip: str | None,
) -> DocumentoRAG:
    """Regla 1 y 4: crea el documento PENDIENTE desde un .md y encola su
    indexación. La API responde sin esperar a Gemini."""
    contenido = _leer_markdown(archivo)
    with transaction.atomic():
        documento = crear_documento_rag(
            titulo=titulo,
            tipo=tipo,
            contenido_fuente=contenido,
            pais=pais,
            autor=autor,
            ip=ip,
        )
        encolar_indexacion(documento_id=documento.id)
    return documento


def reemplazar_documento_rag(
    *, documento: DocumentoRAG, archivo, autor: AbstractBaseUser, ip: str | None
) -> DocumentoRAG:
    """Regla 2: con otro texto, sube la versión y encola. Con el mismo texto
    no cambia nada ni encola: no hay nada nuevo que indexar."""
    contenido = _leer_markdown(archivo)
    with transaction.atomic():
        version_anterior = documento.version
        actual = actualizar_contenido_documento(
            documento=documento, contenido_fuente=contenido, autor=autor, ip=ip
        )
        if actual.version != version_anterior:
            encolar_indexacion(documento_id=actual.id)
    return actual


@transaction.atomic
def reindexar_documento_rag(
    *, documento: DocumentoRAG, autor: AbstractBaseUser, ip: str | None
) -> DocumentoRAG:
    """Regla 12: vuelve a encolar el documento en cualquier estado.

    Un PENDIENTE puede no tener mensaje en la cola (cargar_demo_ia sin
    IA_API_KEY); si lo tiene, se indexa dos veces, y eso es seguro porque
    indexar reemplaza los fragmentos (regla 10).
    """
    actual = DocumentoRAG.objects.select_for_update().get(pk=documento.pk)
    estado_anterior = actual.estado_indexacion
    actual.estado_indexacion = EstadoIndexacion.PENDIENTE
    actual.error_indexacion = ""
    actual.actualizado_por = autor
    actual.save(
        update_fields=[
            "estado_indexacion",
            "error_indexacion",
            "actualizado_por",
            "actualizado_en",
        ]
    )
    registrar_auditoria(
        usuario=autor,
        entidad=ENTIDAD_DOCUMENTO,
        entidad_id=actual.id,
        accion=AccionAuditoria.ACTUALIZAR,
        valores_anteriores={"estado_indexacion": estado_anterior},
        valores_nuevos={"estado_indexacion": EstadoIndexacion.PENDIENTE},
        ip=ip,
    )
    encolar_indexacion(documento_id=actual.id)
    return actual


@transaction.atomic
def desactivar_documento_rag(
    *, documento: DocumentoRAG, autor: AbstractBaseUser, ip: str | None
) -> None:
    """Regla 13: lo saca de las respuestas sin borrar sus fragmentos."""
    documento.activo = False
    documento.actualizado_por = autor
    documento.save(update_fields=["activo", "actualizado_por", "actualizado_en"])
    registrar_auditoria(
        usuario=autor,
        entidad=ENTIDAD_DOCUMENTO,
        entidad_id=documento.id,
        accion=AccionAuditoria.ELIMINAR,
        valores_anteriores={"activo": True},
        valores_nuevos={"activo": False},
        ip=ip,
    )


@transaction.atomic
def marcar_error_indexacion(*, documento_id: int, motivo: str) -> None:
    """Regla 7: la cola agotó los reintentos. El documento queda en ERROR con
    el motivo y conserva los fragmentos que tenía. Lo audita la cola (usuario
    None), como la indexación (§7).

    El motivo lo arma el proveedor (código HTTP, intentos): no lleva la llave
    ni texto del documento.
    """
    documento = DocumentoRAG.objects.select_for_update().get(pk=documento_id)
    documento.estado_indexacion = EstadoIndexacion.ERROR
    documento.error_indexacion = motivo[:255]
    documento.save(
        update_fields=["estado_indexacion", "error_indexacion", "actualizado_en"]
    )
    registrar_auditoria(
        usuario=None,
        entidad=ENTIDAD_DOCUMENTO,
        entidad_id=documento.id,
        accion=AccionAuditoria.ACTUALIZAR,
        valores_nuevos={
            "estado_indexacion": EstadoIndexacion.ERROR,
            "error_indexacion": documento.error_indexacion,
        },
    )


def responder_consulta_publica(
    *, pregunta: str, ip: str | None = None
) -> RespuestaAgente:
    """Responde la pregunta de un visitante con los documentos de la agencia.

    1. Convierte la pregunta en vector y busca los fragmentos más cercanos.
    2. Si ninguno pasa el umbral, responde que no tiene información SIN llamar
       al modelo (regla 3): no gasta cuota ni le da ocasión de inventar.
    3. Si hay fragmentos, se los entrega numerados al modelo con la orden de
       citar [n], y devuelve como citas los fragmentos que el modelo citó.

    Cada consulta, correcta o fallida, queda en la bitácora del agente
    (spec 015) con el contrato acordado en el PR #61: por eso va en services y
    no en selectors. Si Gemini falla, la registra con exito=False y lanza
    AgenteNoDisponible.
    """
    inicio = time.monotonic()
    fragmentos: list[FragmentoRAG] = []
    try:
        proveedor = obtener_proveedor()
        vector = proveedor.generar_embedding(
            texto=pregunta, tarea=TareaEmbedding.CONSULTA
        )
        if len(vector) != DIMENSION_EMBEDDINGS:
            # Con otro tamaño la búsqueda en PostgreSQL fallaría con un 500.
            raise ProveedorIANoDisponible(
                f"El vector de la pregunta tiene {len(vector)} valores y no "
                f"{DIMENSION_EMBEDDINGS}. Revise IA_DIMENSION_EMBEDDINGS."
            )
        fragmentos = selectors.buscar_fragmentos_similares(
            embedding=vector,
            distancia_maxima=settings.IA_DISTANCIA_MAXIMA,
            limite=FRAGMENTOS_POR_CONSULTA,
        )
        if not fragmentos:
            # No se llamó al modelo: se sabe que el consumo fue cero.
            tokens_entrada, tokens_salida = 0, 0
            resultado = RespuestaAgente(
                respuesta=MENSAJE_SIN_INFORMACION, sin_informacion=True, citas=[]
            )
        else:
            respuesta_modelo = proveedor.generar_respuesta(
                mensajes=[
                    Mensaje(RolMensaje.SISTEMA, INSTRUCCIONES_SISTEMA),
                    Mensaje(
                        RolMensaje.USUARIO,
                        armar_mensaje_usuario(pregunta=pregunta, fragmentos=fragmentos),
                    ),
                ]
            )
            # None si el proveedor no los reportó (desconocido, no cero).
            tokens_entrada = respuesta_modelo.tokens_entrada
            tokens_salida = respuesta_modelo.tokens_salida
            texto = respuesta_modelo.texto.strip()
            if not texto:
                # El modelo no dijo nada: para el usuario es lo mismo que no
                # tener información, y no hay respuesta que citar.
                resultado = RespuestaAgente(
                    respuesta=MENSAJE_SIN_INFORMACION, sin_informacion=True, citas=[]
                )
            else:
                resultado = RespuestaAgente(
                    respuesta=texto,
                    sin_informacion=False,
                    citas=_citas_usadas(texto, fragmentos),
                )
    except ProveedorIANoDisponible as error:
        # Los mensajes de ProveedorIANoDisponible los arma el proveedor (código
        # HTTP, intentos): no llevan la llave ni el texto crudo de Gemini, así
        # que sirven como diagnóstico (spec 015). Los tokens quedan en None:
        # si el modelo falló, no se sabe cuánto consumió.
        _registrar_en_bitacora(
            pregunta=pregunta,
            respuesta="",
            fragmentos=fragmentos,
            tokens_entrada=None,
            tokens_salida=None,
            inicio=inicio,
            error=str(error),
            ip=ip,
        )
        raise AgenteNoDisponible() from error

    _registrar_en_bitacora(
        pregunta=pregunta,
        respuesta=resultado.respuesta,
        fragmentos=fragmentos,
        tokens_entrada=tokens_entrada,
        tokens_salida=tokens_salida,
        inicio=inicio,
        ip=ip,
    )
    return resultado


def _registrar_en_bitacora(
    *,
    pregunta: str,
    respuesta: str,
    fragmentos: list[FragmentoRAG],
    tokens_entrada: int | None,
    tokens_salida: int | None,
    inicio: float,
    error: str = "",
    ip: str | None = None,
) -> None:
    """
    Escribe la consulta en la bitácora del agente (spec 015), con el contrato
    acordado en el PR #61.

    - modo PUBLICO y usuario None: el visitante no inicia sesión.
    - documentos_recuperados: cada fragmento que se le dio al modelo, con su
      documento y su distancia, aunque el modelo no lo citara. Así se puede
      revisar después por qué respondió lo que respondió.
    - herramientas_invocadas: vacía hasta que el agente tenga herramientas.
    - duracion_ms: desde el inicio de la consulta, con time.monotonic(), que no
      salta si cambia la hora del servidor.

    Es una sola inserción fuera de transacción: queda guardada aunque después
    se lance AgenteNoDisponible.
    """
    registrar_consulta_agente(
        usuario=None,
        modo=ModoAgente.PUBLICO,
        pregunta=pregunta,
        respuesta=respuesta,
        herramientas_invocadas=[],
        documentos_recuperados=[
            {
                "fragmento_id": fragmento.pk,
                "documento_id": fragmento.documento_id,
                "documento": fragmento.documento.titulo,
                "seccion": fragmento.seccion,
                # float y redondeada: el JSON no admite el tipo de pgvector.
                "distancia": round(float(fragmento.distancia), 4),
            }
            for fragmento in fragmentos
        ],
        tokens_entrada=tokens_entrada,
        tokens_salida=tokens_salida,
        duracion_ms=int((time.monotonic() - inicio) * 1000),
        exito=not error,
        error=error,
        ip=ip,
    )


def _citas_usadas(texto: str, fragmentos: list[FragmentoRAG]) -> list[Cita]:
    """Las fuentes que el modelo citó con [n], con su mismo número.

    Si no citó ninguna, se devuelven todas las que recibió: el usuario siempre
    ve de dónde pudo salir la respuesta (regla 2). Se decidió tras la prueba
    real del 2026-10-31, donde devolver siempre las cinco mostraba fuentes que
    nada tenían que ver con la respuesta.
    """
    citadas = {int(n) for n in _MARCADOR_CITA.findall(texto)}
    numerados = list(enumerate(fragmentos, start=1))
    usados = [(n, f) for n, f in numerados if n in citadas] or numerados
    return [_cita(numero, fragmento) for numero, fragmento in usados]


def _cita(numero: int, fragmento: FragmentoRAG) -> Cita:
    contenido = fragmento.contenido
    extracto = contenido[:LARGO_EXTRACTO]
    if len(contenido) > LARGO_EXTRACTO:
        extracto = extracto.rstrip() + "…"
    return Cita(
        numero=numero,
        documento=fragmento.documento.titulo,
        seccion=fragmento.seccion,
        tipo=fragmento.documento.tipo,
        extracto=extracto,
    )
