"""Contratos en memoria: no crean tablas ni ejecutan consultas (spec 016)."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Columna:
    nombre: str
    etiqueta: str
    tipo: str = "texto"
    formato: str = ""
    alineacion: str = "left"


@dataclass(frozen=True)
class Grupo:
    etiqueta: str
    valores: dict


@dataclass(frozen=True)
class FiltrosInventario:
    pais: int | None = None
    ciudad: int | None = None
    tipo: int | None = None
    moneda: str | None = None
    precio_min: Decimal | None = None
    precio_max: Decimal | None = None
    area_min: Decimal | None = None
    area_max: Decimal | None = None


@dataclass(frozen=True)
class FiltrosVencimientos:
    tipo: str | None = None
    pais: int | None = None
    dias_anticipacion: int = 30


@dataclass(frozen=True)
class FiltrosBitacora:
    usuario: int | None = None
    entidad: str | None = None
    accion: str | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None


@dataclass(frozen=True)
class FiltrosVentas:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    pais: int | None = None
    ciudad: int | None = None
    tipo: int | None = None
    agente: int | None = None
    modalidad: str | None = None
    moneda: str | None = None


@dataclass(frozen=True)
class FiltrosAgentes:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    pais: int | None = None
    agente: int | None = None


@dataclass(frozen=True)
class FiltrosCotizaciones:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    agente: int | None = None
    pais: int | None = None
    estado: str | None = None
    moneda: str | None = None
    monto_min: Decimal | None = None
    monto_max: Decimal | None = None


@dataclass(frozen=True)
class FiltrosClientes:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    pais: int | None = None
    tipo: str | None = None


@dataclass(frozen=True)
class FiltrosEstadoCuenta:
    cliente: int | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    estado: str | None = None
    agente: int | None = None
    moneda: str | None = None


@dataclass(frozen=True)
class FiltrosMorosidad:
    pais: int | None = None
    agente: int | None = None
    moneda: str | None = None
    saldo_min: Decimal | None = None
    saldo_max: Decimal | None = None


@dataclass(frozen=True)
class FiltrosEstadoPropiedades:
    pais: int | None = None
    ciudad: int | None = None
    tipo: int | None = None
    estado: str | None = None
    # Serie II, inciso 7: día (de Guatemala) en que el bien entró a su estado.
    fecha_desde: date | None = None
    fecha_hasta: date | None = None


@dataclass(frozen=True)
class FiltrosAvaluos:
    propiedad: int | None = None
    pais: int | None = None
    moneda: str | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None


@dataclass(frozen=True)
class FiltrosOcupacion:
    pais: int | None = None
    ciudad: int | None = None
    tipo: int | None = None


@dataclass(frozen=True)
class FiltrosCompras:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    proveedor: int | None = None
    pais: int | None = None
    moneda: str | None = None


@dataclass(frozen=True)
class FiltrosObras:
    constructora: int | None = None
    estado: str | None = None
    pais: int | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    moneda: str | None = None


@dataclass(frozen=True)
class FiltrosIngresos:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    pais: int | None = None
    origen: str | None = None
    moneda: str | None = None


FiltrosReporte = (
    FiltrosIngresos
    | FiltrosInventario
    | FiltrosVencimientos
    | FiltrosBitacora
    | FiltrosVentas
    | FiltrosAgentes
    | FiltrosCotizaciones
    | FiltrosClientes
    | FiltrosEstadoCuenta
    | FiltrosMorosidad
    | FiltrosEstadoPropiedades
    | FiltrosAvaluos
    | FiltrosOcupacion
    | FiltrosCompras
    | FiltrosObras
)


@dataclass
class ResumenReporte:
    count: int
    totales: dict
    agrupamientos: list[Grupo] = field(default_factory=list)


@dataclass
class Reporte:
    titulo: str
    subtitulo: str
    generado_en: datetime
    generado_por: str
    columnas: list[Columna]
    filas: list[dict]
    totales: dict
    agrupamientos: list[Grupo]


@dataclass
class ReportePaginado:
    reporte: Reporte
    count: int
    pagina: int
    tamano_pagina: int = 25
