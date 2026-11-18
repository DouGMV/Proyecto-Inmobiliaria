"""Metadatos compartidos por API, exportadores y pantalla genérica."""

from dataclasses import asdict

from django.http import Http404

from apps.auditoria.enums import AccionAuditoria
from apps.catalogo.enums import EstadoPropiedad, TipoDocumento
from apps.construccion.enums import EstadoProyecto
from apps.crm.enums import EstadoCotizacion, TipoCliente
from apps.usuarios.enums import NombreRol
from apps.ventas.enums import ModalidadVenta

from .estructuras import Columna


def filtro(nombre, etiqueta, tipo="texto", origen_opciones="", opciones=None):
    return dict(
        nombre=nombre,
        etiqueta=etiqueta,
        tipo=tipo,
        obligatorio=False,
        origen_opciones=origen_opciones,
        buscable=origen_opciones in ("/ciudades/", "/clientes/", "/agentes/"),
        opciones=opciones or [],
    )


def opciones(choices) -> list[dict]:
    return [dict(valor=v, etiqueta=e) for v, e in choices]


def filtros_periodo(prefijo: str = "") -> list[dict]:
    return [
        filtro("fecha_desde", f"{prefijo} desde", "fecha"),
        filtro("fecha_hasta", f"{prefijo} hasta", "fecha"),
    ]


PAIS = filtro("pais", "País", "entero", "/paises/")
AGENTE = filtro("agente", "Agente", "entero", "/agentes/")
MONEDA = filtro("moneda", "Moneda", "texto", "/monedas/")

CATALOGO = {
    "inventario-disponible": {
        "codigo": "R05",
        "titulo": "Inventario disponible",
        "roles": list(NombreRol.values),
        "columnas": [
            Columna("origen", "Origen"),
            Columna("id", "ID", "entero"),
            Columna("codigo", "Código"),
            Columna("nombre", "Propiedad"),
            Columna("ciudad", "Ciudad"),
            Columna("tipo", "Tipo"),
            Columna("moneda", "Moneda"),
            Columna("area_m2", "Área m²", "decimal", "#,##0.00", "right"),
            Columna("precio_lista", "Precio de lista", "decimal", "#,##0.00", "right"),
        ],
        "filtros": [
            filtro("pais", "País", "entero", "/paises/"),
            filtro("ciudad", "Ciudad", "entero", "/ciudades/"),
            filtro("tipo", "Tipo de propiedad", "entero", "/tipos-propiedad/"),
            filtro("moneda", "Moneda", "texto", "/monedas/"),
            *filtros_periodo("Registro"),
            *[
                filtro(n, e, "decimal")
                for n, e in [
                    ("precio_min", "Precio mínimo"),
                    ("precio_max", "Precio máximo"),
                    ("area_min", "Área mínima"),
                    ("area_max", "Área máxima"),
                ]
            ],
        ],
    },
    "documentos-por-vencer": {
        "codigo": "R16",
        "titulo": "Documentos por vencer",
        "roles": list(NombreRol.values),
        "columnas": [
            Columna("id", "ID", "entero"),
            Columna("propiedad", "Propiedad"),
            Columna("nombre", "Documento"),
            Columna("tipo", "Tipo"),
            Columna("fecha_vencimiento", "Vencimiento", "fecha", "dd/mm/yyyy"),
            Columna("estado", "Estado"),
        ],
        "filtros": [
            filtro("tipo", "Tipo de documento", "texto", "documentos"),
            filtro("pais", "País", "entero", "/paises/"),
            filtro("dias_anticipacion", "Días de anticipación (0 a 365)", "entero"),
        ],
    },
    "bitacora-auditoria": {
        "codigo": "R17",
        "titulo": "Bitácora de auditoría",
        "roles": [NombreRol.ADMINISTRADOR],
        "columnas": [
            Columna("id", "ID", "entero"),
            Columna("fecha", "Fecha (Guatemala)", "fecha_hora", "dd/mm/yyyy hh:mm"),
            Columna("usuario_id", "Usuario ID", "entero"),
            Columna("entidad", "Entidad"),
            Columna("entidad_id", "Entidad ID", "entero"),
            Columna("accion", "Acción"),
        ],
        "filtros": [
            filtro("usuario", "Usuario ID", "entero"),
            filtro("entidad", "Entidad"),
            filtro("accion", "Acción", "texto", "acciones"),
            filtro("fecha_desde", "Desde", "fecha"),
            filtro("fecha_hasta", "Hasta", "fecha"),
        ],
    },
    "ventas-por-periodo": {
        "codigo": "R01",
        "titulo": "Ventas por período",
        "roles": list(NombreRol.values),
        "columnas": [
            Columna("codigo", "Contrato"),
            Columna("fecha_firma", "Firma", "fecha", "dd/mm/yyyy"),
            Columna("cliente_nombre", "Cliente"),
            Columna("agente_nombre", "Agente"),
            Columna("bien", "Bien"),
            Columna("pais", "País"),
            Columna("ciudad", "Ciudad"),
            Columna("modalidad", "Modalidad"),
            Columna("moneda_codigo", "Moneda"),
            Columna("bruto", "Precio bruto", "decimal", "#,##0.00", "right"),
            Columna("descuento", "Descuento", "decimal", "#,##0.00", "right"),
            Columna("monto_total", "Neto", "decimal", "#,##0.00", "right"),
            Columna("comision_agente", "Comisión", "decimal", "#,##0.00", "right"),
        ],
        "filtros": [
            *filtros_periodo("Firma"),
            PAIS,
            filtro("ciudad", "Ciudad", "entero", "/ciudades/"),
            filtro("tipo", "Tipo de propiedad", "entero", "/tipos-propiedad/"),
            AGENTE,
            filtro("modalidad", "Modalidad", opciones=opciones(ModalidadVenta.choices)),
            MONEDA,
        ],
    },
    "desempeno-agentes": {
        "codigo": "R02",
        "titulo": "Desempeño por agente",
        "roles": list(NombreRol.values),
        "columnas": [
            Columna("codigo", "Agente"),
            Columna("nombre", "Nombre"),
            Columna("emitidas", "Cotizaciones emitidas", "entero"),
            Columna("aprobadas", "Aprobadas", "entero"),
            Columna("vinculadas", "Con contrato", "entero"),
            Columna("ventas_directas", "Ventas sin cotización", "entero"),
            Columna("conversion_pct", "Conversión %", "decimal", "#,##0.00", "right"),
            Columna("vendido_usd", "Vendido USD", "decimal", "#,##0.00", "right"),
            Columna("comision_usd", "Comisión USD", "decimal", "#,##0.00", "right"),
        ],
        "filtros": [*filtros_periodo("Período"), PAIS, AGENTE],
    },
    "embudo-cotizaciones": {
        "codigo": "R03",
        "titulo": "Embudo de cotizaciones",
        "roles": list(NombreRol.values),
        "columnas": [
            Columna("codigo", "Cotización"),
            Columna("fecha_emision", "Emisión", "fecha", "dd/mm/yyyy"),
            Columna("cliente_nombre", "Cliente"),
            Columna("agente_nombre", "Agente"),
            Columna("estado", "Estado"),
            Columna("vencida", "Vencida"),
            Columna("moneda_codigo", "Moneda"),
            Columna("total", "Total", "decimal", "#,##0.00", "right"),
            Columna("contrato", "Contrato"),
        ],
        "filtros": [
            *filtros_periodo("Emisión"),
            AGENTE,
            PAIS,
            filtro("estado", "Estado", opciones=opciones(EstadoCotizacion.choices)),
            MONEDA,
            filtro("monto_min", "Monto mínimo", "decimal"),
            filtro("monto_max", "Monto máximo", "decimal"),
        ],
    },
    "ranking-clientes": {
        "codigo": "R04",
        "titulo": "Ranking de clientes",
        "roles": list(NombreRol.values),
        "columnas": [
            Columna("codigo", "Cliente"),
            Columna("cliente_nombre", "Nombre"),
            Columna("contratos", "Contratos de venta", "entero"),
            Columna("arrendamientos_vigentes", "Arrendamientos vigentes", "entero"),
            Columna("vendido_usd", "Vendido USD", "decimal", "#,##0.00", "right"),
            Columna("saldos", "Saldo actual"),
        ],
        "filtros": [
            *filtros_periodo("Firma"),
            PAIS,
            filtro("tipo", "Tipo de cliente", opciones=opciones(TipoCliente.choices)),
        ],
    },
    "estado-cuenta-clientes": {
        "codigo": "R10",
        "titulo": "Estado de cuenta de clientes",
        "roles": list(NombreRol.values),
        "columnas": [
            Columna("cliente_nombre", "Cliente"),
            Columna("contrato_codigo", "Contrato"),
            Columna("origen", "Origen"),
            Columna("detalle", "Cuota o período"),
            Columna("fecha_vencimiento", "Vencimiento", "fecha", "dd/mm/yyyy"),
            Columna("moneda_codigo", "Moneda"),
            Columna("exigible", "Exigible", "decimal", "#,##0.00", "right"),
            Columna("pagado", "Pagado", "decimal", "#,##0.00", "right"),
            Columna("saldo", "Saldo", "decimal", "#,##0.00", "right"),
            Columna("estado", "Estado"),
            Columna("mora", "En mora"),
        ],
        "filtros": [
            filtro("cliente", "Cliente", "entero", "/clientes/"),
            *filtros_periodo("Vencimiento"),
            filtro(
                "estado",
                "Estado",
                opciones=[
                    dict(valor="PENDIENTE", etiqueta="Pendiente"),
                    dict(valor="PARCIAL", etiqueta="Pago parcial"),
                    dict(valor="PAGADO", etiqueta="Pagado"),
                ],
            ),
            AGENTE,
            MONEDA,
        ],
    },
    "morosidad": {
        "codigo": "R11",
        "titulo": "Morosidad",
        "roles": list(NombreRol.values),
        "columnas": [
            Columna("cliente_nombre", "Cliente"),
            Columna("contrato_codigo", "Contrato"),
            Columna("origen", "Origen"),
            Columna("agente_nombre", "Agente"),
            Columna("fecha_vencimiento", "Vencimiento", "fecha", "dd/mm/yyyy"),
            Columna("dias_atraso", "Días de atraso", "entero"),
            Columna("tramo", "Tramo"),
            Columna("moneda_codigo", "Moneda"),
            Columna("saldo", "Saldo", "decimal", "#,##0.00", "right"),
        ],
        "filtros": [
            PAIS,
            AGENTE,
            MONEDA,
            filtro("saldo_min", "Saldo mínimo", "decimal"),
            filtro("saldo_max", "Saldo máximo", "decimal"),
        ],
    },
}


# Reportes del catálogo (spec 021, rol A). Todos los roles (regla 7).
CIUDAD = filtro("ciudad", "Ciudad", "entero", "/ciudades/")
TIPO_PROPIEDAD = filtro("tipo", "Tipo de propiedad", "entero", "/tipos-propiedad/")

CATALOGO.update(
    {
        "propiedades-por-estado": {
            "codigo": "R06",
            "titulo": "Propiedades por estado",
            "roles": list(NombreRol.values),
            "columnas": [
                Columna("origen", "Origen"),
                Columna("id", "ID", "entero"),
                Columna("codigo", "Código"),
                Columna("nombre", "Propiedad"),
                Columna("tipo", "Tipo"),
                Columna("ciudad", "Ciudad"),
                Columna("estado", "Estado"),
                Columna("fecha_estado", "En el estado desde", "fecha", "dd/mm/yyyy"),
                Columna("dias_en_estado", "Días en el estado", "entero"),
            ],
            "filtros": [
                PAIS,
                CIUDAD,
                TIPO_PROPIEDAD,
                filtro("estado", "Estado", opciones=opciones(EstadoPropiedad.choices)),
            ],
        },
        "evolucion-avaluos": {
            "codigo": "R08",
            "titulo": "Evolución de avalúos",
            "roles": list(NombreRol.values),
            "columnas": [
                Columna("id", "ID", "entero"),
                Columna("propiedad_codigo", "Código"),
                Columna("propiedad_nombre", "Propiedad"),
                Columna("fecha", "Fecha", "fecha", "dd/mm/yyyy"),
                Columna("perito", "Perito"),
                Columna("moneda_codigo", "Moneda"),
                Columna("valor", "Valor", "decimal", "#,##0.00", "right"),
                Columna("anterior", "Avalúo anterior", "decimal", "#,##0.00", "right"),
                Columna("variacion_pct", "Variación %", "decimal", "#,##0.00", "right"),
            ],
            "filtros": [
                filtro("propiedad", "Propiedad", "entero", "/propiedades/"),
                PAIS,
                MONEDA,
                *filtros_periodo("Avalúo"),
            ],
        },
        "ocupacion-arrendamientos": {
            "codigo": "R14",
            "titulo": "Ocupación de arrendamientos",
            "roles": list(NombreRol.values),
            "columnas": [
                Columna("id", "ID", "entero"),
                Columna("codigo", "Código"),
                Columna("nombre", "Propiedad"),
                Columna("ciudad", "Ciudad"),
                Columna("tipo", "Tipo"),
                Columna("elegibles", "Bienes", "entero"),
                Columna("arrendados", "Arrendados", "entero"),
                Columna("disponibles", "Disponibles", "entero"),
                Columna("otros", "Otros estados", "entero"),
                Columna("ocupacion_pct", "Ocupación %", "decimal", "#,##0.00", "right"),
                Columna("ingreso_recurrente", "Renta mensual vigente"),
            ],
            "filtros": [PAIS, CIUDAD, TIPO_PROPIEDAD],
        },
    }
)


# Compras y construcción (spec 021, regla 7): administración, gerencia y
# contabilidad. Los hizo A en el cierre, sobre los modelos de la spec 017.
FINANZAS = [NombreRol.ADMINISTRADOR, NombreRol.GERENTE, NombreRol.CONTABILIDAD]

CATALOGO.update(
    {
        "compras-proveedores": {
            "codigo": "R13",
            "titulo": "Compras por proveedor",
            "roles": FINANZAS,
            "columnas": [
                Columna("codigo", "Contrato"),
                Columna("fecha_compra", "Compra", "fecha", "dd/mm/yyyy"),
                Columna("proveedor_nombre", "Proveedor"),
                Columna("propiedad_codigo", "Código"),
                Columna("propiedad_nombre", "Propiedad"),
                Columna("moneda_codigo", "Moneda"),
                Columna("monto", "Monto", "decimal", "#,##0.00", "right"),
                Columna(
                    "gastos_legales", "Gastos legales", "decimal", "#,##0.00", "right"
                ),
                Columna("impuestos", "Impuestos", "decimal", "#,##0.00", "right"),
                Columna("costo_total", "Costo total", "decimal", "#,##0.00", "right"),
                Columna("costo_total_usd", "Costo USD", "decimal", "#,##0.00", "right"),
            ],
            "filtros": [
                *filtros_periodo("Compra"),
                filtro("proveedor", "Proveedor", "entero", "/proveedores/"),
                PAIS,
                MONEDA,
            ],
        },
        "avance-presupuesto-obra": {
            "codigo": "R15",
            "titulo": "Avance y presupuesto de obra",
            "roles": FINANZAS,
            "columnas": [
                Columna("codigo", "Proyecto"),
                Columna("nombre", "Nombre"),
                Columna("constructora_nombre", "Constructora"),
                Columna("propiedad_codigo", "Propiedad"),
                Columna("estado", "Estado"),
                Columna("fecha_inicio", "Inicio", "fecha", "dd/mm/yyyy"),
                Columna("fecha_fin_estimada", "Fin estimado", "fecha", "dd/mm/yyyy"),
                Columna("fecha_fin_real", "Fin real", "fecha", "dd/mm/yyyy"),
                Columna("desviacion_dias", "Días de atraso", "entero"),
                Columna("moneda_codigo", "Moneda"),
                Columna(
                    "presupuesto_total", "Presupuesto", "decimal", "#,##0.00", "right"
                ),
                Columna("programado", "Programado", "decimal", "#,##0.00", "right"),
                Columna("pagado", "Pagado", "decimal", "#,##0.00", "right"),
                Columna("comprometido", "Comprometido", "decimal", "#,##0.00", "right"),
                Columna("disponible", "Disponible", "decimal", "#,##0.00", "right"),
                Columna(
                    "saldo_por_pagar", "Saldo por pagar", "decimal", "#,##0.00", "right"
                ),
                Columna("porcentaje_avance", "Avance físico %", "entero"),
                Columna(
                    "avance_financiero",
                    "Avance financiero %",
                    "decimal",
                    "#,##0.00",
                    "right",
                ),
            ],
            "filtros": [
                filtro("constructora", "Constructora", "entero", "/constructoras/"),
                filtro("estado", "Estado", opciones=opciones(EstadoProyecto.choices)),
                PAIS,
                *filtros_periodo("Inicio"),
                MONEDA,
            ],
        },
    }
)


CATALOGO["flujo-ingresos"] = {
    "codigo": "R12",
    "titulo": "Flujo de ingresos",
    "roles": FINANZAS,
    "columnas": [
        Columna("origen", "Origen"),
        Columna("id_fuente", "ID fuente", "entero"),
        Columna("contrato", "Contrato"),
        Columna("fecha", "Fecha de cobro", "fecha", "dd/mm/yyyy"),
        Columna("pais", "País del bien"),
        Columna("moneda", "Moneda"),
        Columna("recibido", "Recibido", "decimal", "#,##0.00", "right"),
        Columna("tasa_a_usd", "Tasa a USD", "decimal", "0.000000", "right"),
        Columna("monto_usd", "Recibido USD", "decimal", "#,##0.00", "right"),
    ],
    "filtros": [
        *filtros_periodo("Cobro"),
        PAIS,
        MONEDA,
        filtro(
            "origen",
            "Origen",
            opciones=[
                {"valor": v, "etiqueta": e}
                for v, e in (
                    ("CONTADO", "Venta al contado"),
                    ("ENGANCHE", "Enganche de venta"),
                    ("CUOTA", "Abono a cuota"),
                    ("RENTA", "Pago de renta"),
                )
            ],
        ),
    ],
}


def definicion_reporte(slug: str) -> dict:
    """Un slug desconocido siempre es 404."""
    if slug not in CATALOGO:
        raise Http404
    return CATALOGO[slug]


def metadatos(slug: str) -> dict:
    definicion = definicion_reporte(slug)
    filtros = []
    for filtro_actual in definicion["filtros"]:
        opciones = filtro_actual["opciones"]
        if filtro_actual["origen_opciones"] == "documentos":
            opciones = [dict(valor=v, etiqueta=e) for v, e in TipoDocumento.choices]
        elif filtro_actual["origen_opciones"] == "acciones":
            opciones = [dict(valor=v, etiqueta=e) for v, e in AccionAuditoria.choices]
        filtros.append({**filtro_actual, "opciones": opciones})
    return {
        **definicion,
        "slug": slug,
        "filtros": filtros,
        "columnas": [asdict(c) for c in definicion["columnas"]],
    }
