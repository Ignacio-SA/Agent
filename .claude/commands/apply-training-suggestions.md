# Skill: Aplicar Sugerencias del Training Log

## Objetivo
Analizar cada sugerencia pendiente en `context/training_log.md` y aplicarla al proyecto de forma interactiva con el usuario.

## Instrucciones

Eres un experto en el proyecto Chatbot Multi-Agente. Tu trabajo es leer el training log, analizar cada sugerencia, y proponerle al usuario cómo aplicarla. El usuario aprueba o rechaza cada propuesta.

### Paso 1 — Cargar contexto del proyecto

Antes de empezar, lee estos archivos para tener el contexto completo:

1. **Reglas de negocio** → `context/business_rules.md`
   - Contiene reglas SQL, de presentación, y de datos que inyecta el data_agent
   - Las sugerencias de componente `business_rules` se aplican aquí

2. **Orchestrator** → `app/agents/orchestrator.py`
   - Clasifica mensajes en: data, interaction, feedback, off_topic
   - Las sugerencias de componente `orchestrator` se aplican aquí (ajustar clasificación, keywords, prompt)

3. **Data Agent** → `app/agents/data_agent.py`
   - Pipeline Text-to-SQL: genera SQL, ejecuta, formatea respuesta
   - Métodos clave: `_generate_sql()` (prompt del LLM para SQL), `_format_response()` (prompt para presentar datos), `_compute_summary()` (métricas en Python)
   - Las sugerencias de componente `data_agent` se aplican aquí (ajustar prompts, lógica SQL, formateo)

4. **Interaction Agent** → `app/agents/interaction.py`
   - Responde saludos y preguntas sobre el chatbot
   - Las sugerencias de componente `interaction` se aplican aquí

5. **Training Log** → `context/training_log.md`
   - Lee TODAS las entradas pendientes

### Paso 2 — Procesar sugerencias una por una

Para CADA entrada en `training_log.md`, seguir este flujo:

#### A. Mostrar al usuario:
```
📋 Sugerencia #N de M

- Fecha: [timestamp]
- Sesión: [session_id]
- Tipo: [positivo/negativo]
- Componente: [componente afectado]
- Prioridad: [alta/media/baja]

💬 El usuario preguntó: "..."
🤖 El agente respondió: "..."
📝 Feedback: "..."

🔍 Causa raíz: ...
💡 Sugerencia: ...
```

#### B. Analizar y proponer:

Según el **componente afectado**, proponer un cambio concreto:

- **`business_rules`**: Proponer la regla nueva o modificada en formato markdown para agregar a `context/business_rules.md`. Mostrar exactamente dónde iría dentro del archivo (después de qué sección).

- **`data_agent`**: Proponer el cambio al prompt del sistema en `_generate_sql()` o `_format_response()`, o un ajuste en la lógica de `_compute_summary()`. Mostrar el diff exacto.

- **`orchestrator`**: Proponer cambio a las descripciones de clasificación en el system prompt, o nuevas keywords en el fallback. Mostrar el diff exacto.

- **`interaction`**: Proponer cambio al system prompt del interaction agent. Mostrar el diff exacto.

- **Si es tipo `positivo`**: Proponer cómo reforzar el patrón exitoso (ej: agregar como ejemplo en business_rules, reforzar en el prompt, etc). Si no hay acción necesaria, indicarlo.

#### C. Preguntar al usuario:
```
¿Aplicar este cambio? (sí/no/modificar)
```

- **sí** → Aplicar el cambio al archivo correspondiente y eliminar la entrada de `training_log.md`
- **no** → Marcar como `[DESCARTADO]` en `training_log.md` y pasar a la siguiente
- **modificar** → Pedir al usuario qué cambiar, ajustar la propuesta, y volver a preguntar

### Paso 3 — Limpieza final

Una vez procesadas todas las sugerencias:
1. Verificar que `training_log.md` solo tenga el header y las entradas descartadas/pendientes
2. Mostrar un resumen de lo aplicado:
   - Cuántas sugerencias se aplicaron
   - Cuántas se descartaron
   - Qué archivos se modificaron
3. Preguntar si quiere eliminar las entradas marcadas como `[DESCARTADO]`

### Mapa de archivos del proyecto

```
Agent/
├── app/
│   ├── main.py                    # Entry point, startup
│   ├── config.py                  # Settings (pydantic-settings)
│   ├── agents/
│   │   ├── orchestrator.py        # Clasificación de intents (Sonnet)
│   │   ├── data_agent.py          # Text-to-SQL pipeline (Haiku)
│   │   ├── interaction.py         # Conversación general (Haiku)
│   │   ├── memory_agent.py        # Resúmenes de sesión (Haiku)
│   │   └── training_agent.py      # Análisis de feedback (Haiku)
│   ├── routers/
│   │   └── chat.py                # Endpoints POST /chat, sesiones, historial
│   ├── db/
│   │   ├── connection.py          # pyodbc → Fabric Warehouse
│   │   ├── sales_repo.py          # SP de ventas
│   │   ├── memory_repo.py         # SQLite local (sesiones + mensajes)
│   │   └── training_repo.py       # TrainingMemory singleton (RAM + disco)
│   └── models/
│       ├── schemas.py             # ChatRequest, ChatResponse, etc.
│       └── memory.py              # MemoryEntry model
├── context/
│   ├── business_rules.md          # ← EDITABLE: reglas de negocio
│   └── training_log.md            # ← LEER: sugerencias pendientes
├── sql/
│   └── sp_GetSalesForChatbot.sql  # SP en Fabric
└── ui_test/
    └── index.html                 # UI de prueba
```

### Convenciones a respetar al editar

- Imports: relativos dentro de `app` (`from ..config import settings`)
- Sin comentarios salvo lógica no obvia
- `temperature=0` siempre en llamadas Anthropic
- `business_rules.md` se lee en **runtime** (cambios inmediatos, sin restart)
- Regla SQL crítica: siempre `WHERE Type != '2'` en agregaciones
- Búsquedas: siempre `LOWER(col) LIKE LOWER('%texto%')`
- Fechas SQLite: `strftime()`, `DATE()`, nunca `YEAR()` o `MONTH()`
- Presentación: nunca mostrar nombres técnicos de columnas al usuario

### Reglas de seguridad

- NUNCA eliminar reglas existentes de business_rules.md sin aprobación explícita
- NUNCA modificar la estructura de la tabla `ventas` ni el SP
- Cada cambio debe ser atómico y reversible
- Si hay duda sobre el impacto, preguntar antes de aplicar
