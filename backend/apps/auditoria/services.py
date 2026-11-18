"""Servicios de auditoría: escrituras con reglas de negocio, transacciones y
auditoría.

No conocen request ni hablan HTTP.
"""

from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import ValidationError

from .enums import AccionAuditoria
from .models import LogAgenteIA, LogAuditoria


def registrar_auditoria(
    *,
    usuario: AbstractBaseUser | None,
    entidad: str,
    entidad_id: int | None,
    accion: AccionAuditoria,
    valores_anteriores: dict | None = None,
    valores_nuevos: dict | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> LogAuditoria:
    """
    Registra una operación en la bitácora del sistema (CLAUDE.md §8).

    Se llama explícitamente desde cada servicio de escritura, y no con
    señales de Django, para que la auditoría se vea en el código que escribe.

    No abre su propia transacción a propósito: debe llamarse dentro de la
    transacción del servicio que escribe. Así, si la operación de negocio
    falla y se revierte, su registro se revierte con ella, y nunca queda una
    operación sin registro ni un registro de algo que no ocurrió.

    usuario es None cuando la acción la hace el sistema (una tarea
    programada) o cuando nadie se autenticó (un login fallido). Se anota como
    AbstractBaseUser, la clase de Django, para no importar la app usuarios.
    """
    return LogAuditoria.objects.create(
        usuario=usuario,
        entidad=entidad,
        entidad_id=entidad_id,
        accion=accion,
        valores_anteriores=valores_anteriores,
        valores_nuevos=valores_nuevos,
        ip=ip,
        user_agent=user_agent or "",
    )


def registrar_consulta_agente(
    *,
    usuario: AbstractBaseUser | None,
    modo: str,
    pregunta: str,
    respuesta: str,
    herramientas_invocadas: list[dict],
    documentos_recuperados: list[dict],
    tokens_entrada: int | None,
    tokens_salida: int | None,
    duracion_ms: int,
    exito: bool,
    error: str = "",
    ip: str | None = None,
) -> LogAgenteIA:
    """Registra una consulta completa, sin llamar a IA ni abrir un atomic.

    Se llama una vez al finalizar la consulta, también ante fallo. El error
    debe ser un diagnóstico controlado, nunca una excepción cruda con secretos.
    Los tokens desconocidos se conservan como None, no como cero.

    Es una sola inserción: en autocommit se confirma al guardar; dentro de una
    transacción del llamador participa en ella y se revierte con ella.
    """
    # Django convierte valores como True o "3" a enteros al validar campos.
    # El contrato recibe contadores enteros reales, antes de esa conversión.
    errores = {}
    for campo, valor in (
        ("tokens_entrada", tokens_entrada),
        ("tokens_salida", tokens_salida),
        ("duracion_ms", duracion_ms),
    ):
        if valor is None and campo != "duracion_ms":
            continue
        if type(valor) is not int or valor < 0:
            errores[campo] = "Debe ser un entero no negativo."
    if type(exito) is not bool:
        errores["exito"] = "Debe ser un booleano."
    for campo, valor in (
        ("pregunta", pregunta),
        ("respuesta", respuesta),
        ("error", error),
    ):
        if not isinstance(valor, str):
            errores[campo] = "Debe ser texto."
    if errores:
        raise ValidationError(errores)

    registro = LogAgenteIA(
        usuario=usuario,
        modo=modo,
        pregunta=pregunta,
        respuesta=respuesta,
        herramientas_invocadas=herramientas_invocadas,
        documentos_recuperados=documentos_recuperados,
        tokens_entrada=tokens_entrada,
        tokens_salida=tokens_salida,
        duracion_ms=duracion_ms,
        exito=exito,
        error=error,
        ip=ip,
    )
    registro.full_clean()
    registro.save()
    return registro
