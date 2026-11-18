# 027 · Manual de visitas en el RAG

| Campo | Valor |
|---|---|
| Estado | Implementada, pendiente de comprobación final |
| Responsable | Nathaly Saraí Reyes Cifuentes |
| Revisión previa | Exceptuada para esta práctica |
| Fecha | 2026-11-18 |
| Apps | `ia` |
| Rama | `Nathaly-Examen-Final` |

## 1. Problema

El agente necesita una fuente sobre la solicitud de visitas de demostración.

## 2. Alcance

Agregar el manual ficticio a los documentos versionados y al comando
`cargar_demo_ia`. Mantener las funciones existentes de indexación y consulta.

## 3. Reglas

El documento se identifica como ficticio y establece 24 horas de anticipación
para las visitas de demostración. La respuesta debe citar ese manual.
La carga repetida no debe duplicar el documento ni sus fragmentos.

## 4. Datos y API

Sin cambios al esquema ni a las rutas. Usar `DocumentoRAG`, `FragmentoRAG`
y el endpoint público de consultas existente.

## 5. Servicios y auditoría

Usar la carga e indexación existentes, que registran creación, cambios y
consulta en auditoría. El archivo fuente se incluye en `documentos_demo`.

## 6. Criterios de aceptación

- [x] El manual queda versionado y registrado en `DOCUMENTOS_DEMO`.
- [x] La base local contiene el manual indexado con cuatro fragmentos.
- [x] Una consulta real responde 24 horas y cita el manual.
- [ ] Las pruebas de carga repetida siguen funcionando con el documento nuevo.

## 7. Pruebas

Ejecutar las pruebas existentes de datos de demostración y una consulta real.
Verificar que el archivo coincide con el contenido del documento ya indexado.

## 8. Decisión

La ingesta conserva el flujo existente; no se crea un segundo indexador.
