# 025 · Rango de fechas para inventario disponible

| Campo | Valor |
|---|---|
| Estado | Implementada y verificada localmente |
| Responsable | Nathaly Saraí Reyes Cifuentes |
| Revisión previa | Exceptuada para esta práctica |
| Fecha | 2026-11-18 |
| Apps | `reportes` |
| Rama | `Nathaly-Examen-Final` |

## 1. Problema

El reporte de inventario disponible permite filtrar por ubicación, precio y
área, pero no por la fecha de registro de cada propiedad o unidad.

## 2. Alcance

Agregar fechas desde y hasta al reporte existente y mantener los mismos
resultados en la vista previa, Excel y PDF. No crear otro reporte.

## 3. Reglas

1. Se filtra `creado_en` de cada propiedad o unidad, no la fecha del edificio.
2. Ambos extremos son opcionales y corresponden a días de Guatemala.
3. El límite inferior incluye el inicio del día y el superior incluye el día
   completo, usando la medianoche siguiente como límite exclusivo.
4. Rechazar desde mayor que hasta y hasta igual a 9999-12-31.
5. Sin fechas se conserva el comportamiento existente.
6. Pantalla, totales y archivos usan las mismas fuentes filtradas.

## 4. Datos

Sin migraciones. Se reutiliza el campo `creado_en` existente. Se agregan
`fecha_desde` y `fecha_hasta` opcionales a `FiltrosInventario`.

## 5. API

Las rutas existentes de inventario y sus exportaciones aceptan
`fecha_desde=2026-11-18&fecha_hasta=2026-11-18`. Se conservan los permisos.
El catálogo declara los controles como fechas y especifica que son de registro.

## 6. Selectores y servicios

Aplicar ambos límites en `_fuentes_inventario` antes de resumir, paginar o
exportar. Validar las fechas en `FiltrosInventarioSerializer`. Mantener las
validaciones de moneda, precio y área. Usar los exportadores existentes.

## 7. Auditoría

Solo lectura; no se modifican entidades de negocio.

## 8. Aceptación

- [x] El catálogo publica los controles de fecha de registro.
- [x] Se incluyen los dos extremos en horario de Guatemala.
- [x] Se filtran tanto propiedades como unidades.
- [x] Un rango invertido devuelve 400.
- [x] Los totales y las filas exportadas corresponden al mismo rango.
- [x] Se genera y relee el Excel; el PDF se renderiza y se revisa visualmente.

## 9. Pruebas

Verificar límites horarios, filtros de un solo extremo, rango invertido y
coincidencia de vista previa con exportación. Ejecutar las pruebas existentes
de reportes y abrir los archivos generados con datos locales.

Resultado: 160 pruebas de reportes aprobadas en Docker con las bibliotecas
nativas de WeasyPrint. Formato, Ruff y comprobación de migraciones aprobados.
La consulta local para 2026-11-18 obtiene dos registros y para 2026-11-17
obtiene cero. Excel y PDF se generaron con los dos registros del primer rango.

## 10. Decisión

Se usa la fecha de alta para acotar el inventario actual. El reporte no
reconstruye disponibilidad histórica ni usa fechas de venta o avalúo.
