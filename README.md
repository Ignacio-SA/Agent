# Chatbot Multi-Agente — Asistente de Ventas para Franquiciados

A multi-agent AI chatbot for franchise sales analysis. Built with FastAPI and Claude (Anthropic), it connects to Microsoft Fabric Warehouse to query sales data via stored procedures, loads results into SQLite in-memory, and uses Text-to-SQL to answer natural language questions in Spanish.

## Arquitectura

```
Cliente (UI Web / API)
    ↓
FastAPI Gateway
    ↓
Orchestrator Agent (Claude Sonnet — decide qué agente responde)
    ├→ Data Agent      (Haiku — Text-to-SQL sobre datos de ventas)
    ├→ Interaction Agent (Haiku — conversación general)
    └→ Memory Agent    (Haiku — resumen y contexto de sesión)
    ↓
Microsoft Fabric Warehouse  →  sp_GetSalesForChatbot
    ↓
SQLite en memoria (Text-to-SQL)     SQLite local (memoria de sesiones)
```

### Flujo del Data Agent (Text-to-SQL)
1. Ejecuta `sp_GetSalesForChatbot` en Fabric Warehouse con el `FranchiseCode` del usuario
2. Carga los resultados en una tabla `ventas` SQLite en memoria
3. El LLM genera una consulta SQLite a partir del lenguaje natural del usuario
4. Ejecuta el SQL y formatea la respuesta en español

## Requisitos

- Python 3.12
- Microsoft Fabric Warehouse (con ODBC Driver 17 for SQL Server)
- Cuenta Anthropic con acceso a Claude Sonnet y Haiku
- Azure AD con permisos de lectura sobre el Warehouse

## Instalación

```bash
# 1. Crear entorno virtual
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Linux/Mac

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
copy .env.example .env
# Editar .env con tus valores
```

## Variables de entorno (`.env`)

```env
# Anthropic API
ANTHROPIC_API_KEY=sk-ant-...

# Microsoft Fabric Warehouse
DB_SERVER=tu-servidor.datawarehouse.fabric.microsoft.com
DB_NAME=nombre_de_tu_warehouse
DB_USER=tu@email.com
DB_AUTH_MODE=interactive    # Abre el navegador para login con MFA

# Solo si DB_AUTH_MODE=sql
DB_PASSWORD=

# Memoria local (SQLite)
MEMORY_DB_PATH=./memory.db
```

## Configurar el Warehouse

Ejecutar en el **SQL Query Editor de Microsoft Fabric**:

```sql
-- 1. Stored procedure de ventas
-- (contenido en sql/sp_GetSalesForChatbot.sql)

-- 2. Verificar ejecución
EXEC sp_GetSalesForChatbot @FranchiseCode = 'tu-franchise-code'
```

> La memoria de sesiones se guarda localmente en SQLite (`memory.db`). No requiere permisos DDL en Fabric.

## Ejecutar

```bash
uvicorn app.main:app --reload
```

Al iniciar por primera vez con `DB_AUTH_MODE=interactive`, se abrirá el navegador para autenticarse con Azure AD (MFA). El token se cachea en `~/.azure/`.

Accesos:
- **UI Web**: http://localhost:8000/ui/index.html
- **API Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health

## Endpoints

### `POST /chat/`
```json
{
  "message": "¿Cuál fue el producto más vendido ayer?",
  "session_id": "session_abc123",
  "franchise_id": "4066b2def050495a8fc9ff8c0cb3f8f4",
  "user_id": "opcional"
}
```
Respuesta:
```json
{
  "session_id": "session_abc123",
  "response": "El producto más vendido ayer fue...",
  "agent_type": "data",
  "timestamp": "2026-04-08T11:00:00"
}
```

### `GET /chat/sessions/`
Lista todas las sesiones guardadas con su resumen.

### `GET /chat/sessions/{session_id}/messages`
Historial completo de mensajes de una sesión.

### `DELETE /chat/sessions/{session_id}`
Elimina una sesión y todos sus mensajes.

### `GET /chat/history/{session_id}`
Resumen de contexto de una sesión.

## Estructura del proyecto

```
Agent/
├── app/
│   ├── agents/
│   │   ├── orchestrator.py      # Decide qué agente responde
│   │   ├── data_agent.py        # Text-to-SQL sobre ventas
│   │   ├── interaction.py       # Conversación general
│   │   └── memory_agent.py      # Resumen y contexto
│   ├── db/
│   │   ├── connection.py        # Conexión Azure AD a Fabric
│   │   ├── sales_repo.py        # Llama al SP de ventas
│   │   └── memory_repo.py       # SQLite local (sesiones + mensajes)
│   ├── models/
│   │   └── schemas.py           # Modelos Pydantic
│   ├── routers/
│   │   └── chat.py              # Endpoints FastAPI
│   ├── config.py                # Variables de entorno
│   └── main.py                  # App FastAPI
├── context/
│   └── business_rules.md        # Reglas de negocio para el agente
├── sql/
│   └── sp_GetSalesForChatbot.sql
├── ui_test/
│   └── index.html               # UI web de prueba
├── validate_setup.py            # Valida conexión y configuración
├── .env.example
├── requirements.txt
└── README.md
```

## Reglas de negocio (`context/business_rules.md`)

El agente lee este archivo en cada consulta. Contiene:
- Descripción de columnas de la tabla `ventas`
- Regla del campo `Type`: `1` = ítem unitario, `2` = cabecera de promoción (excluir de totales)
- Reglas de presentación: no mostrar información técnica al usuario
- Reglas de búsqueda: siempre usar `LOWER(...) LIKE LOWER('%texto%')` para nombres de artículos

Para agregar una nueva regla de negocio, editar `context/business_rules.md` — no se requiere reiniciar el servidor.

## Agentes

### Orchestrator (Claude Sonnet)
Analiza el mensaje y decide si derivar a `data` (consultas de ventas) o `interaction` (conversación general). Usa palabras clave como fallback si el LLM no responde en formato JSON válido.

### Data Agent (Claude Haiku)
1. Llama al SP con el `franchise_id` del usuario
2. Carga los datos en SQLite en memoria (decodificando `DATETIMEOFFSET` binario de pyodbc)
3. Genera SQL SQLite con el LLM (usando las reglas de negocio como contexto)
4. Ejecuta el SQL y formatea la respuesta en lenguaje natural

### Interaction Agent (Claude Haiku)
Responde consultas generales de conversación. No inventa información sobre el negocio — si no sabe algo, sugiere consultar con el administrador.

### Memory Agent (Claude Haiku)
Genera resúmenes de la conversación y los persiste en SQLite local. El contexto se recupera al inicio de cada sesión.

## Troubleshooting

**Error de autenticación Azure AD (22007 / 24803)**
- Usar `DB_AUTH_MODE=interactive` en lugar de `sql`
- Asegurarse de tener instalado `azure-identity` (`pip install azure-identity`)

**El SP devuelve 0 filas**
- Verificar que el WHERE usa `h.FranchiseCode` (no `h.FranchiseeCode`)
- Ejecutar `EXEC sp_GetSalesForChatbot @FranchiseCode = 'tu-id'` directo en Fabric

**Fechas incorrectas**
- La columna `SaleDateTimeUtc` en Fabric es `DATETIMEOFFSET` en UTC+00:00
- El SP aplica `SWITCHOFFSET(..., '-03:00')` para convertir a Argentina
- pyodbc devuelve el valor como bytes binarios de 20 bytes — el agente los decodifica con `struct.unpack`

**No aparece información de ventas**
- Validar setup: `python validate_setup.py`
- Verificar que `franchise_id` en el UI corresponde a `FranchiseCode` en Fabric (no `FranchiseeCode`)
