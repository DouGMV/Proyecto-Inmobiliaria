"""
Reportes del catálogo de la spec 021: R06, R08 y R14 (rol A).

Van aparte de selectors.py, como los comerciales, para no pisarnos. Cada
reporte son dos funciones: una que agrega todo el filtro en PostgreSQL y otra
que trae solo las filas de la página. Los tres los leen todos los roles
(regla 7): el catálogo no tiene cartera.
"""

from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.base_user import AbstractBaseUser
from django.db.models import (
    Case,
    CharField,
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.fields.json import KT
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.arrendamientos.enums import EstadoArrendamiento
from apps.arrendamientos.models import ContratoArrendamiento
from apps.auditoria.models import LogAuditoria
from apps.catalogo.enums import EstadoPropiedad
from apps.catalogo.models import Propiedad, Unidad
from apps.catalogo.selectors import listar_avaluos, listar_propiedades, listar_unidades

from .estructuras import (
    FiltrosAvaluos,
    FiltrosEstadoPropiedades,
    FiltrosOcupacion,
    Grupo,
    ResumenReporte,
)

GUATEMALA = ZoneInfo("America/Guatemala")
CENTAVOS = Decimal("0.01")


def _hoy():
    """El corte de estos reportes es siempre hoy en Guatemala (regla 2)."""
    return timezone.localdate(timezone=GUATEMALA)


def _porcentaje(parte: Decimal, total: Decimal) -> Decimal | None:
    """Con denominador cero no hay porcentaje: null, no cero (reglas 13 y 17)."""
    if not total:
        return None
    return (Decimal(parte) / Decimal(total) * 100).quantize(CENTAVOS, ROUND_HALF_UP)


# ---------- R06 Propiedades por estado ----------


def _fecha_de_entrada(modelo) -> Subquery:
    """
    Regla 12: la última vez que la bitácora registró el estado actual del bien.
    Sirve un cambio de estado o la creación, si la creación guardó ese estado.
    Sin registro, null: no se usa actualizado_en, que cambia por cualquier
    edición y no dice cuándo entró al estado.
    """
    return Subquery(
        LogAuditoria.objects.filter(
            entidad=modelo._meta.db_table, entidad_id=OuterRef("pk")
        )
        # KT lee la clave del JSON como texto: así se compara con el estado.
        .annotate(estado_registrado=KT("valores_nuevos__estado"))
        .filter(estado_registrado=OuterRef("estado"))
        .order_by("-fecha", "-id")
        .values("fecha")[:1]
    )


def _bienes_por_estado(filtros: FiltrosEstadoPropiedades) -> tuple[QuerySet, QuerySet]:
    """
    Regla 12, como R05: los bienes son las propiedades cuyo tipo no lleva
    unidades, y las unidades de los tipos que sí. Un edificio no se cuenta
    además de sus unidades.
    """
    propiedades = listar_propiedades().filter(tipo__requiere_unidades=False)
    unidades = listar_unidades().filter(propiedad__tipo__requiere_unidades=True)
    fuentes = []
    for consulta, prefijo, modelo in (
        (propiedades, "", Propiedad),
        (unidades, "propiedad__", Unidad),
    ):
        for campo, valor in (
            ("ciudad__pais_id", filtros.pais),
            ("ciudad_id", filtros.ciudad),
            ("tipo_id", filtros.tipo),
        ):
            if valor is not None:
                consulta = consulta.filter(**{prefijo + campo: valor})
        if filtros.estado is not None:
            consulta = consulta.filter(estado=filtros.estado)
        consulta = consulta.order_by().annotate(fecha_estado=_fecha_de_entrada(modelo))
        fuentes.append(_filtrar_por_fecha_estado(consulta, filtros))
    return tuple(fuentes)


def _filtrar_por_fecha_estado(
    consulta: QuerySet, filtros: FiltrosEstadoPropiedades
) -> QuerySet:
    """
    Serie II, inciso 7: rango de días de Guatemala, inclusivo, sobre la fecha
    en que el bien entró a su estado actual. Igual que la bitácora (R17), el
    límite superior es el inicio del día siguiente, exclusivo: así entra todo
    el último día sin depender de la hora.

    Un bien sin historia (fecha null) no cumple ningún rango: si se pide un
    período, no se puede afirmar que entró a su estado dentro de él.
    """
    if filtros.fecha_desde is not None:
        consulta = consulta.filter(
            fecha_estado__gte=datetime.combine(
                filtros.fecha_desde, time.min, tzinfo=GUATEMALA
            )
        )
    if filtros.fecha_hasta is not None:
        consulta = consulta.filter(
            fecha_estado__lt=datetime.combine(
                filtros.fecha_hasta + timedelta(days=1), time.min, tzinfo=GUATEMALA
            )
        )
    return consulta


def resumir_estados(
    *, filtros: FiltrosEstadoPropiedades, usuario: AbstractBaseUser | None = None
) -> ResumenReporte:
    """
    Conteos por estado y tipo. La antigüedad media solo usa los bienes con
    fecha conocida, y se informa cuántos no tienen historia (regla 12).
    """
    hoy = _hoy()
    dias = ExpressionWrapper(
        Value(hoy) - TruncDate("fecha_estado", tzinfo=GUATEMALA),
        output_field=DurationField(),
    )
    grupos: dict[tuple[str, str], dict] = {}
    for consulta, prefijo in zip(
        _bienes_por_estado(filtros), ("", "propiedad__"), strict=True
    ):
        filas = consulta.values(
            "estado", tipo_reporte=F(prefijo + "tipo__nombre")
        ).annotate(
            cantidad=Count("id"),
            con_fecha=Count("fecha_estado"),
            dias=Sum(dias),
        )
        for fila in filas:
            clave = (fila["estado"], fila["tipo_reporte"])
            grupo = grupos.setdefault(
                clave,
                dict(
                    estado=fila["estado"],
                    tipo=fila["tipo_reporte"],
                    cantidad=0,
                    con_fecha=0,
                    dias=timedelta(0),
                ),
            )
            grupo["cantidad"] += fila["cantidad"]
            grupo["con_fecha"] += fila["con_fecha"]
            grupo["dias"] += fila["dias"] or timedelta(0)

    def promedio(dias: timedelta, con_fecha: int) -> Decimal | None:
        if not con_fecha:
            return None
        return (Decimal(dias.days) / con_fecha).quantize(CENTAVOS, ROUND_HALF_UP)

    cantidad = sum(g["cantidad"] for g in grupos.values())
    con_fecha = sum(g["con_fecha"] for g in grupos.values())
    dias_totales = sum((g["dias"] for g in grupos.values()), timedelta(0))
    return ResumenReporte(
        cantidad,
        dict(
            cantidad=cantidad,
            sin_historia=cantidad - con_fecha,
            dias_promedio=promedio(dias_totales, con_fecha),
        ),
        [
            Grupo(
                f"{g['estado']} / {g['tipo']}",
                dict(
                    estado=g["estado"],
                    tipo=g["tipo"],
                    cantidad=g["cantidad"],
                    sin_historia=g["cantidad"] - g["con_fecha"],
                    dias_promedio=promedio(g["dias"], g["con_fecha"]),
                ),
            )
            for _, g in sorted(grupos.items())
        ],
    )


def seleccionar_estados(
    *,
    filtros: FiltrosEstadoPropiedades,
    offset: int,
    limite: int,
    usuario: AbstractBaseUser | None = None,
) -> list[dict]:
    """UNION ALL con identidad (origen, id), como R05; LIMIT antes de list()."""
    proyecciones = []
    for consulta, origen, prefijo in zip(
        _bienes_por_estado(filtros),
        ("PROPIEDAD", "UNIDAD"),
        ("", "propiedad__"),
        strict=True,
    ):
        proyecciones.append(
            consulta.values(
                "id",
                "codigo",
                "estado",
                "fecha_estado",
                origen=Value(origen, output_field=CharField()),
                nombre_reporte=F(prefijo + "nombre"),
                tipo_reporte=F(prefijo + "tipo__nombre"),
                ciudad_reporte=F(prefijo + "ciudad__nombre"),
            )
        )
    union = proyecciones[0].union(proyecciones[1], all=True).order_by("origen", "id")
    hoy = _hoy()
    filas = list(union[offset : offset + limite])
    for fila in filas:
        for campo in ("nombre", "tipo", "ciudad"):
            fila[campo] = fila.pop(campo + "_reporte")
        fecha = fila.pop("fecha_estado")
        fila["fecha_estado"] = fecha.astimezone(GUATEMALA).date() if fecha else None
        fila["dias_en_estado"] = (
            (hoy - fila["fecha_estado"]).days if fila["fecha_estado"] else None
        )
    return filas


# ---------- R08 Evolución de avalúos ----------


def _avaluos(filtros: FiltrosAvaluos) -> QuerySet:
    consulta = listar_avaluos()
    for campo, valor in (
        ("propiedad_id", filtros.propiedad),
        ("propiedad__ciudad__pais_id", filtros.pais),
        ("moneda__codigo", filtros.moneda),
        ("fecha__gte", filtros.fecha_desde),
        ("fecha__lte", filtros.fecha_hasta),
    ):
        if valor is not None:
            consulta = consulta.filter(**{campo: valor})
    return consulta


def _anterior_comparable() -> Subquery:
    """
    Regla 13: el avalúo anterior de la misma propiedad y moneda, con orden
    (fecha, id). Se busca entre todos los avalúos activos, no solo los del
    período: el primero del período también tiene anterior si lo hubo antes.
    """
    return Subquery(
        listar_avaluos()
        .filter(propiedad=OuterRef("propiedad"), moneda=OuterRef("moneda"))
        .filter(
            Q(fecha__lt=OuterRef("fecha"))
            | Q(fecha=OuterRef("fecha"), id__lt=OuterRef("id"))
        )
        .order_by("-fecha", "-id")
        .values("valor")[:1]
    )


def _variacion(nuevo: Decimal | None, anterior: Decimal | None) -> Decimal | None:
    """Regla 13: (nuevo / anterior − 1) × 100; sin anterior o con cero, null."""
    if nuevo is None or not anterior:
        return None
    return ((nuevo / anterior - 1) * 100).quantize(CENTAVOS, ROUND_HALF_UP)


def resumir_avaluos(
    *, filtros: FiltrosAvaluos, usuario: AbstractBaseUser | None = None
) -> ResumenReporte:
    """
    Por propiedad y moneda: la primera y la última valuación del período y su
    variación. Nunca compara monedas distintas (regla 13).
    """
    base = _avaluos(filtros)
    mismo_grupo = _avaluos(filtros).filter(
        propiedad=OuterRef("propiedad"), moneda=OuterRef("moneda")
    )
    grupos = (
        base.order_by()
        .values("propiedad", "moneda")
        .annotate(
            propiedad_codigo=F("propiedad__codigo"),
            moneda_codigo=F("moneda__codigo"),
            cantidad=Count("id"),
            primera=Subquery(mismo_grupo.order_by("fecha", "id").values("valor")[:1]),
            ultima=Subquery(mismo_grupo.order_by("-fecha", "-id").values("valor")[:1]),
        )
        .order_by("propiedad__codigo", "moneda__codigo")
    )
    cantidad = base.count()
    return ResumenReporte(
        cantidad,
        dict(
            cantidad=cantidad,
            propiedades=base.values("propiedad").distinct().count(),
        ),
        [
            Grupo(
                f"{g['propiedad_codigo']} / {g['moneda_codigo']}",
                dict(
                    propiedad=g["propiedad_codigo"],
                    moneda=g["moneda_codigo"],
                    cantidad=g["cantidad"],
                    primera=g["primera"],
                    ultima=g["ultima"],
                    variacion_pct=_variacion(g["ultima"], g["primera"])
                    if g["cantidad"] > 1
                    else None,
                ),
            )
            for g in grupos
        ],
    )


def seleccionar_avaluos(
    *,
    filtros: FiltrosAvaluos,
    offset: int,
    limite: int,
    usuario: AbstractBaseUser | None = None,
) -> list[dict]:
    filas = list(
        _avaluos(filtros)
        .annotate(anterior=_anterior_comparable())
        .order_by("propiedad__codigo", "fecha", "id")
        .values(
            "id",
            "fecha",
            "perito",
            "valor",
            "anterior",
            propiedad_codigo=F("propiedad__codigo"),
            propiedad_nombre=F("propiedad__nombre"),
            moneda_codigo=F("moneda__codigo"),
        )[offset : offset + limite]
    )
    for fila in filas:
        fila["variacion_pct"] = _variacion(fila["valor"], fila["anterior"])
    return filas


# ---------- R14 Ocupación de arrendamientos ----------


def _contar_unidades(**condiciones) -> Coalesce:
    """Unidades activas de cada propiedad que cumplen las condiciones."""
    return Coalesce(
        Subquery(
            listar_unidades()
            .filter(propiedad=OuterRef("pk"), **condiciones)
            .order_by()
            .values("propiedad")
            .annotate(cantidad=Count("id"))
            .values("cantidad")[:1],
            output_field=IntegerField(),
        ),
        0,
    )


def _propiedades_ocupacion(filtros: FiltrosOcupacion) -> QuerySet:
    """
    Regla 17: el denominador son los bienes activos elegibles. Un edificio
    cuenta sus unidades; las demás propiedades se cuentan a sí mismas.
    Disponible es el estado DISPONIBLE, no el total menos los arrendados.
    """
    consulta = listar_propiedades()
    for campo, valor in (
        ("ciudad__pais_id", filtros.pais),
        ("ciudad_id", filtros.ciudad),
        ("tipo_id", filtros.tipo),
    ):
        if valor is not None:
            consulta = consulta.filter(**{campo: valor})
    arrendada, disponible = EstadoPropiedad.ARRENDADA, EstadoPropiedad.DISPONIBLE
    return consulta.order_by().annotate(
        elegibles=_si_unidades(_contar_unidades(), Value(1)),
        arrendados=_si_unidades(
            _contar_unidades(estado=arrendada), _uno_si_estado(arrendada)
        ),
        disponibles=_si_unidades(
            _contar_unidades(estado=disponible), _uno_si_estado(disponible)
        ),
    )


def _si_unidades(con_unidades, sin_unidades) -> Case:
    """Lo que vale para un edificio (sus unidades) o para cualquier otro bien."""
    return Case(
        When(tipo__requiere_unidades=True, then=con_unidades),
        default=sin_unidades,
        output_field=IntegerField(),
    )


def _uno_si_estado(estado: str) -> Case:
    """1 si la propiedad misma está en ese estado: un bien sin unidades."""
    return Case(When(estado=estado, then=Value(1)), default=Value(0))


def _contratos_que_cubren_hoy() -> QuerySet:
    """
    Regla 17: los contratos cuya renta se cobra hoy. Cubren hoy por fechas, no
    están rescindidos a esa fecha, y un RENOVADO cuya renovación se rescindió
    no cuenta aunque sus fechas cubran hoy. Una renovación que empieza después
    no se suma al contrato anterior: las fechas no se cruzan.
    """
    hoy = _hoy()
    return (
        ContratoArrendamiento.objects.filter(
            activo=True, fecha_inicio__lte=hoy, fecha_fin__gte=hoy
        )
        .exclude(estado=EstadoArrendamiento.RESCINDIDO, fecha_rescision__lte=hoy)
        .exclude(
            estado=EstadoArrendamiento.RENOVADO,
            renovacion__estado=EstadoArrendamiento.RESCINDIDO,
        )
        .annotate(propiedad_raiz=Coalesce("propiedad_id", "unidad__propiedad_id"))
    )


def _ingresos_por_propiedad(ids: list[int]) -> dict[int, dict[str, Decimal]]:
    """Renta de hoy de cada propiedad, separada por moneda: no se suman monedas."""
    ingresos: dict[int, dict[str, Decimal]] = defaultdict(dict)
    filas = (
        _contratos_que_cubren_hoy()
        .filter(propiedad_raiz__in=ids)
        .values("propiedad_raiz", "moneda__codigo")
        .annotate(total=Sum("renta_mensual"))
    )
    for fila in filas:
        ingresos[fila["propiedad_raiz"]][fila["moneda__codigo"]] = fila["total"]
    return ingresos


def _texto_por_moneda(montos: dict[str, Decimal]) -> str:
    return " · ".join(
        f"{moneda} {monto:,.2f}" for moneda, monto in sorted(montos.items())
    )


def resumir_ocupacion(
    *, filtros: FiltrosOcupacion, usuario: AbstractBaseUser | None = None
) -> ResumenReporte:
    """
    Ocupación ponderada: arrendados sobre elegibles de todo el filtro, no el
    promedio de los porcentajes de cada propiedad. Por ciudad, igual. El
    ingreso recurrente va por moneda.
    """
    propiedades = _propiedades_ocupacion(filtros)
    # Los nombres de las sumas no pueden repetir los de las anotaciones.
    totales = propiedades.aggregate(
        total_elegibles=Coalesce(Sum("elegibles"), 0),
        total_arrendados=Coalesce(Sum("arrendados"), 0),
        total_disponibles=Coalesce(Sum("disponibles"), 0),
    )
    elegibles = totales["total_elegibles"]
    arrendados = totales["total_arrendados"]
    disponibles = totales["total_disponibles"]
    por_ciudad = (
        propiedades.values(ciudad_reporte=F("ciudad__nombre"))
        .annotate(
            ciudad_elegibles=Sum("elegibles"),
            ciudad_arrendados=Sum("arrendados"),
        )
        .order_by("ciudad__nombre")
    )
    ingresos = (
        _contratos_que_cubren_hoy()
        .filter(propiedad_raiz__in=propiedades.values("id"))
        .values("moneda__codigo")
        .annotate(total=Sum("renta_mensual"))
        .order_by("moneda__codigo")
    )
    cantidad = propiedades.count()
    return ResumenReporte(
        cantidad,
        dict(
            cantidad=cantidad,
            elegibles=elegibles,
            arrendados=arrendados,
            disponibles=disponibles,
            otros=elegibles - arrendados - disponibles,
            ocupacion_pct=_porcentaje(arrendados, elegibles),
            ingreso_por_moneda={i["moneda__codigo"]: i["total"] for i in ingresos},
        ),
        [
            Grupo(
                c["ciudad_reporte"],
                dict(
                    ciudad=c["ciudad_reporte"],
                    elegibles=c["ciudad_elegibles"],
                    arrendados=c["ciudad_arrendados"],
                    ocupacion_pct=_porcentaje(
                        c["ciudad_arrendados"], c["ciudad_elegibles"]
                    ),
                ),
            )
            for c in por_ciudad
        ],
    )


def seleccionar_ocupacion(
    *,
    filtros: FiltrosOcupacion,
    offset: int,
    limite: int,
    usuario: AbstractBaseUser | None = None,
) -> list[dict]:
    filas = list(
        _propiedades_ocupacion(filtros)
        .order_by("codigo", "id")
        .values(
            "id",
            "codigo",
            "nombre",
            "elegibles",
            "arrendados",
            "disponibles",
            ciudad_reporte=F("ciudad__nombre"),
            tipo_reporte=F("tipo__nombre"),
        )[offset : offset + limite]
    )
    ingresos = _ingresos_por_propiedad([fila["id"] for fila in filas])
    for fila in filas:
        fila["ciudad"] = fila.pop("ciudad_reporte")
        fila["tipo"] = fila.pop("tipo_reporte")
        fila["otros"] = fila["elegibles"] - fila["arrendados"] - fila["disponibles"]
        fila["ocupacion_pct"] = _porcentaje(fila["arrendados"], fila["elegibles"])
        fila["ingreso_recurrente"] = _texto_por_moneda(ingresos.get(fila["id"], {}))
    return filas


REPORTES_CATALOGO = {
    "propiedades-por-estado": (resumir_estados, seleccionar_estados),
    "evolucion-avaluos": (resumir_avaluos, seleccionar_avaluos),
    "ocupacion-arrendamientos": (resumir_ocupacion, seleccionar_ocupacion),
}
