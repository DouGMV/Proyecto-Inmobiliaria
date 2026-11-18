"""Registro de los modelos de auditoría en el panel de Django.

Sin reglas de negocio.
"""

from django.contrib import admin

from .models import LogAgenteIA, LogAuditoria


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    """Solo lectura: la bitácora se consulta, nunca se crea ni se edita a mano."""

    list_display = ["fecha", "accion", "entidad", "entidad_id", "usuario", "ip"]
    list_filter = ["accion", "entidad"]
    date_hierarchy = "fecha"
    list_select_related = ["usuario"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LogAgenteIA)
class LogAgenteIAAdmin(admin.ModelAdmin):
    """Consulta la evidencia del agente sin crearla, alterarla ni borrarla."""

    list_display = ["fecha", "modo", "usuario", "ip", "exito", "duracion_ms"]
    list_filter = ["modo", "exito"]
    date_hierarchy = "fecha"
    list_select_related = ["usuario"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
