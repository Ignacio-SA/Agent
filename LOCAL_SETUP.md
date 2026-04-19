# Local Setup — Chatbot Multi-Agente

## Qué se hizo en esta sesión

### 1. Análisis de infraestructura (`INFRASTRUCTURE_PLAN.md`)

Se analizó el proyecto completo y se generó un plan maestro de infraestructura que cubre:

- **Diagnóstico del estado actual** — fortalezas del proyecto y deudas técnicas (CORS abierto, sin auth, SQLite no escalable, logs en archivos, etc.)
- **Recomendación de cloud: Azure** — justificado porque Microsoft Fabric ya vive en Azure, Azure AD ya se usa para auth, y los costos iniciales son menores gracias a scale-to-zero.
- **Arquitectura objetivo** — API en Azure Container Apps, frontend estático en Azure CDN + Blob Storage, CosmosDB para sesiones, PostgreSQL para logs y training.
- **Estrategia multi-ambiente** — dev (Docker local), stg (Azure, scale-to-zero), prod (Azure, auto-scale).
- **Seguridad** — JWT, CORS por ambiente, rate limiting, Key Vault para secrets, Managed Identity para Fabric.
- **Integración WhatsApp** — Meta Cloud API con webhook, whitelist de números en BD, verificación de firma HMAC.
- **Backoffice** — frontend desacoplado con chat playground, visor de sesiones, training console, gestión de reglas y números de WhatsApp.
- **Roadmap en 5 fases** con estimación de costos (~$35-70/mes en staging).

---

### 2. Containerización del proyecto

Se crearon los archivos necesarios para simular localmente el entorno de Azure, sin tocar ningún archivo de código existente.

#### `Dockerfile`
Imagen de la API con Python 3.12 slim + ODBC Driver 17 para SQL Server (requerido por `pyodbc` para conectarse a Microsoft Fabric).

```
python:3.12-slim
  └── ODBC Driver 17 (Microsoft)
  └── pip install -r requirements.txt
  └── COPY app/
  └── uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### `docker-compose.yml`
Orquesta dos servicios:

| Servicio | Contenedor | Puerto | Simula en Azure |
|----------|-----------|--------|-----------------|
| `api` | FastAPI + hot reload | 8000 | Azure Container Apps |
| `frontend` | nginx sirviendo `ui_test/` | 3000 | Azure CDN + Blob Storage |

El servicio `api` monta como volúmenes:
- `./app` → hot reload del código
- `./context` → `business_rules.md` editable en vivo sin rebuild
- `./logs` → logs accesibles desde el host
- `./memory.db` → SQLite persistente entre reinicios

#### `nginx/nginx.conf`
Configuración mínima de nginx para servir el frontend estático, exactamente como lo haría Azure CDN sirviendo desde un Blob Storage.

#### `.dockerignore`
Excluye de la imagen Docker: `venv/`, `.env`, `logs/`, `memory.db`, herramientas de IA (`.gemini/`, `.claude/`), documentación y archivos innecesarios. Mantiene la imagen liviana.

---

### 3. Analogía local ↔ Azure

```
LOCAL                              AZURE (futuro)
─────────────────────────────────────────────────────────
docker compose up                  GitHub Actions → deploy
API en localhost:8000              Azure Container Apps
nginx en localhost:3000            Azure CDN + Blob Storage
.env file                          Azure Key Vault + App Settings
memory.db (SQLite en volumen)      Azure CosmosDB Serverless
training_log.md                    Azure PostgreSQL Flexible
DB_AUTH_MODE=sql                   DB_AUTH_MODE=managedidentity
```

---

## Cómo levantar el proyecto

### Requisitos previos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y corriendo
- Archivo `.env` configurado en la raíz del proyecto (ver `.env.example`)

### Variables de entorno mínimas en `.env`

```bash
ANTHROPIC_API_KEY=sk-ant-xxxxx          # obligatorio
DB_SERVER=tu-servidor.database.windows.net
DB_DATABASE=tu-base-de-datos
DB_AUTH_MODE=sql                        # usar "sql" para Docker local
DB_USER=tu-usuario
DB_PASSWORD=tu-contraseña
MEMORY_DB_PATH=./memory.db
FASTAPI_ENV=development
FASTAPI_DEBUG=true
```

> **Importante:** Si tu `.env` tiene `DB_AUTH_MODE=activedirectoryinteractive` o `activedirectoryintegrated`, cambiarlo a `sql` para Docker. El modo interactivo requiere un browser y no funciona dentro de un contenedor.

---

### Conexión a Microsoft Fabric Warehouse

#### Por qué `sql` y no el modo interactivo en Docker

| Modo | Cómo autentica | ¿Funciona en Docker? | Cuándo usarlo |
|------|---------------|----------------------|---------------|
| `activedirectoryinteractive` | Abre browser → MFA | ❌ No | Solo dev local sin Docker |
| `sql` | Usuario + contraseña | ✅ Sí | Docker local y servidores |
| `managedidentity` | El servidor se autentica solo | ✅ Sí (solo en Azure) | Producción en Azure |

#### Cómo obtener los datos de conexión a Fabric

1. Ir al portal de **Microsoft Fabric** → [https://app.fabric.microsoft.com](https://app.fabric.microsoft.com)
2. Abrir el **Workspace** y seleccionar el **Warehouse**
3. Ir a **Settings** (engranaje) → **SQL connection string**
4. Copiar los valores:

```
Server:   <workspace>.datawarehouse.fabric.microsoft.com
Database: <nombre del warehouse>
```

5. El **usuario** es el email corporativo (`usuario@empresa.com`) y la **contraseña** es la del tenant de Azure AD (la misma que se usa para el MFA interactivo).

#### Variables completas para Docker en `.env`

```bash
DB_SERVER=workspace-id.datawarehouse.fabric.microsoft.com
DB_DATABASE=nombre-del-warehouse
DB_AUTH_MODE=sql
DB_USER=usuario@empresa.com
DB_PASSWORD=contraseña-de-azure-ad
```

#### Verificar que la conexión funciona

Después de completar el `.env` y levantar los contenedores, probá el health check:

```bash
curl http://localhost:8000/health
```

Luego mandá un mensaje de interacción simple (sin datos) para aislar si el problema es la BD o el LLM:

```bash
curl -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "hola", "session_id": "test", "franchise_id": "test"}'
```

Si responde correctamente → el LLM funciona. Luego probá con una consulta de datos real.

#### Troubleshooting

| Error en logs | Causa | Solución |
|---------------|-------|----------|
| `Login failed for user` | Credenciales incorrectas | Verificar `DB_USER` y `DB_PASSWORD` |
| `Cannot open server ... requested by the login` | `DB_SERVER` incorrecto | Copiar exactamente desde el portal de Fabric |
| `SSL Provider error` | Falta `Encrypt=yes` | Ya está en `connection.py`, no requiere cambio |
| `timeout expired` | Red bloqueada o VPN necesaria | Verificar que tu máquina accede a Fabric sin Docker primero |

---

### Comandos

#### Levantar todo (primera vez o después de cambios en `requirements.txt`)
```bash
docker compose up --build
```

#### Levantar sin rebuild (inicio rápido)
```bash
docker compose up
```

#### Detener
```bash
docker compose down
```

#### Ver logs en tiempo real
```bash
# Ambos servicios
docker compose logs -f

# Solo la API
docker compose logs -f api
```

#### Rebuild solo de la API (si cambiaste requirements.txt)
```bash
docker compose up --build api
```

---

### URLs disponibles

| URL | Qué es |
|-----|--------|
| http://localhost:3000 | Frontend (chat UI) |
| http://localhost:8000 | API directa |
| http://localhost:8000/docs | Documentación interactiva (Swagger) |
| http://localhost:8000/health | Health check |
| http://localhost:8000/debug/token-logs | Log de tokens consumidos |

---

### Cómo usar el chat

1. Abrir http://localhost:3000
2. Ingresar el **Franchise ID** en el campo de la parte superior
3. Escribir una pregunta de ventas (ej: *"¿Cuántas ventas hubo hoy?"*)
4. El toggle **🎓 Entrenamiento** activa el modo de feedback para reentrenar el modelo

---

### Flujo interno de un mensaje

```
Usuario escribe → Frontend (localhost:3000)
                      ↓ POST http://localhost:8000/chat/
                  API (FastAPI)
                      ↓
                  Orchestrator (Claude Sonnet) → clasifica el mensaje
                      ↓
          ┌───────────────────────────────┐
          │                               │
       data_agent                   interaction_agent
    (Claude Haiku)                  (Claude Haiku)
          │                               │
    1. Extrae fechas              Responde saludos
    2. Llama a Fabric SP          y preguntas generales
    3. Carga SQLite en RAM
    4. Genera SQL
    5. Ejecuta SQL
    6. Formatea respuesta
          │
          └──────────────→ Respuesta al usuario
                                  ↓
                         Guarda en memory.db
                         Guarda en logs/
```

---

### Estructura de archivos relevantes

```
Agent/
├── Dockerfile              ← imagen de la API
├── docker-compose.yml      ← orquesta API + frontend
├── .dockerignore           ← mantiene la imagen liviana
├── nginx/
│   └── nginx.conf          ← config del servidor de frontend estático
├── app/                    ← código de la API (hot reload activo)
│   ├── agents/             ← orchestrator, data_agent, training_agent, etc.
│   ├── routers/            ← endpoints /chat/ y /debug/
│   ├── db/                 ← repositorios (memory, training, sales, connection)
│   └── models/             ← schemas Pydantic
├── context/
│   ├── business_rules.md   ← reglas de negocio (editable en vivo)
│   └── training_log.md     ← log de sugerencias de entrenamiento
├── ui_test/
│   └── index.html          ← frontend del chat (servido por nginx)
├── logs/                   ← logs por sesión (generados en runtime)
├── memory.db               ← base de datos SQLite local (sesiones y tokens)
├── INFRASTRUCTURE_PLAN.md  ← plan completo de arquitectura para producción
└── .env                    ← variables de entorno (NO commitear)
```

---

### Próximos pasos (según INFRASTRUCTURE_PLAN.md)

1. **Fase 1** — Agregar autenticación JWT + deploy en Azure Container Apps
2. **Fase 2** — Migrar SQLite a CosmosDB y training_log.md a PostgreSQL
3. **Fase 3** — Integrar WhatsApp via Meta Cloud API
4. **Fase 4** — Hardening de producción (circuit breakers, alertas, load testing)
