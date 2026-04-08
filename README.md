# 🤖 Chatbot Multi-Agente

Sistema de chatbot basado en arquitectura multi-agente con Claude de Anthropic. Utiliza Claude Sonnet como orquestador y Claude Haiku para sub-agentes especializados (interacción, datos, memoria).

## 🏗️ Arquitectura

```
Cliente (UI / API Externas)
    ↓
FastAPI Gateway (Rate limiting, Auth)
    ↓
Orchestrator Agent (Claude Sonnet - decide qué agente)
    ├→ Interaction Agent (Haiku - respuestas)
    ├→ Data Agent (Haiku - consultas SQL/ventas)
    └→ Memory Agent (Haiku - recordar contexto)
    ↓
SQL Server (Datos + Memoria)
```

## 📋 Requisitos

- Python 3.9+
- SQL Server (o compatible)
- Clave de API de Anthropic
- pip

## 🚀 Instalación

1. **Clonar/preparar repositorio**
```bash
cd chatbot-franchise
```

2. **Crear virtual env**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**
```bash
cp .env.example .env
# Editar .env con tus valores
```

Variables necesarias:
```
ANTHROPIC_API_KEY=sk-ant-xxx
DB_SERVER=localhost
DB_DATABASE=chatbot_db
DB_USER=sa
DB_PASSWORD=YourPassword123!
```

5. **Crear bases de datos**
```bash
# Conectarse a SQL Server y ejecutar:
sqlcmd -S localhost -U sa -P YourPassword123! -i sql/create_chatbot_memory.sql
sqlcmd -S localhost -U sa -P YourPassword123! -i sql/sp_GetSalesForChatbot.sql
```

## 🏃 Ejecutar

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Luego accede a:
- **API Docs**: http://localhost:8000/docs
- **UI de Prueba**: http://localhost:8000/ui/index.html

## 📡 Endpoints

### Chat
```bash
POST /chat/
{
  "message": "¿Cuál es el total de ventas?",
  "session_id": "session_123",
  "franchise_id": "franchise_001",
  "user_id": "user_001"
}
```

**Response:**
```json
{
  "session_id": "session_123",
  "response": "El total de ventas es...",
  "agent_type": "data",
  "timestamp": "2024-01-15T10:30:00"
}
```

### Historial
```bash
GET /chat/history/{session_id}
```

## 🧪 Tests

```bash
pytest tests/ -v
```

## 📁 Estructura

```
chatbot-franchise/
├── app/
│   ├── agents/           # Agentes especializados
│   ├── db/               # Acceso a datos
│   ├── models/           # Schemas Pydantic
│   ├── routers/          # Endpoints FastAPI
│   ├── config.py         # Variables de entorno
│   └── main.py           # Punto de entrada
├── sql/                  # Scripts SQL
├── tests/                # Pruebas
├── ui_test/              # Frontend mínimo
├── requirements.txt
└── README.md
```

## 🤖 Agentes

### Orchestrator (Claude Sonnet)
- Analiza el mensaje del usuario
- Decide qué sub-agente debe responder
- Coordina flujo y memoria

### Interaction Agent (Haiku)
- Responde conversacionalmente
- Usa contexto de memoria
- Respuestas naturales y breves

### Data Agent (Haiku)
- Convierte lenguaje natural a conceptos SQL
- Accede a sp_GetSalesForChatbot
- Retorna datos estructurados

### Memory Agent (Haiku)
- Genera resúmenes de conversaciones
- Lee/escribe tabla chatbot_memory
- Mantiene contexto entre sesiones

## 🔧 Configuración Avanzada

### Rate Limiting
```python
# En config.py
API_RATE_LIMIT=100  # Requests por minutos
```

### Modelos de Claude
Editar en cada agente:
```python
self.model = "claude-3-5-sonnet-20241022"  # Orchestrator
self.model = "claude-3-5-haiku-20241022"   # Sub-agentes
```

## 🐛 Troubleshooting

**Error de conexión a BD:**
- Verificar connection string en .env
- Asegurar que SQL Server está corriendo
- Ejecutar scripts SQL primero

**Error de API de Anthropic:**
- Verificar ANTHROPIC_API_KEY
- Comprobar cuota disponible en https://console.anthropic.com

**CORS Error:**
- Los CORS están habilitados por defecto
- Configurar en `app/main.py` si es necesario

## 📝 Licencia

MIT

## 👤 Autor

Creado para arquitectura multi-agente de Anthropic.
