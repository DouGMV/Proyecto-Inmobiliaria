"""Contrato de registro de IA, inmutabilidad y transacciones (spec 015)."""

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.auditoria.enums import ModoAgente
from apps.auditoria.exceptions import RegistroAuditoriaInmutable
from apps.auditoria.models import LogAgenteIA, LogAuditoria
from apps.auditoria.services import registrar_consulta_agente
from apps.usuarios.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db


def registrar(**cambios):
    datos = {
        "usuario": None,
        "modo": ModoAgente.PUBLICO,
        "pregunta": "¿Cuánto dura una reserva?",
        "respuesta": "La reserva dura 15 días [1].",
        "herramientas_invocadas": [],
        "documentos_recuperados": [],
        "tokens_entrada": 12,
        "tokens_salida": 8,
        "duracion_ms": 150,
        "exito": True,
    }
    datos.update(cambios)
    return registrar_consulta_agente(**datos)


@pytest.mark.parametrize("ip", [None, "192.0.2.10", "2001:db8::1"])
def test_registra_ip_opcional(ip):
    registro = registrar(ip=ip)
    registro.refresh_from_db()
    assert registro.ip == ip


def test_rechaza_ip_invalida():
    with pytest.raises(ValidationError):
        registrar(ip="direccion-invalida")
    assert not LogAgenteIA.objects.exists()


def test_conserva_usuario_fuentes_herramientas_y_metricas():
    usuario = UsuarioFactory()
    fuentes = [
        {
            "fragmento_id": 12,
            "documento_id": 3,
            "documento": "Manual de procesos de venta",
            "seccion": "Reservas",
            "distancia": 0.23,
        }
    ]
    herramientas = [{"nombre": "buscar_propiedades", "argumentos": {"pais_id": 1}}]

    registro = registrar(
        usuario=usuario,
        modo=ModoAgente.INTERNO,
        herramientas_invocadas=herramientas,
        documentos_recuperados=fuentes,
    )
    registro.refresh_from_db()

    assert registro.usuario == usuario
    assert registro.modo == ModoAgente.INTERNO
    assert registro.pregunta == "¿Cuánto dura una reserva?"
    assert registro.respuesta == "La reserva dura 15 días [1]."
    assert registro.documentos_recuperados == fuentes
    assert registro.herramientas_invocadas == herramientas
    assert (registro.tokens_entrada, registro.tokens_salida) == (12, 8)
    assert registro.duracion_ms == 150
    assert registro.exito is True
    assert registro.error == ""
    assert timezone.is_aware(registro.fecha)
    assert LogAuditoria.objects.count() == 0


def test_sin_informacion_conserva_cero_y_sin_proveedor_conserva_desconocido():
    sin_informacion = registrar(
        tokens_entrada=0,
        tokens_salida=0,
        respuesta="No encontré información sobre eso en los documentos.",
    )
    fallo = registrar(
        tokens_entrada=None,
        tokens_salida=None,
        exito=False,
        respuesta="",
        error="El proveedor no está disponible.",
    )
    sin_informacion.refresh_from_db()
    fallo.refresh_from_db()

    assert sin_informacion.usuario is None
    assert sin_informacion.tokens_entrada == sin_informacion.tokens_salida == 0
    assert fallo.tokens_entrada is None and fallo.tokens_salida is None
    assert fallo.exito is False
    assert fallo.respuesta == ""


@pytest.mark.parametrize("campo", ["tokens_entrada", "tokens_salida", "duracion_ms"])
@pytest.mark.parametrize("valor", [-1, True, 1.5, "2"])
def test_rechaza_contadores_invalidos_sin_insertar(campo, valor):
    with pytest.raises(ValidationError) as error:
        registrar(**{campo: valor})

    assert campo in error.value.message_dict
    assert LogAgenteIA.objects.count() == 0


@pytest.mark.parametrize(
    "cambios,campo",
    [
        ({"modo": "OTRO"}, "modo"),
        ({"duracion_ms": None}, "duracion_ms"),
        ({"exito": "False"}, "exito"),
        ({"exito": False}, "error"),
        ({"exito": False, "error": "  "}, "error"),
        ({"exito": True, "error": "Falló"}, "error"),
        ({"herramientas_invocadas": {}}, "herramientas_invocadas"),
        ({"herramientas_invocadas": ["buscar"]}, "herramientas_invocadas"),
        ({"herramientas_invocadas": [{"nombre": "buscar"}]}, "herramientas_invocadas"),
        ({"documentos_recuperados": None}, "documentos_recuperados"),
        ({"documentos_recuperados": [{}]}, "documentos_recuperados"),
    ],
)
def test_rechaza_modo_resultado_y_listas_invalidas(cambios, campo):
    with pytest.raises(ValidationError) as error:
        registrar(**cambios)

    assert campo in error.value.message_dict
    assert LogAgenteIA.objects.count() == 0


@pytest.mark.parametrize("distancia", [float("nan"), float("inf"), True, "0.23"])
def test_rechaza_puntajes_no_numericos_o_no_finitos(distancia):
    with pytest.raises(ValidationError):
        registrar(
            documentos_recuperados=[
                {
                    "fragmento_id": 12,
                    "documento_id": 3,
                    "documento": "Manual",
                    "seccion": "Reservas",
                    "distancia": distancia,
                }
            ]
        )

    assert LogAgenteIA.objects.count() == 0


def test_no_permite_modificar_ni_borrar_registros():
    registro = registrar()
    respuesta_original = registro.respuesta
    registro.respuesta = "Texto alterado"

    with pytest.raises(RegistroAuditoriaInmutable):
        registro.save()
    with pytest.raises(RegistroAuditoriaInmutable):
        registro.delete()

    registro.refresh_from_db()
    assert registro.respuesta == respuesta_original


def test_no_comparte_listas_por_defecto_entre_instancias():
    primero = LogAgenteIA()
    segundo = LogAgenteIA()
    primero.documentos_recuperados.append({"documento_id": 1})
    primero.herramientas_invocadas.append({"nombre": "buscar"})

    assert segundo.documentos_recuperados == []
    assert segundo.herramientas_invocadas == []


def test_otra_instancia_con_el_mismo_id_no_sobrescribe_el_log():
    original = registrar()
    copia = LogAgenteIA(
        pk=original.pk,
        modo=ModoAgente.PUBLICO,
        pregunta="Pregunta distinta",
        respuesta="Respuesta alterada",
        duracion_ms=1,
        exito=True,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        copia.save()

    original.refresh_from_db()
    assert original.respuesta == "La reserva dura 15 días [1]."


def test_impide_el_borrado_del_usuario_referenciado():
    usuario = UsuarioFactory()
    registrar(usuario=usuario)

    with pytest.raises(ProtectedError):
        usuario.delete()


def test_panel_sin_alta_edicion_ni_borrado():
    panel = admin.site._registry[LogAgenteIA]

    assert panel.has_add_permission(request=None) is False
    assert panel.has_change_permission(request=None) is False
    assert panel.has_delete_permission(request=None) is False


def test_si_llamador_revierte_transaccion_tambien_revierte_el_log():
    with pytest.raises(RuntimeError), transaction.atomic():
        registrar()
        raise RuntimeError("Se revierte la transacción del llamador.")

    assert LogAgenteIA.objects.count() == 0


def test_registrar_fallo_despues_de_revertir_lo_conserva():
    with pytest.raises(RuntimeError), transaction.atomic():
        raise RuntimeError("Falla antes de registrar la consulta.")

    registro = registrar(
        exito=False,
        respuesta="",
        error="El proveedor no respondió.",
        tokens_entrada=None,
        tokens_salida=None,
    )

    assert LogAgenteIA.objects.get(pk=registro.pk).error == "El proveedor no respondió."
