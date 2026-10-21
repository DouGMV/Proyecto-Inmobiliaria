# Plan de trabajo

## Principio rector

**Desplegar temprano, desplegar siempre.** El enunciado es explícito: los
sistemas no desplegados no serán revisados. El despliegue no es la última fase,
es la primera. Al final de la fase 1 debe existir un endpoint vivo en la nube,
aunque solo devuelva una lista de países.

El segundo riesgo más alto es el historial de Git: se evalúa el proceso, así que
el trabajo debe distribuirse en el tiempo desde ya.

---

## Reparto por responsable

Cada rol es **dueño** de un bloque de apps: es quien aprueba los pull requests
de esas apps, quien mejor debe poder defenderlas y quien decide sobre ellas.
Ser dueño no implica programarlo todo: quién implementa cada bloque está en la
tabla de reparto de trabajo, más abajo.

| Rol | Responsable | Apps y áreas | Componente de la rúbrica |
|---|---|---|---|
| **A** | DouGMV | `core`, `usuarios`, `catalogo`; despliegue e integración continua | Sistema base, arquitectura, autenticación, despliegue |
| **B** | Lilfacce | `crm`, `ventas`, `arrendamientos` | Sistema base, flujo comercial |
| **C** | AngelOvalle29 | `compras`, `construccion`, `ia` | Agente de IA y RAG |
| **D** | NathalyR15 | `reportes`, `auditoria`; mensajería (RabbitMQ y Celery) | Reportería, Power BI, RabbitMQ |

Asignado el 2026-10-14. Los nombres están como usuarios de GitHub; cada
integrante agrega su nombre real en el README.

**Responsabilidades compartidas:**
- El integrante **A** define los modelos base y las convenciones de código en la
  fase 0; el resto construye sobre eso.
- El integrante **A** monta el despliegue y la integración continua (spec 002)
  y mantiene el entorno de producción. Se movió del rol D al A al asignar los
  roles. Cualquier integrante puede colaborar en el despliegue con pull
  requests; A es quien los aprueba.
- El integrante **A** además apoya a los demás en sus apps cuando haga falta,
  siguiendo la regla de `docs/convenciones.md` §4: el cambio se marca en el
  pull request y lo aprueba el dueño de esa app.
- El integrante **D** es dueño de `auditoria`, que se creó con la spec 001: su
  primer paso es leer esa app y su sección de la spec.
- Todos revisan pull requests de todos.

### Reparto de trabajo

Decidido el 2026-10-20. La entrega es en 3 a 5 semanas (entre el 10 y el 24
de noviembre de 2026, por confirmar con el catedrático), y no alcanza para
que cada integrante construya su bloque completo a su ritmo. El integrante
**A**, con apoyo de Claude Code, implementa la mayor parte; el resto del
equipo implementa bloques autocontenidos que siguen patrones ya construidos.

Los pesos son una estimación de esfuerzo, no una medición.

| Bloque | Peso aprox. | Implementa | Revisa y aprueba |
|---|---:|---|---|
| Despliegue e integración continua (spec 002) | 5 % | A | Cualquier integrante |
| Catálogo de propiedades | 12 % | A | Cualquier integrante |
| CRM: clientes, agentes, cotizaciones | 8 % | A | **B** |
| Ventas: contratos, planes y cuotas | 8 % | A | **B** |
| Mensajería: ingesta de documentos y notificaciones | 7 % | A | **D** |
| Agente de IA y RAG | 12 % | A | **C** |
| Capa genérica de reportes y 7 reportes | 6 % | A | **D** |
| Frontend: base y pantallas principales | 13 % | A | Cualquier integrante |
| Datos de demostración y manual técnico | 3 % | A | Cualquier integrante |
| **Arrendamientos**: backend y pantallas | 9 % | **B** | A |
| **Compras y construcción**: backend y pantallas | 9 % | **C** | A |
| **Power BI** y 8 de los 15 reportes | 8 % | **D** | A |

Reparto resultante: alrededor de 74 % A y 26 % el resto del equipo.

**Por qué así:**
- A construye primero lo de mayor riesgo (despliegue, IA, mensajería) y los
  patrones que los demás copian: el CRUD de catálogo, el flujo de ventas y la
  capa genérica de reportes.
- Los bloques de B, C y D empiezan cuando su patrón exista: arrendamientos
  después de ventas, compras y construcción después de catálogo, los reportes
  después de la capa genérica. Power BI puede empezar en cuanto haya tablas.
- **Revisar es parte del trabajo de cada integrante, no un trámite.** El dueño
  de cada área revisa y aprueba lo que A implementa en ella. Es la forma de
  que cada quien pueda explicar en la defensa individual cualquier parte del
  sistema (`docs/requisitos.md` §10), incluida la que no programó.

**Ritmo de trabajo con el agente:** A implementa cada spec completa en varios
commits pequeños y la explica al cerrarla, antes de abrir el pull request.
Cada commit sigue siendo revisable por sí solo.

---

## Fases

### Fase 0 · Fundación

Objetivo: que los cuatro puedan programar sin pisarse.

- Repositorio en GitHub con ramas protegidas
- Estructura del proyecto Django con las apps vacías
- `docker-compose.yml` con PostgreSQL (con pgvector) y RabbitMQ. Redis queda
  fuera por ahora (ver `docs/arquitectura.md` §6)
- Modelo base abstracto con campos de rastro
- Entidades de `core`: país, ciudad, moneda, tipo de cambio
- Autenticación JWT y roles
- Configuración de `ruff`, `pytest` y `drf-spectacular`
- `.env.example` y archivos de requisitos

Spec: `specs/001-fundacion.md`

### Fase 1 · Despliegue mínimo

Objetivo: tener producción funcionando cuando todavía no duele arreglarla.

- Backend desplegado en Railway: API, worker, PostgreSQL y RabbitMQ
- Frontend desplegado en Vercel (al inicio, una página en blanco basta)
- Variables de entorno y secretos configurados en ambos proveedores
- Límite de gasto configurado en Railway
- Integración continua con GitHub Actions, obligatoria para fusionar
- Despliegue automático al fusionar a `main`
- Endpoint de salud (`/api/v1/health/`) respondiendo públicamente

Spec: `specs/002-despliegue.md`

### Fase 2 · Catálogo y CRM

- CRUD de propiedades, unidades, tipos, amenidades
- Avalúos y documentos oficiales (carga de archivos)
- Historial de eventos de propiedad
- CRUD de clientes y agentes
- Cotizaciones con detalle y cambios de estado
- Auditoría funcionando en todo lo anterior

### Fase 3 · Operación comercial

- Contratos de venta, planes de pago y cuotas
- Contratos de arrendamiento y pagos de renta
- Proveedores y contratos de compra
- Constructoras, proyectos, avances y pagos
- Reglas de negocio y cambios de estado de propiedades

### Fase 4 · Mensajería asíncrona

- RabbitMQ y Celery integrados
- Flujo de ingesta de documentos: subir, extraer texto, trocear, generar
  embeddings, indexar
- Flujo de notificaciones por correo con PDF adjunto
- Reintentos, manejo de errores y registro en bitácora

### Fase 5 · Agente de IA y RAG

- pgvector y modelo de embeddings
- Carga de la base documental: políticas, manuales, requisitos legales
- Recuperación por similitud con citación de fuentes
- Herramientas del agente sobre los selectores existentes
- Modo público y modo interno con permisos
- Bitácora completa del agente
- Interfaz de conversación en el frontend

### Fase 6 · Reportería y Power BI

- Capa genérica de reportes y sus exportadores
- Los 15 reportes del catálogo
- Exportación a Excel y PDF de cada uno
- Esquema `bi` con vistas en modelo estrella
- Usuario de solo lectura para Power BI
- Tableros en Power BI y archivo `.pbix` versionado

### Fase 7 · Frontend completo

Avanza en paralelo desde la fase 2, se cierra aquí.

- Autenticación y control de acceso por rol
- Pantallas de catálogo, CRM, ventas, arrendamientos y construcción
- Visor de reportes con filtros y botones de descarga
- Interfaz del agente de IA
- Consulta de bitácoras de auditoría

### Fase 8 · Cierre

- Manual técnico
- Datos de demostración realistas y abundantes
- Pruebas de extremo a extremo de los flujos principales
- Ensayo de la defensa oral con defensa cruzada
- Revisión final contra la rúbrica de `docs/requisitos.md`

---

## Dependencias entre fases

```
Fase 0 ──┬── Fase 1 (despliegue)
         │
         └── Fase 2 ──┬── Fase 3
                      │
                      ├── Fase 4 ── Fase 5
                      │
                      └── Fase 6
                      
Fase 7 avanza en paralelo desde la fase 2
```

La fase 5 depende de la 4 porque la ingesta de documentos para el RAG usa la
cola. La fase 6 necesita datos reales de las fases 2 y 3 para que los reportes
tengan sentido.

---

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El despliegue falla cerca de la entrega | Desplegar en la fase 1, mantenerlo vivo |
| La factura de Railway se dispara | Límite de gasto configurado desde el primer día |
| Historial de Git concentrado al final | Commits distribuidos, reunión semanal |
| El RAG consume más tiempo del previsto | Empezar con pocos documentos y ampliar |
| Límites de la capa gratuita de Gemini | Cache de respuestas, límite de peticiones por usuario, revisar los límites en AI Studio antes de la defensa |
| Un integrante se atrasa y bloquea al resto | Bloques verticales independientes, revisión cruzada |
| Reportes dejados para el final | La capa genérica se construye con los primeros 3 reportes, el resto es repetitivo |
| Nadie puede explicar el módulo ajeno | Defensa cruzada antes de la entrega |

---

## Antes de empezar

1. Confirmar con el catedrático que el dominio no está tomado.
2. Confirmar fechas de entrega y de defensa.
3. Confirmar con el catedrático que el frontend puede usar TypeScript. La
   restricción del enunciado aplica a la API, pero conviene dejarlo por escrito.
4. Asignar nombres reales a A, B, C y D.
5. Crear el repositorio y configurar la protección de ramas, con la
   integración continua como verificación obligatoria.
6. Crear las cuentas de Railway y Vercel, y acordar quién paga y cómo se
   reparte el costo (alrededor de $15 a $20 al mes entre cuatro).
7. Obtener la llave de la API de Gemini en Google AI Studio y confirmar ahí los
   identificadores exactos de los modelos y la dimensión de los embeddings.
8. Crear una cuenta de Gmail para el proyecto, activar la verificación en dos
   pasos y generar una contraseña de aplicación para el SMTP.
