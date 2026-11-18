"""Lecturas y agregaciones SQL. Se limita el detalle antes de materializarlo."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.base_user import AbstractBaseUser
from django.db.models import CharField, Count, F, QuerySet, Sum, Value
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.catalogo.selectors import (
    listar_documentos,
    listar_propiedades,
    listar_unidades,
)

from .catalogo import CATALOGO, metadatos
from .estructuras import (
    FiltrosBitacora,
    FiltrosInventario,
    FiltrosReporte,
    FiltrosVencimientos,
    Grupo,
    ResumenReporte,
)
from .selectors_catalogo import REPORTES_CATALOGO
from .selectors_comerciales import REPORTES_COMERCIALES
from .selectors_compras_obra import REPORTES_COMPRAS_OBRA
from .selectors_ingresos import resumir_ingresos, seleccionar_ingresos

GUATEMALA = ZoneInfo("America/Guatemala")


def listar_reportes(*, usuario: AbstractBaseUser) -> list[dict]:
    """Catálogo autorizado para el rol autenticado."""
    return sorted(
        (
            metadatos(slug)
            for slug, d in CATALOGO.items()
            if usuario.rol.nombre in d["roles"]
        ),
        key=lambda reporte: reporte["codigo"],
    )


def _fuentes_inventario(filtros: FiltrosInventario) -> tuple[QuerySet, QuerySet]:
    propiedades = listar_propiedades().filter(tipo__requiere_unidades=False)
    unidades = listar_unidades().filter(propiedad__tipo__requiere_unidades=True)
    fuentes = []
    for consulta, prefijo in ((propiedades, ""), (unidades, "propiedad__")):
        consulta = consulta.filter(estado="DISPONIBLE")
        if filtros.fecha_desde is not None:
            consulta = consulta.filter(
                creado_en__gte=datetime.combine(
                    filtros.fecha_desde, time.min, tzinfo=GUATEMALA
                )
            )
        if filtros.fecha_hasta is not None:
            consulta = consulta.filter(
                creado_en__lt=datetime.combine(
                    filtros.fecha_hasta + timedelta(days=1), time.min, tzinfo=GUATEMALA
                )
            )
        for campo, valor in (
            ("ciudad__pais_id", filtros.pais),
            ("ciudad_id", filtros.ciudad),
            ("tipo_id", filtros.tipo),
        ):
            if valor is not None:
                consulta = consulta.filter(**{prefijo + campo: valor})
        for campo, valor in (
            ("moneda__codigo", filtros.moneda),
            ("precio_lista__gte", filtros.precio_min),
            ("precio_lista__lte", filtros.precio_max),
            ("area_m2__gte", filtros.area_min),
            ("area_m2__lte", filtros.area_max),
        ):
            if valor is not None:
                consulta = consulta.filter(**{campo: valor})
        fuentes.append(consulta.order_by())
    return tuple(fuentes)


def seleccionar_inventario(*, filtros: FiltrosInventario) -> QuerySet[dict]:
    """UNION ALL con identidad (origen, id), sin contar los edificios."""
    propiedades, unidades = _fuentes_inventario(filtros)
    proyecciones = []
    for consulta, origen, prefijo in (
        (propiedades, "PROPIEDAD", ""),
        (unidades, "UNIDAD", "propiedad__"),
    ):
        proyecciones.append(
            consulta.values(
                "id",
                "codigo",
                "area_m2",
                "precio_lista",
                origen=Value(origen, output_field=CharField()),
                nombre_reporte=F(prefijo + "nombre"),
                ciudad_reporte=F(prefijo + "ciudad__nombre"),
                tipo_reporte=F(prefijo + "tipo__nombre"),
                moneda_reporte=F("moneda__codigo"),
            )
        )
    return proyecciones[0].union(proyecciones[1], all=True).order_by("origen", "id")


def seleccionar_vencimientos(*, filtros: FiltrosVencimientos) -> QuerySet:
    """Vencidos y límite inclusivo hoy + N; omite nulos e inactivos."""
    limite = timezone.localdate(timezone=GUATEMALA) + timedelta(
        days=filtros.dias_anticipacion
    )
    consulta = listar_documentos().filter(fecha_vencimiento__lte=limite)
    if filtros.tipo is not None:
        consulta = consulta.filter(tipo=filtros.tipo)
    if filtros.pais is not None:
        consulta = consulta.filter(propiedad__ciudad__pais_id=filtros.pais)
    return consulta.order_by("fecha_vencimiento", "id")


def seleccionar_bitacora(*, filtros: FiltrosBitacora) -> QuerySet:
    """Días de Guatemala, usando el siguiente día como límite exclusivo."""
    consulta = LogAuditoria.objects.all()
    for campo, valor in (
        ("usuario_id", filtros.usuario),
        ("entidad", filtros.entidad),
        ("accion", filtros.accion),
    ):
        if valor is not None:
            consulta = consulta.filter(**{campo: valor})
    if filtros.fecha_desde is not None:
        consulta = consulta.filter(
            fecha__gte=datetime.combine(filtros.fecha_desde, time.min, tzinfo=GUATEMALA)
        )
    if filtros.fecha_hasta is not None:
        consulta = consulta.filter(
            fecha__lt=datetime.combine(
                filtros.fecha_hasta + timedelta(days=1), time.min, tzinfo=GUATEMALA
            )
        )
    return consulta.order_by("-fecha", "-id")


def resumir_reporte(
    *, slug: str, filtros: FiltrosReporte, usuario: AbstractBaseUser | None = None
) -> ResumenReporte:
    """
    Agrega todo el filtro en PostgreSQL sin cargar detalles. Los reportes
    comerciales necesitan al usuario para aplicar su cartera (spec 021, regla 6).
    """
    if slug == "flujo-ingresos":
        return resumir_ingresos(filtros=filtros, usuario=usuario)
    if slug in REPORTES_COMERCIALES:
        return REPORTES_COMERCIALES[slug][0](filtros=filtros, usuario=usuario)
    if slug in REPORTES_CATALOGO:
        return REPORTES_CATALOGO[slug][0](filtros=filtros, usuario=usuario)
    if slug in REPORTES_COMPRAS_OBRA:
        return REPORTES_COMPRAS_OBRA[slug][0](filtros=filtros, usuario=usuario)
    if slug == "inventario-disponible":
        grupos, monedas = {}, {}
        count, area = 0, Decimal("0.00")
        for consulta, prefijo in zip(
            _fuentes_inventario(filtros), ("", "propiedad__"), strict=True
        ):
            resumenes = consulta.values(
                ciudad_id_reporte=F(prefijo + "ciudad_id"),
                ciudad_reporte=F(prefijo + "ciudad__nombre"),
                tipo_id_reporte=F(prefijo + "tipo_id"),
                tipo_reporte=F(prefijo + "tipo__nombre"),
                moneda_reporte=F("moneda__codigo"),
            ).annotate(
                cantidad=Count("id"), area=Sum("area_m2"), valor=Sum("precio_lista")
            )
            for r in resumenes:
                moneda = r["moneda_reporte"]
                clave = (r["ciudad_id_reporte"], r["tipo_id_reporte"], moneda)
                g = grupos.setdefault(
                    clave,
                    dict(
                        ciudad=r["ciudad_reporte"],
                        tipo=r["tipo_reporte"],
                        moneda=moneda,
                        cantidad=0,
                        area_m2=Decimal("0.00"),
                        precio_lista=Decimal("0.00"),
                    ),
                )
                g["cantidad"] += r["cantidad"]
                g["area_m2"] += r["area"]
                g["precio_lista"] += r["valor"]
                count += r["cantidad"]
                area += r["area"]
                monedas[moneda] = monedas.get(moneda, Decimal("0.00")) + r["valor"]
        return ResumenReporte(
            count,
            dict(
                cantidad=count,
                area_m2=area,
                valor_por_moneda=dict(sorted(monedas.items())),
            ),
            [
                Grupo(" / ".join((g["ciudad"], g["tipo"], g["moneda"])), g)
                for _, g in sorted(grupos.items())
            ],
        )
    if slug == "documentos-por-vencer":
        consulta = seleccionar_vencimientos(filtros=filtros)
        hoy = timezone.localdate(timezone=GUATEMALA)
        count = consulta.count()
        vencidos = consulta.filter(fecha_vencimiento__lt=hoy).count()
        return ResumenReporte(
            count, dict(cantidad=count, vencidos=vencidos, por_vencer=count - vencidos)
        )
    consulta = seleccionar_bitacora(filtros=filtros)
    grupos = (
        consulta.order_by()
        .values("entidad", "accion")
        .annotate(cantidad=Count("id"))
        .order_by("entidad", "accion")
    )
    count = consulta.count()
    return ResumenReporte(
        count,
        {"cantidad": count},
        [Grupo(f"{g['entidad']} / {g['accion']}", g) for g in grupos],
    )


def seleccionar_filas_reporte(
    *,
    slug: str,
    filtros: FiltrosReporte,
    offset: int,
    limite: int,
    usuario: AbstractBaseUser | None = None,
) -> list[dict]:
    """LIMIT/OFFSET antes de list(); nunca pagina detalles en memoria."""
    if slug == "flujo-ingresos":
        return seleccionar_ingresos(
            filtros=filtros, usuario=usuario, offset=offset, limite=limite
        )
    if slug in REPORTES_COMERCIALES:
        return REPORTES_COMERCIALES[slug][1](
            filtros=filtros, usuario=usuario, offset=offset, limite=limite
        )
    if slug in REPORTES_CATALOGO:
        return REPORTES_CATALOGO[slug][1](
            filtros=filtros, usuario=usuario, offset=offset, limite=limite
        )
    if slug in REPORTES_COMPRAS_OBRA:
        return REPORTES_COMPRAS_OBRA[slug][1](
            filtros=filtros, usuario=usuario, offset=offset, limite=limite
        )
    if slug == "inventario-disponible":
        filas = list(seleccionar_inventario(filtros=filtros)[offset : offset + limite])
        for fila in filas:
            for campo in ("nombre", "ciudad", "tipo", "moneda"):
                fila[campo] = fila.pop(campo + "_reporte")
        return filas
    if slug == "documentos-por-vencer":
        filas = list(
            seleccionar_vencimientos(filtros=filtros).values(
                "id",
                "nombre",
                "tipo",
                "fecha_vencimiento",
                propiedad_codigo=F("propiedad__codigo"),
            )[offset : offset + limite]
        )
        hoy = timezone.localdate(timezone=GUATEMALA)
        for fila in filas:
            fila["propiedad"] = fila.pop("propiedad_codigo")
            fila["estado"] = (
                "VENCIDO" if fila["fecha_vencimiento"] < hoy else "POR VENCER"
            )
        return filas
    return list(
        seleccionar_bitacora(filtros=filtros).values(
            "id", "fecha", "usuario_id", "entidad", "entidad_id", "accion"
        )[offset : offset + limite]
    )
