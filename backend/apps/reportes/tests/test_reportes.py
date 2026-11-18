"""Reglas de la spec 016 con PostgreSQL y exportadores reales."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import pytest
from django.db import connection
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.auditoria.models import LogAuditoria
from apps.catalogo.models import Propiedad, Unidad
from apps.catalogo.tests.factories import (
    DocumentoOficialFactory,
    PropiedadFactory,
    UnidadFactory,
)
from apps.core.tests.factories import MonedaFactory
from apps.reportes.estructuras import (
    FiltrosBitacora,
    FiltrosInventario,
    FiltrosVencimientos,
)
from apps.reportes.exceptions import ReporteDemasiadoGrande
from apps.reportes.exportadores import contexto_pdf, exportar_excel, exportar_pdf
from apps.reportes.selectors import (
    GUATEMALA,
    resumir_reporte,
    seleccionar_filas_reporte,
)
from apps.reportes.services import (
    obtener_reporte_exportacion,
    obtener_reporte_paginado,
)
from apps.usuarios.enums import NombreRol
from apps.usuarios.models import Rol
from apps.usuarios.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db
SLUG = "inventario-disponible"


@pytest.fixture
def usuario():
    return UsuarioFactory()


@pytest.fixture
def cliente(usuario):
    cliente = APIClient()
    cliente.force_authenticate(usuario)
    return cliente


def test_inventario_no_duplica_edificio_y_separa_monedas():
    casa = PropiedadFactory(estado="DISPONIBLE", precio_lista=Decimal("100.00"))
    unidad = UnidadFactory(
        id=casa.id,
        estado="DISPONIBLE",
        precio_lista=Decimal("200.00"),
        moneda=MonedaFactory(codigo="GTQ"),
    )
    unidad.propiedad.estado = "DISPONIBLE"
    unidad.propiedad.save()
    PropiedadFactory(activo=False, estado="DISPONIBLE")
    UnidadFactory(id=casa.id + 1, activo=False, estado="DISPONIBLE")
    UnidadFactory(
        id=casa.id + 2, propiedad=PropiedadFactory(activo=False), estado="DISPONIBLE"
    )
    resumen = resumir_reporte(slug=SLUG, filtros=FiltrosInventario())
    assert resumen.count == 2
    assert resumen.totales["valor_por_moneda"] == {
        "USD": Decimal("100.00"),
        "GTQ": Decimal("200.00"),
    }
    filtros = FiltrosInventario(
        pais=casa.ciudad.pais_id,
        ciudad=casa.ciudad_id,
        tipo=casa.tipo_id,
        moneda="USD",
        precio_min=Decimal("100"),
        precio_max=Decimal("100"),
        area_min=casa.area_m2,
        area_max=casa.area_m2,
    )
    filas = seleccionar_filas_reporte(slug=SLUG, filtros=filtros, offset=0, limite=25)
    assert [(f["origen"], f["id"]) for f in filas] == [("PROPIEDAD", casa.id)]


@pytest.mark.parametrize("fabrica", [PropiedadFactory, UnidadFactory])
def test_inventario_fechas_incluye_dias_completos_de_guatemala(usuario, fabrica):
    dia = date(2026, 11, 18)
    inicio = datetime(2026, 11, 18, tzinfo=GUATEMALA)
    siguiente = inicio + timedelta(days=1)
    bienes = [fabrica(estado="DISPONIBLE") for _ in range(4)]
    instantes = [
        inicio - timedelta(microseconds=1),
        inicio,
        siguiente - timedelta(microseconds=1),
        siguiente,
    ]
    for bien, instante in zip(bienes, instantes, strict=True):
        modelo = Unidad if isinstance(bien, Unidad) else Propiedad
        modelo.objects.filter(pk=bien.pk).update(creado_en=instante)

    filtros = FiltrosInventario(fecha_desde=dia, fecha_hasta=dia)
    pagina = obtener_reporte_paginado(slug=SLUG, filtros=filtros, usuario=usuario)
    exportado = obtener_reporte_exportacion(slug=SLUG, filtros=filtros, usuario=usuario)
    assert pagina.count == 2
    assert {fila["id"] for fila in pagina.reporte.filas} == {b.pk for b in bienes[1:3]}
    assert exportado.filas == pagina.reporte.filas
    assert exportado.totales == pagina.reporte.totales
    assert "fecha_desde: 2026-11-18" in exportado.subtitulo
    assert (
        resumir_reporte(slug=SLUG, filtros=FiltrosInventario(fecha_desde=dia)).count
        == 3
    )
    assert (
        resumir_reporte(slug=SLUG, filtros=FiltrosInventario(fecha_hasta=dia)).count
        == 3
    )


@pytest.mark.parametrize("sufijo", ["", "excel/", "pdf/"])
@pytest.mark.parametrize(
    "parametros",
    [
        {"fecha_desde": "2026-11-19", "fecha_hasta": "2026-11-18"},
        {"fecha_hasta": "9999-12-31"},
        {"fecha_desde": "no-es-fecha"},
    ],
)
def test_inventario_rechaza_fechas_invalidas_en_todas_las_salidas(
    cliente, sufijo, parametros
):
    respuesta = cliente.get(f"/api/v1/reportes/{SLUG}/{sufijo}", parametros)
    assert respuesta.status_code == 400


def test_sesenta_filas_pagina_en_sql_y_exporta_todo(usuario):
    base = PropiedadFactory(estado="DISPONIBLE")
    PropiedadFactory.create_batch(59, estado="DISPONIBLE", ciudad=base.ciudad)
    with CaptureQueriesContext(connection) as consultas:
        pagina = obtener_reporte_paginado(
            slug=SLUG, filtros=FiltrosInventario(), usuario=usuario, pagina=2
        )
    assert pagina.count == 60
    assert len(pagina.reporte.filas) == 25
    assert pagina.reporte.totales["cantidad"] == 60
    detalles = [c["sql"] for c in consultas if "UNION ALL" in c["sql"]]
    assert len(detalles) == 1
    assert "LIMIT 25 OFFSET 25" in detalles[0]
    exportado = obtener_reporte_exportacion(
        slug=SLUG, filtros=FiltrosInventario(), usuario=usuario
    )
    assert len(exportado.filas) == 60
    assert exportado.totales == pagina.reporte.totales
    libro = load_workbook(BytesIO(exportar_excel(exportado)))
    assert libro["Reporte"].max_row == 66
    assert libro["Reporte"].freeze_panes == "A7"
    assert libro["Reporte"]["I7"].data_type == "n"
    assert exportar_pdf(exportado).startswith(b"%PDF-")


def test_limite_5001_rechaza_antes_de_leer_detalle(usuario):
    base = PropiedadFactory(estado="DISPONIBLE")
    Propiedad.objects.bulk_create(
        [
            Propiedad(
                nombre=f"Demo {n}",
                tipo=base.tipo,
                ciudad=base.ciudad,
                direccion="Demo",
                area_m2=1,
                precio_lista=1,
                moneda=base.moneda,
                estado="DISPONIBLE",
            )
            for n in range(5000)
        ]
    )
    with patch("apps.reportes.services.seleccionar_filas_reporte") as detalle:
        with pytest.raises(ReporteDemasiadoGrande):
            obtener_reporte_exportacion(
                slug=SLUG, filtros=FiltrosInventario(), usuario=usuario
            )
        detalle.assert_not_called()


def test_vencimientos_limites_y_nulos():
    hoy = timezone.localdate(timezone=GUATEMALA)
    documentos = [
        DocumentoOficialFactory(fecha_vencimiento=hoy + timedelta(days=d))
        for d in (-1, 0, 30, 31)
    ]
    DocumentoOficialFactory(fecha_vencimiento=None)
    DocumentoOficialFactory(fecha_vencimiento=hoy, activo=False)
    DocumentoOficialFactory(
        fecha_vencimiento=hoy, propiedad=PropiedadFactory(activo=False)
    )
    resumen = resumir_reporte(
        slug="documentos-por-vencer", filtros=FiltrosVencimientos()
    )
    assert resumen.totales == dict(cantidad=3, vencidos=1, por_vencer=2)
    filas = seleccionar_filas_reporte(
        slug="documentos-por-vencer", filtros=FiltrosVencimientos(), offset=0, limite=25
    )
    assert [f["id"] for f in filas] == [d.id for d in documentos[:3]]


def test_bitacora_dias_de_guatemala_y_campos_excluidos():
    for hora in (5, 6, 29, 30):
        fecha = datetime(2026, 10, 30, tzinfo=UTC) + timedelta(hours=hora)
        with patch("django.utils.timezone.now", return_value=fecha):
            LogAuditoria.objects.create(
                entidad="demo",
                accion="CREAR",
                ip="127.0.0.1",
                valores_nuevos={"privado": 1},
            )
    filtros = FiltrosBitacora(
        fecha_desde=date(2026, 10, 30),
        fecha_hasta=date(2026, 10, 30),
        entidad="demo",
        accion="CREAR",
    )
    filas = seleccionar_filas_reporte(
        slug="bitacora-auditoria", filtros=filtros, offset=0, limite=25
    )
    assert len(filas) == 2
    assert set(filas[0]) == {
        "id",
        "fecha",
        "usuario_id",
        "entidad",
        "entidad_id",
        "accion",
    }


@pytest.mark.parametrize("rol", NombreRol.values)
def test_permisos_catalogo_json_y_archivos(rol):
    usuario = UsuarioFactory(rol=Rol.objects.get(nombre=rol))
    cliente = APIClient()
    cliente.force_authenticate(usuario)
    catalogo = cliente.get("/api/v1/reportes/")
    assert catalogo.status_code == 200
    slugs = [reporte["slug"] for reporte in catalogo.data["results"]]
    assert ("bitacora-auditoria" in slugs) == (rol == "ADMINISTRADOR")
    for slug in (SLUG, "documentos-por-vencer", "bitacora-auditoria"):
        esperado = (
            403 if slug == "bitacora-auditoria" and rol != "ADMINISTRADOR" else 200
        )
        for sufijo in ("", "excel/", "pdf/"):
            respuesta = cliente.get(f"/api/v1/reportes/{slug}/{sufijo}")
            assert respuesta.status_code == esperado


@pytest.mark.parametrize(
    "slug,parametros",
    [
        (SLUG, {"desconocido": "x"}),
        (SLUG, {"precio_min": 1}),
        (SLUG, {"moneda": "USD", "precio_min": 2, "precio_max": 1}),
        (SLUG, {"area_min": 2, "area_max": 1}),
        (SLUG, {"pais": -1}),
        ("documentos-por-vencer", {"dias_anticipacion": 366}),
        ("documentos-por-vencer", {"tipo": "INVALIDO"}),
    ],
)
def test_filtros_invalidos(cliente, slug, parametros):
    respuesta = cliente.get(f"/api/v1/reportes/{slug}/", parametros)
    assert respuesta.status_code == 400
    assert respuesta.data["error"]["codigo"] == "VALIDACION"


@pytest.mark.parametrize("sufijo", ("excel/", "pdf/"))
def test_exportacion_no_admite_pagina(cliente, sufijo):
    assert (
        cliente.get(f"/api/v1/reportes/{SLUG}/{sufijo}", {"page": 1}).status_code == 400
    )


def test_autenticacion_slug_y_pagina(cliente):
    assert APIClient().get("/api/v1/reportes/").status_code == 401
    assert cliente.get("/api/v1/reportes/no-existe/").status_code == 404
    assert cliente.get(f"/api/v1/reportes/{SLUG}/?page=2").status_code == 404
    assert cliente.get(f"/api/v1/reportes/{SLUG}/?page=no").status_code == 404
    assert cliente.get(f"/api/v1/reportes/{SLUG}/").data["totales"]["cantidad"] == 0


def test_json_conserva_decimal_exacto_y_enlaces(cliente):
    base = PropiedadFactory(
        estado="DISPONIBLE", precio_lista=Decimal("1234567890123456.78")
    )
    PropiedadFactory.create_batch(25, estado="DISPONIBLE", ciudad=base.ciudad)
    respuesta = cliente.get(f"/api/v1/reportes/{SLUG}/?moneda=USD")
    assert respuesta.status_code == 200
    assert (
        respuesta.json()["filas"]["results"][0]["precio_lista"] == "1234567890123456.78"
    )
    assert "moneda=USD" in respuesta.data["filas"]["next"]
    assert "page=2" in respuesta.data["filas"]["next"]
    siguiente = cliente.get(respuesta.data["filas"]["next"])
    assert len(siguiente.data["filas"]["results"]) == 1
    assert siguiente.data["totales"] == respuesta.data["totales"]


@pytest.mark.parametrize("sufijo", ("excel/", "pdf/"))
def test_api_limite_exportacion_y_error_uniforme(cliente, sufijo):
    from apps.reportes.estructuras import ResumenReporte

    with patch(
        "apps.reportes.services.resumir_reporte", return_value=ResumenReporte(5001, {})
    ):
        with patch("apps.reportes.services.seleccionar_filas_reporte") as detalles:
            respuesta = cliente.get(f"/api/v1/reportes/{SLUG}/{sufijo}")
            assert respuesta.status_code == 400
            assert respuesta.data["error"]["codigo"] == "REPORTE_DEMASIADO_GRANDE"
            detalles.assert_not_called()


def test_excel_fecha_y_descargas_autenticadas(cliente):
    hoy = timezone.localdate(timezone=GUATEMALA)
    DocumentoOficialFactory(fecha_vencimiento=hoy)
    respuesta = cliente.get("/api/v1/reportes/documentos-por-vencer/excel/")
    assert respuesta.status_code == 200
    assert 'filename="R16_documentos_por_vencer_' in respuesta["Content-Disposition"]
    hoja = load_workbook(BytesIO(respuesta.content))["Reporte"]
    assert hoja["E7"].is_date
    assert hoja["E7"].value.date() == hoy
    for sufijo in ("", "excel/", "pdf/"):
        assert APIClient().get(f"/api/v1/reportes/{SLUG}/{sufijo}").status_code == 401


def test_filtro_repetido_y_fechas_invalidas(cliente, usuario):
    assert (
        cliente.get(f"/api/v1/reportes/{SLUG}/?moneda=USD&moneda=GTQ").status_code
        == 400
    )
    usuario.rol = Rol.objects.get(nombre="ADMINISTRADOR")
    usuario.save()
    for parametros in (
        {"fecha_desde": "2026-11-01", "fecha_hasta": "2026-10-31"},
        {"fecha_hasta": "2026-02-30"},
        {"accion": "INVALIDA"},
    ):
        assert (
            cliente.get("/api/v1/reportes/bitacora-auditoria/", parametros).status_code
            == 400
        )


@pytest.mark.parametrize(
    "texto", ["=1+1", "+SUM(A1)", "-1+2", "@SUM(A1)", "<img src='https://demo.test/x'>"]
)
def test_excel_literal_y_html_escapado(usuario, texto):
    PropiedadFactory(estado="DISPONIBLE", nombre=texto)
    reporte = obtener_reporte_exportacion(
        slug=SLUG, filtros=FiltrosInventario(), usuario=usuario
    )
    reporte = replace(reporte, generado_por=texto)
    hoja = load_workbook(BytesIO(exportar_excel(reporte)))["Reporte"]
    assert hoja["D7"].value == texto
    assert hoja["D7"].data_type == "s"
    html = render_to_string("reportes/reporte.html", contexto_pdf(reporte))
    assert "<img src=" not in html
