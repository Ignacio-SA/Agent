# Arquitectura del Chatbot Multi-Agente

## Índice
1. [Visión general](#1-visión-general)
2. [Estructura de carpetas](#2-estructura-de-carpetas)
3. [Flujo de una consulta](#3-flujo-de-una-consulta)
4. [Componentes en detalle](#4-componentes-en-detalle)
5. [Bases de datos](#5-bases-de-datos)
6. [Cómo construirlo desde cero](#6-cómo-construirlo-desde-cero)
7. [Variables de entorno](#7-variables-de-entorno)
8. [Decisiones de diseño importantes](#8-decisiones-de-diseño-importantes)
9. [Sistema de Entrenamiento (Training Mode)](#9-sistema-de-entrenamiento-training-mode)

---

## 1. Visión general

El sistema es un chatbot orientado a **franquiciados** que pueden consultar sus datos de ventas en lenguaje natural. El backend es una API FastAPI con un sistema multi-agente donde cada agente tiene una responsabilidad específica.

```
Usuario (HTML) ──POST /chat──► Orchestrator ──► Agente correcto ──► Respuesta
```

El chatbot se conecta a un **Microsoft Fabric Warehouse** para traer datos de ventas, los carga en **SQLite en memoria**, genera SQL con un LLM y formatea la respuesta en lenguaje natural.

---

## 2. Estructura de carpetas

```
Agent/
├── app/                          # Código principal de la aplicación
│   ├── main.py                   # Punto de entrada FastAPI
│   ├── config.py                 # Variables de entorno (via pydantic-settings)
│   ├── agents/                   # Los agentes de IA
│   │   ├── orchestrator.py       # Decide qué agente responde cada mensaje
│   │   ├── data_agent.py         # Consulta y analiza datos de ventas
│   │   ├── interaction.py        # Responde conversación general del negocio
│   │   ├── memory_agent.py       # Genera y recupera resúmenes de sesión
│   │   └── training_agent.py     # Analiza feedback y genera sugerencias de mejora
│   ├── routers/
│   │   └── chat.py               # Endpoints HTTP de la API
│   ├── db/
│   │   ├── connection.py         # Conexión a Fabric Warehouse (pyodbc + Azure AD)
│   │   ├── sales_repo.py         # Ejecuta el SP de ventas
│   │   ├── memory_repo.py        # CRUD de sesiones y mensajes (SQLite local)
│   │   └── training_repo.py      # Singleton TrainingMemory (RAM + disco)
│   └── models/
│       ├── schemas.py            # Modelos de request/response (Pydantic)
│       └── memory.py             # Modelo de la entidad MemoryEntry
├── context/
│   ├── business_rules.md         # Reglas de negocio que leen los agentes en runtime
│   └── training_log.md           # Log append-only de sugerencias de entrenamiento
├── sql/
│   ├── sp_GetSalesForChatbot.sql  # Stored Procedure en Fabric Warehouse
│   └── create_chatbot_memory.sql  # Script auxiliar (referencia)
├── ui_test/
│   └── index.html                # UI de prueba (chat + panel de sesiones + toggle entrenamiento)
├── memory.db                     # SQLite local (se crea automáticamente)
├── .env                          # Variables de entorno (NO commitear)
├── .env.example                  # Plantilla de variables de entorno
└── requirements.txt              # Dependencias Python
```

---

## 3. Flujo de una consulta

### Paso a paso

```
1. Usuario escribe un mensaje en index.html
        │
        ▼
2. POST /chat  →  chat.py::chat()
        │
        ▼
3. OrchestratorAgent.decide_agent(mensaje)
   ├─ "data"       → DataAgent
   ├─ "interaction" → InteractionAgent
   ├─ "off_topic"  → Respuesta fija (sin LLM, 0 tokens de generación)
   └─ "memory"     → Devuelve resumen guardado
        │
        ▼ (si es "data")
4. DataAgent.process_data_request()
   │
   ├─ a) sales_repo.get_sales(franchise_code)
   │       └─ EXEC sp_GetSalesForChatbot @FranchiseCode=?
   │           └─ Retorna rows del Fabric Warehouse
   │
   ├─ b) _load_into_memory(sales)
   │       └─ Crea tabla SQLite en RAM con los datos
   │           └─ Decodifica DATETIMEOFFSET (20 bytes raw) con struct.unpack
   │
   ├─ c) _generate_sql(user_message)
   │       └─ LLM (Haiku) genera SQL SQLite
   │           └─ Incluye business_rules.md como contexto del sistema
   │
   ├─ d) _execute_sql(conn, sql)
   │       └─ Ejecuta la consulta sobre SQLite en memoria
   │
   └─ e) _format_response(user_message, sql, columns, rows)
           └─ LLM (Haiku) convierte los resultados a lenguaje natural
               └─ Incluye business_rules.md para no mostrar datos técnicos
        │
        ▼
5. chat.py guarda los mensajes en SQLite local (chat_messages)
   y actualiza el resumen de sesión (memory_agent.save_memory)
        │
        ▼
6. Respuesta JSON → index.html → Renderiza en el chat
```

---

## 4. Componentes en detalle

### `app/agents/orchestrator.py` — El portero

Usa **Claude Sonnet** para clasificar cada mensaje en una de estas categorías:

| Tipo | Cuándo | Costo |
|------|--------|-------|
| `data` | Consultas de ventas, productos, precios, reportes | Alto (3 llamadas LLM) |
| `interaction` | Saludos, preguntas sobre el chatbot | Bajo (1 llamada LLM, 200 tokens) |
| `off_topic` | Todo lo demás | Cero (respuesta hardcodeada) |
| `memory` | "¿Qué hablamos antes?" | Bajo (solo lectura de DB) |

El fallback por keywords evita llamadas extra si el LLM falla en retornar JSON válido.

---

### `app/agents/data_agent.py` — El analista

Es el agente más complejo. Implementa un pipeline **Text-to-SQL**:

```
Pregunta en español
      │
      ▼
LLM genera SQL (SQLite syntax) con reglas de negocio inyectadas
      │
      ▼
SQL ejecutado contra tabla en RAM (datos frescos del SP)
      │
      ▼
LLM formatea resultado como respuesta natural para el usuario
```

**Punto crítico — DATETIMEOFFSET:** `pyodbc` retorna las fechas del Fabric Warehouse como 20 bytes raw. Hay que decodificarlos con:
```python
struct.unpack('<hHHHHHIhh', v)
# → year, month, day, hour, minute, second, fraction_ns, tz_h, tz_m
```

**Punto crítico — SQLite:** La tabla en memoria usa comillas en todos los nombres de columna (`"Type" TEXT`) porque `Type` es palabra reservada en SQLite.

---

### `app/agents/interaction.py` — El recepcionista

Responde saludos y preguntas sobre el chatbot. Usa Haiku con `max_tokens=200`. Si detecta algo fuera de scope, da una respuesta corta fija sin gastar tokens adicionales (el filtro real lo hace el Orchestrator con `off_topic`).

---

### `app/agents/memory_agent.py` — La memoria

- **`save_memory()`**: Al final de cada conversación, pide a Haiku que genere un resumen de 2-3 puntos y lo guarda en SQLite.
- **`retrieve_memory()`**: Al inicio de cada request, carga el resumen de la sesión para dárselo como contexto a los agentes.

> El resumen es diferente al historial completo. El historial mensaje-a-mensaje se guarda en `chat_messages` via `memory_repo.save_message()`.

---

### `app/agents/training_agent.py` — El analista de feedback

Agente basado en Claude Haiku que implementa el ciclo de aprendizaje supervisado:

- **`process_feedback()`**: Recibe el `session_id`, el historial de la sesión y el mensaje de feedback del usuario. Analiza el ciclo completo (pregunta → respuesta → feedback) y genera una sugerencia estructurada en JSON.
- Identifica el **componente afectado** (`data_agent`, `orchestrator`, `interaction`, `business_rules`) y la **causa raíz** del problema o acierto.
- Guarda la sugerencia en `TrainingMemory` (RAM) y hace append a `context/training_log.md` (disco).
- En caso de error al parsear el JSON del LLM, genera un fallback manual para no perder el feedback.

> El training_agent **nunca modifica** archivos de código ni `business_rules.md`. Solo escribe en `training_log.md`. Las sugerencias son revisadas por un humano antes de aplicarse.

---

### `app/db/training_repo.py` — TrainingMemory

Singleton con doble storage:

- **RAM** (`self._context: list[dict]`): Últimas 20 sugerencias para inyección inmediata en prompts.
- **Disco** (`context/training_log.md`): Append-only de todas las sugerencias históricas.

| Método | Cuándo se llama | Qué hace |
|---|---|---|
| `load_from_disk()` | Al iniciar la app (`main.py`) | Lee `training_log.md` y carga las últimas 20 en RAM |
| `add_suggestion(dict)` | Por `training_agent` en cada feedback | Agrega a RAM + append en disco |
| `get_context_for_prompt()` | Por `orchestrator` si `training_mode=True` | Devuelve string formateado para inyectar en system prompts |
| `get_recent_entries(n)` | Por `training_agent` al analizar | Provee contexto de sugerencias previas para evitar repetición |

---

### `app/db/connection.py` — La conexión a Fabric

Soporta tres modos de autenticación configurables via `.env`:

| Modo (`DB_AUTH_MODE`) | Cuándo usar |
|---|---|
| `sql` | Usuario y contraseña SQL directos |
| `activedirectoryinteractive` | Login Azure AD con popup MFA en el browser |
| `activedirectoryintegrated` | Azure AD integrado (Windows Auth, sin popup) |

El token Azure AD se reutiliza (singleton `_credential`) para no pedir MFA en cada request.

La línea `conn.add_output_converter(-155, lambda x: x)` le dice a pyodbc que **no convierta** el tipo DATETIMEOFFSET (-155) y lo entregue como bytes raw, lo que permite decodificarlo con `struct.unpack` en el DataAgent.

---

### `app/db/memory_repo.py` — Persistencia local

SQLite local (`memory.db`) con dos tablas:

**`chatbot_memory`** — Un registro por sesión con el resumen:
```
session_id | user_id | context | summary | created_at | updated_at
```

**`chat_messages`** — Historial completo, un registro por mensaje:
```
id | session_id | role | content | agent_type | created_at
```

---

### `context/business_rules.md` — Las reglas del negocio

Archivo Markdown leído en **runtime** por el DataAgent en cada consulta. No requiere reiniciar el servidor para actualizarse.

Reglas clave que contiene:
- `Type=1` → ítem unitario (incluir en sumas), `Type=2` → cabecera de promo (excluir)
- Siempre `WHERE "Type" = '1'` en agregaciones
- Búsqueda de artículos: `LOWER(ArticleDescription) LIKE LOWER('%texto%')`
- Nunca mostrar nombres técnicos de columnas al usuario
- Cómo presentar franjas horarias de manera legible

---

### `sql/sp_GetSalesForChatbot.sql` — El Stored Procedure

Corre en **Microsoft Fabric Warehouse**. Puntos críticos:

```sql
-- Conversión de UTC a UTC-3 (Argentina)
SWITCHOFFSET(TRY_CONVERT(DATETIMEOFFSET, d.SaleDateTimeUtc), '-03:00') AS SaleDateTimeUtc

-- Filtro correcto: FranchiseCode (sin doble 'e'), no FranchiseeCode
WHERE h.FranchiseCode = @FranchiseCode
```

> **Atención:** `FranchiseCode` y `FranchiseeCode` son **dos columnas distintas** con valores diferentes. El filtro va sobre `FranchiseCode`.

---

## 5. Bases de datos

| Base de datos | Tecnología | Dónde vive | Para qué |
|---|---|---|---|
| Warehouse | Microsoft Fabric | Cloud | Datos de ventas (fuente de verdad) |
| SQLite en memoria | sqlite3 | RAM del servidor | Tabla temporal por consulta (se destruye al terminar) |
| SQLite local | sqlite3 | `memory.db` en disco | Sesiones, historial de mensajes |
| Training Log | Markdown | `context/training_log.md` en disco | Sugerencias de mejora (append-only, revisión humana) |
| Training Memory | Python list | RAM del servidor | Últimas 20 sugerencias para inyectar en prompts |

---

## 6. Cómo construirlo desde cero

### Paso 1 — Prerrequisitos

```bash
# Python 3.11+
python -m venv venv
venv\Scripts\activate  # Windows

pip install fastapi uvicorn anthropic pydantic-settings pyodbc azure-identity python-dotenv
```

Instalar **ODBC Driver 17 for SQL Server** desde Microsoft.

---

### Paso 2 — Variables de entorno

Crear `.env` (ver `.env.example`):

```env
ANTHROPIC_API_KEY=sk-ant-...
DB_SERVER=tu-server.database.fabric.microsoft.com
DB_DATABASE=nombre_de_tu_warehouse
DB_USER=tu@email.com
DB_AUTH_MODE=activedirectoryinteractive
MEMORY_DB_PATH=./memory.db
```

---

### Paso 3 — Estructura mínima viable

Para empezar con lo mínimo necesario, crear en orden:

```
1. app/config.py          → Leer variables de entorno con pydantic-settings
2. app/db/connection.py   → Conexión pyodbc a Fabric
3. app/db/memory_repo.py  → SQLite local + init_memory_db()
4. app/models/schemas.py  → ChatRequest, ChatResponse (Pydantic)
5. app/agents/orchestrator.py → Clasificar mensajes con LLM
6. app/agents/data_agent.py   → Pipeline text-to-SQL
7. app/agents/interaction.py  → Respuestas de conversación
8. app/agents/memory_agent.py → Resúmenes de sesión
9. app/routers/chat.py    → Endpoint POST /chat
10. app/main.py           → FastAPI app + CORS + montar router
```

---

### Paso 4 — El Stored Procedure en Fabric

Ejecutar `sql/sp_GetSalesForChatbot.sql` en el Fabric Warehouse. Siempre usar `DROP PROCEDURE IF EXISTS` antes de `CREATE` porque Fabric no soporta `ALTER PROCEDURE`.

```sql
DROP PROCEDURE IF EXISTS [dbo].[sp_GetSalesForChatbot]
GO
CREATE PROCEDURE [dbo].[sp_GetSalesForChatbot] ...
```

---

### Paso 5 — Reglas de negocio

Crear `context/business_rules.md` con las reglas que el LLM necesita conocer para generar SQL correcto y presentar datos apropiadamente. El DataAgent lo lee en cada consulta — no hace falta reiniciar el servidor para agregar nuevas reglas.

---

### Paso 6 — UI de prueba

`ui_test/index.html` es un archivo HTML estático servido por FastAPI (`/ui/index.html`). Solo necesita:
- `localStorage` para persistir el `session_id` entre recargas
- `fetch` para llamar a `POST /chat`
- Endpoints de sesiones: `GET /chat/sessions/`, `GET /chat/sessions/{id}/messages`, `DELETE /chat/sessions/{id}`

---

### Paso 7 — Levantar el servidor

```bash
uvicorn app.main:app --reload --port 8000
```

Abrir: `http://localhost:8000/ui/index.html`

---

## 7. Variables de entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `ANTHROPIC_API_KEY` | Sí | API key de Anthropic |
| `DB_SERVER` | Sí | Host del Fabric Warehouse |
| `DB_DATABASE` | Sí | Nombre de la base de datos en Fabric |
| `DB_USER` | Sí | Usuario o email Azure AD |
| `DB_PASSWORD` | Solo si `DB_AUTH_MODE=sql` | Contraseña SQL |
| `DB_AUTH_MODE` | No (default: `sql`) | `sql` / `activedirectoryinteractive` / `activedirectoryintegrated` |
| `MEMORY_DB_PATH` | No (default: `./memory.db`) | Ruta del SQLite local |

---

## 8. Decisiones de diseño importantes

### ¿Por qué SQLite en memoria para el análisis?

En lugar de pedirle al LLM que genere SQL para Fabric directamente, se traen todos los datos del año al Python y se cargan en SQLite. Esto permite:
- Queries complejos sin depender de la sintaxis T-SQL de Fabric
- El LLM trabaja con SQLite (más simple y predecible)
- Aislamiento: el LLM no puede modificar datos reales

**Contrapartida:** Si la franquicia tiene millones de filas, esto es inviable. Para ese caso habría que cambiar a generación de T-SQL directa contra Fabric.

### ¿Por qué leer `business_rules.md` en runtime?

Para poder agregar o corregir reglas sin reiniciar el servidor ni hacer un deploy. El archivo es editable directamente y el cambio toma efecto en la siguiente consulta.

### ¿Por qué dos tablas de memoria (resumen + historial)?

- `chatbot_memory` (resumen): se inyecta como contexto en cada request para que el agente "recuerde" conversaciones anteriores de forma compacta (pocos tokens).
- `chat_messages` (historial completo): permite reconstruir la conversación exacta en la UI cuando el usuario carga una sesión anterior.

### ¿Por qué el tipo `off_topic` en el Orchestrator?

Para que mensajes fuera de scope (código, clima, traducciones) no consuman tokens de generación. El router responde con texto hardcodeado sin llamar a ningún modelo.

---

## 9. Sistema de Entrenamiento (Training Mode)

### Descripción General

El sistema de entrenamiento permite que el chatbot mejore continuamente a partir del feedback de los usuarios. Funciona como un ciclo de aprendizaje supervisado donde:

1. El usuario hace una **consulta** al chatbot
2. El chatbot genera una **respuesta** usando sus agentes
3. El usuario da **feedback** (positivo o negativo) sobre la respuesta
4. El **training_agent** analiza el ciclo y genera **sugerencias de mejora**
5. Las sugerencias se almacenan y se inyectan como contexto en futuras respuestas

### Ciclo de Feedback

```
Usuario pregunta → Agente responde → Usuario da feedback
                                           │
                                 Training Agent analiza
                                           │
                          ┌────────────────┴──────────────────┐
                          │                                   │
                 training_log.md                      TrainingMemory
                 (disco, append)                      (RAM, inyección)
                          │                                   │
                Revisión humana                  Se usa en próximas
                para aplicar                     respuestas del bot
```

### Archivos Involucrados

| Archivo | Rol |
|---------|-----|
| `app/agents/training_agent.py` | Analiza feedback y genera sugerencias |
| `app/db/training_repo.py` | Singleton `TrainingMemory` — RAM + disco |
| `app/agents/orchestrator.py` | Clasifica `feedback` como intent + inyecta contexto |
| `app/routers/chat.py` | Solicita feedback + rutea al training_agent |
| `context/training_log.md` | Log persistente de sugerencias (append only) |
| `app/models/schemas.py` | Campo `training_mode` en `ChatRequest` |

### Formato del training_log.md

Cada entrada tiene este formato:

```markdown
## [YYYY-MM-DD HH:MM] Sesión: {session_id} | Tipo: {negativo|positivo}

**Chat analizado:**
- Usuario preguntó: "..."
- Agente respondió: "..."
- Feedback recibido: "..."

**Componente afectado:** {data_agent | orchestrator | interaction | business_rules}

**Causa raíz identificada:**
...

**Sugerencia de cambio:**
...

**Prioridad:** {alta|media|baja}
---
```

- **Tipo `positivo`**: patrón exitoso a mantener
- **Tipo `negativo`**: problema a corregir
- **Prioridad `alta`**: datos incorrectos o queries fallidas
- **Prioridad `media`**: respuestas imprecisas o incompletas
- **Prioridad `baja`**: preferencias de estilo

### Workflow para Aplicar Sugerencias

1. Revisar `context/training_log.md` periódicamente (semanalmente o cuando haya muchas entradas)
2. Filtrar por prioridad `alta` primero
3. Agrupar por componente afectado
4. **`business_rules`** → agregar o modificar reglas en `context/business_rules.md`
5. **`data_agent`** → ajustar el prompt del sistema en `_generate_sql()` o `_format_response()`
6. **`orchestrator`** → refinar las descripciones de clasificación o agregar keywords
7. **`interaction`** → ajustar el prompt del sistema del agente de interacción
8. Testear los cambios con los mismos mensajes que generaron el feedback
9. Marcar como aplicado (opcionalmente agregar `[APLICADO]` al inicio de la entrada)

### Validación Interactiva con el Skill IA

Para agilizar la aplicación del feedback, el proyecto incluye un **Skill de IA** (`apply-training-suggestions`) que automatiza el workflow descrito arriba. 

**¿Qué hace este skill?**
1. **Carga el contexto:** Lee automáticamente `business_rules.md`, los agentes principales y el `training_log.md`.
2. **Analiza una a una:** Pasa por cada sugerencia pendiente en el log de entrenamiento.
3. **Propone un diff:** Basado en el componente afectado (ej: `data_agent`, `business_rules`), propone exactamente qué y dónde cambiar en el código o en las reglas.
4. **Flujo Interactivo:** Te pregunta sugerencia por sugerencia: `¿Aplicar este cambio? (sí/no/modificar)`.
5. **Aplica y limpia:** Si aceptás, modifica el archivo pertinente y elimina la entrada del `training_log.md`.

**¿Cómo invocarlo?**
El skill está disponible en las 3 herramientas:
*   **Gemini / Antigravity:** Pedir *"aplicá el skill apply_training_suggestions"*
*   **Claude Code:** Ejecutar `/project:apply-training-suggestions`
*   **OpenCode:** Seleccionarlo desde el menú interactivo de prompts.

### Inyección de Contexto en Prompts

Cuando `training_mode=True`, el orchestrator inyecta en cada system prompt:

```
=== CONTEXTO DE ENTRENAMIENTO ACTIVO ===
Las siguientes son sugerencias de mejora basadas en feedback previo de usuarios.
Tené en cuenta estos patrones al generar tu respuesta:
⚠️ CORRECCIÓN (data_agent): Query sin filtro Type → Agregar WHERE Type != '2'
✅ PATRÓN EXITOSO (business_rules): Formato de hora como "entre las X y X+1 hs"
```

Límites del sistema:
- Máximo **20 entradas** en RAM (las más recientes)
- El contexto inyectado se limita a ~**500 tokens** (prioridad alta/media)
- Máximo **10 turnos** del historial se pasan al training_agent por análisis

### Deshabilitar Training Mode en Producción

**Opción 1 — Desde el frontend:** desactivar el switch "Modo Entrenamiento" en la UI. Envía `training_mode: false` en cada request.

**Opción 2 — Cambiar el default en el schema:**
```python
# app/models/schemas.py
training_mode: bool = False  # cambiar de True a False
```

**Opción 3 — Variable de entorno:**
```env
TRAINING_MODE_DEFAULT=false
```
Y modificar `config.py` para leerla.

### Consideraciones de Seguridad

- El training_agent **NUNCA modifica** archivos de código ni `business_rules.md`
- Solo escribe en `context/training_log.md` (append mode)
- Las sugerencias son **revisadas por un humano** antes de aplicarse
- El contexto en RAM es **efímero** y se reconstruye en cada reinicio de la app
- Los datos del feedback no se envían a servicios externos más allá de la API de Anthropic