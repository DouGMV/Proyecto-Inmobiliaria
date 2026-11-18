# 026 · Herramienta de inventario disponible para el agente

| Campo | Valor |
|---|---|
| Estado | En implementación |
| Responsable | Nathaly Saraí Reyes Cifuentes |
| Revisión previa | Exceptuada para esta práctica |
| Fecha | 2026-11-18 |
| Apps | `ia` |
| Rama | `Nathaly-Examen-Final` |

## 1. Problema

El agente responde con documentos, pero no consulta el número actual de bienes
disponibles en la base de datos.

## 2. Alcance

Agregar `contar_inventario_disponible`, disponible para preguntas públicas
sobre cantidad de inventario o bienes disponibles. Conservar el flujo RAG
para las demás preguntas. Sin migraciones ni dependencias nuevas.

## 3. Reglas

1. Contar propiedades activas disponibles que no requieren unidades y unidades
   activas disponibles de edificios activos que requieren unidades.
2. No contar el edificio junto con sus unidades. Devolver propiedades, unidades
   y total, sin datos personales ni precios.
3. El modelo debe solicitar la herramienta; el servidor consulta PostgreSQL y
   devuelve el resultado al modelo para redactar la respuesta.
4. Solo se ejecutan herramientas declaradas con su función autorizada.
   Esta herramienta no acepta argumentos.
5. Limitar el intercambio a tres respuestas del proveedor y registrar todas
   las invocaciones efectivamente ejecutadas, incluso si falla la red después.
6. Una respuesta numérica requiere al menos una invocación real; si no existe,
   se devuelve indisponibilidad en lugar de aceptar un conteo inventado.
7. Mantener las citas de documentos en las consultas RAG y la IP de auditoría.

## 4. Datos

Reutilizar `LogAgenteIA.herramientas_invocadas`: nombre, argumentos y resultado.
Agregar una función ejecutable opcional al contrato en memoria `Herramienta`.

## 5. API

Usar `POST /api/v1/agente/consultas/` con los permisos y el contrato existentes.
Ejemplo de pregunta: `¿Cuántos bienes disponibles hay actualmente en inventario?`.

## 6. Servicios y selectores

El selector de IA lee el catálogo mediante sus selectores públicos de dominio.
El servicio declara la herramienta y registra su ejecución. El proveedor
Gemini traduce llamadas y resultados al SDK, sin consultar modelos de negocio.

## 7. Auditoría

Guardar la pregunta, respuesta, IP, tokens acumulados, duración e invocaciones
con sus resultados. Ninguna clave ni dato personal se envía en la herramienta.

## 8. Aceptación

- [ ] Una pregunta de conteo provoca una solicitud de herramienta del modelo.
- [ ] La función consulta el estado actual de la base y el conteo coincide.
- [ ] La invocación y su resultado quedan en auditoría.
- [ ] Se rechazan nombres desconocidos y argumentos no admitidos.
- [ ] El flujo de documentos y citas continúa funcionando.

## 9. Pruebas

Probar conteo sin duplicar edificios, activos y estados; intercambio de
llamada y resultado; límites, herramienta desconocida y argumentos inválidos;
auditoría exitosa y fallida. Comprobar una consulta con Gemini real.

## 10. Decisiones

Las preguntas que mencionan inventario, o disponibilidad junto a cantidades,
usan el flujo de herramientas. El resto conserva el flujo RAG y su respuesta
sin información. El SDK permanece encapsulado en `proveedores/`.
