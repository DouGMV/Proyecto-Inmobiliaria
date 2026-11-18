"""Modelos de auditoría: campos, relaciones, constraints y validación propia.

No llaman a servicios ni envían correos.
"""

import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from .enums import AccionAuditoria, ModoAgente
from .exceptions import RegistroAuditoriaInmutable


class LogAuditoria(models.Model):
    """
    Una operación de escritura sobre una entidad del sistema
    (docs/arquitectura.md §5). Lo crea registrar_auditoria y nada más.

    Es de solo inserción: un registro de auditoría que se puede editar no
    sirve como evidencia. save() y delete() lo impiden para cualquier código
    que pase por el modelo; QuerySet.update() y QuerySet.delete() sí lo
    saltan, así que ningún código del proyecto debe usarlos sobre esta tabla.
    """

    # Referencia por settings.AUTH_USER_MODEL y no importando Usuario:
    # auditoria no importa ninguna app (spec 001, §4).
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="registros_auditoria",
    )
    # Nombre de la tabla afectada, por ejemplo "usuarios_usuario".
    entidad = models.CharField(max_length=100)
    # Nulo cuando no hay registro asociado, como en un login fallido con un
    # correo que no existe.
    entidad_id = models.BigIntegerField(null=True, blank=True)
    accion = models.CharField(max_length=20, choices=AccionAuditoria.choices)
    # DjangoJSONEncoder porque los valores incluyen montos (Decimal) y fechas,
    # que el codificador JSON estándar de Python no sabe escribir.
    valores_anteriores = models.JSONField(
        null=True, blank=True, encoder=DjangoJSONEncoder
    )
    valores_nuevos = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    # auto_now_add: la fecha la pone la base al insertar; nadie puede
    # registrar una operación con otra fecha.
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auditoria_log_sistema"
        ordering = ["-fecha"]
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"
        indexes = [
            # "Historia de este contrato": todas las operaciones de un registro.
            models.Index(
                fields=["entidad", "entidad_id"], name="auditoria_entidad_idx"
            ),
            # Consultas y reportes por rango de fechas.
            models.Index(fields=["fecha"], name="auditoria_fecha_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_accion_display()} {self.entidad} #{self.entidad_id}"

    def save(self, *args, **kwargs):
        # _state.adding es True solo mientras el objeto aún no existe en la
        # base. Si es False, alguien intenta modificar un registro guardado.
        if not self._state.adding:
            raise RegistroAuditoriaInmutable(
                "Los registros de auditoría no se modifican."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RegistroAuditoriaInmutable("Los registros de auditoría no se borran.")


class LogAgenteIA(models.Model):
    """Una consulta del agente, exitosa o fallida (spec 015).

    Solo se inserta, como LogAuditoria. No usa ModeloBase ni importa ia:
    conserva las fuentes como JSON aunque después cambien los documentos.
    QuerySet.update/delete omiten estas protecciones y no deben usarse.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="consultas_agente",
    )
    modo = models.CharField(max_length=10, choices=ModoAgente.choices)
    pregunta = models.TextField()
    respuesta = models.TextField(blank=True)
    herramientas_invocadas = models.JSONField(default=list, blank=True)
    documentos_recuperados = models.JSONField(default=list, blank=True)
    # None es desconocido; cero significa que se conoce consumo cero.
    tokens_entrada = models.PositiveIntegerField(null=True, blank=True)
    tokens_salida = models.PositiveIntegerField(null=True, blank=True)
    duracion_ms = models.PositiveIntegerField()
    exito = models.BooleanField()
    error = models.TextField(blank=True)
    # IP del visitante que preguntó (Serie II, inciso 5). El agente es
    # público y no tiene usuario: la IP es el único rastro de quién consultó.
    # Nula en consultas que no vienen de una petición HTTP (shell, pruebas)
    # o en registros anteriores a este campo.
    ip = models.GenericIPAddressField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auditoria_log_agente"
        ordering = ["-fecha", "-id"]
        verbose_name = "consulta del agente"
        verbose_name_plural = "consultas del agente"
        indexes = [models.Index(fields=["fecha"], name="agente_fecha_idx")]

    def __str__(self) -> str:
        resultado = "correcta" if self.exito else "fallida"
        return f"Consulta {self.modo} {resultado} #{self.pk}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RegistroAuditoriaInmutable(
                "Las consultas del agente no se modifican."
            )
        # Un objeto nuevo con un id asignado no debe sobrescribir un log
        # existente: Django por defecto intentaría UPDATE antes que INSERT.
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RegistroAuditoriaInmutable("Las consultas del agente no se borran.")

    def clean(self) -> None:
        """Valida el contrato JSON y la coherencia del resultado, sin usar IA."""
        super().clean()
        errores = {}
        if self.exito is False and (
            not isinstance(self.error, str) or not self.error.strip()
        ):
            errores["error"] = "Una consulta fallida debe incluir un diagnóstico."
        elif self.exito is True and self.error:
            errores["error"] = "Una consulta exitosa no debe incluir un error."

        for campo in ("herramientas_invocadas", "documentos_recuperados"):
            elementos = getattr(self, campo)
            if not isinstance(elementos, list) or any(
                not isinstance(elemento, dict) for elemento in elementos
            ):
                errores[campo] = "Debe ser una lista de objetos JSON."
                continue
            try:
                # PostgreSQL no admite NaN/Infinity, aunque json.dumps los
                # acepte por defecto. Rechazarlos antes evita un error SQL.
                json.dumps(elementos, allow_nan=False)
            except (TypeError, ValueError):
                errores[campo] = "Los elementos deben contener valores JSON válidos."
                continue
            for elemento in elementos:
                if campo == "herramientas_invocadas":
                    valido = (
                        isinstance(elemento.get("nombre"), str)
                        and bool(elemento["nombre"].strip())
                        and isinstance(elemento.get("argumentos"), dict)
                    )
                else:
                    valido = all(
                        type(elemento.get(clave)) is int and elemento[clave] > 0
                        for clave in ("documento_id", "fragmento_id")
                    ) and all(
                        isinstance(elemento.get(clave), str)
                        for clave in ("documento", "seccion")
                    )
                    valido = valido and type(elemento.get("distancia")) in (
                        int,
                        float,
                    )
                if not valido:
                    errores[campo] = "Un elemento no cumple el contrato de la spec 015."
                    break
        if errores:
            raise ValidationError(errores)
