# 024 · Dirección IP en la auditoría de consultas del agente

| Campo | Valor |
|---|---|
| Estado | Implementada y verificada localmente |
| Responsable | Nathaly Saraí Reyes Cifuentes |
| Revisor | Revisión previa exceptuada para esta práctica |
| Fecha | 2026-11-18 |
| Apps afectadas | `auditoria`, `ia` |
| Rama | `Nathaly-Examen-Final` |
| Pull request | Pendiente |

## 1. Problema

La tabla `auditoria_log_agente` registra las preguntas y el consumo del agente,
pero no la dirección IP que originó la consulta.

## 2. Alcance

Agregar la IP a las consultas nuevas del agente y mostrarla en Django admin.
No modificar registros anteriores ni cambiar el contrato público de respuesta.

## 3. Reglas de negocio

1. El campo acepta IPv4 e IPv6 y puede quedar nulo cuando no hay petición HTTP.
2. La vista obtiene la IP con `obtener_ip_cliente`, respetando `NUM_PROXIES`.
3. La IP se conserva tanto en consultas exitosas como en fallidas.
4. No se envía la IP al proveedor de IA ni se incluye en la respuesta pública.
5. Los registros existentes conservan su valor nulo y su inmutabilidad.

## 4. Modelo de datos

Agregar `ip = models.GenericIPAddressField(null=True, blank=True)` a
`LogAgenteIA`. Crear una migración nueva en `auditoria`.

## 5. API

`POST /api/v1/agente/consultas/` mantiene su petición, respuesta y permisos.
La IP se obtiene de la conexión HTTP; el usuario no la proporciona en el JSON.

## 6. Servicios y selectores

Agregar `ip: str | None = None` a `registrar_consulta_agente`,
`responder_consulta_publica` y `_registrar_en_bitacora`. Transmitir el valor
desde la vista hasta la inserción del registro. Sin selectores nuevos.

## 7. Auditoría

Cada consulta nueva guarda su IP en la misma fila de `LogAgenteIA`.
Los procesos sin contexto HTTP pueden seguir omitiendo el parámetro.

## 8. Criterios de aceptación

- [x] La migración agrega la columna nullable sin actualizar registros anteriores.
- [x] Una petición HTTP local registra `127.0.0.1`.
- [x] La dirección no aparece en el JSON público del agente.
- [x] Se conserva la IP si falla el proveedor.
- [x] Una llamada desde consola sin IP continúa funcionando.
- [x] Django admin incluye la IP en su configuración de columnas.

## 9. Pruebas

Pruebas del servicio de auditoría, de consulta del agente y de la vista.
Cubrir transmisión de IP, fallo del proveedor y compatibilidad sin IP.
Verificar también una petición HTTP local y consultar su fila guardada.

Validación local: 69 pruebas aprobadas en los módulos de registro de auditoría,
API del agente y consulta del agente. Ruff sin errores; no hay migraciones
pendientes de generar. Petición HTTP real al puerto 8001 respondida con éxito
y registrada con IP `127.0.0.1`.

## 10. Decisiones

Reutilizar el helper existente para interpretar las cabeceras del proxy.
Usar un campo de IP validado en lugar de texto libre. Mantener el parámetro
opcional para las llamadas existentes desde consola y las tareas.
