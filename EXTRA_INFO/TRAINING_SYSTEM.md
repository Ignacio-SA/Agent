# Sistema de Entrenamiento (Training Mode)

## Descripción General

El sistema de entrenamiento permite que el chatbot mejore continuamente a partir del feedback de los usuarios.
Funciona como un ciclo de aprendizaje supervisado donde:

1. El usuario hace una **consulta** al chatbot
2. El chatbot genera una **respuesta** usando sus agentes
3. El usuario da **feedback** (positivo o negativo) sobre la respuesta
4. El **training_agent** analiza el ciclo y genera **sugerencias de mejora**
5. Las sugerencias se almacenan y se inyectan como contexto en futuras respuestas

## Ciclo de Feedback

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   Usuario pregunta → Agente responde → Usuario da feedback  │
│                                              │              │
│                                    Training Agent analiza   │
│                                              │              │
│                              ┌───────────────┴────────────┐ │
│                              │                            │ │
│                     training_log.md              TrainingMemory │
│                     (disco, append)              (RAM, inyección) │
│                              │                            │ │
│                    Revisión humana           Se usa en próximas │
│                    para aplicar              respuestas del bot │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Archivos Involucrados

| Archivo | Rol |
|---------|-----|
| `app/agents/training_agent.py` | Analiza feedback y genera sugerencias |
| `app/db/training_repo.py` | Singleton `TrainingMemory` — RAM + disco |
| `app/agents/orchestrator.py` | Clasifica `feedback` como intent + inyecta contexto |
| `app/routers/chat.py` | Solicita feedback + rutea al training_agent |
| `context/training_log.md` | Log persistente de sugerencias (append only) |
| `app/models/schemas.py` | Campo `training_mode` en `ChatRequest` |

## Cómo Leer training_log.md

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

### Campos clave:
- **Tipo**: `positivo` = patrón exitoso a mantener, `negativo` = problema a corregir
- **Componente afectado**: indica qué parte del sistema tiene el problema
- **Prioridad**: `alta` = datos incorrectos/queries fallidas, `media` = imprecisiones, `baja` = estilo

## Cómo Aplicar Sugerencias Manualmente

### Workflow recomendado:

1. **Revisar** `context/training_log.md` periódicamente (semanalmente o cuando haya muchas entradas)
2. **Filtrar** por prioridad `alta` primero
3. **Agrupar** por componente afectado
4. **Para `business_rules`**: agregar o modificar reglas en `context/business_rules.md`
5. **Para `data_agent`**: ajustar el prompt del sistema o la lógica de `_generate_sql`
6. **Para `orchestrator`**: refinar las descripciones de clasificación o agregar keywords
7. **Para `interaction`**: ajustar el prompt del sistema del agente de interacción
8. **Testear** los cambios con los mismos mensajes que generaron el feedback
9. **Marcar como aplicado** (opcionalmente, agregar `[APLICADO]` al inicio de la entrada)

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

### Ejemplo de aplicación:

Si el log dice:
```
**Componente afectado:** business_rules
**Causa raíz:** El agente no filtra por Type != '2' al calcular promedios
**Sugerencia:** Agregar regla explícita sobre promedios en business_rules.md
```

Entonces agregar en `context/business_rules.md`:
```markdown
- Para calcular promedios de precio o cantidad, SIEMPRE filtrar `WHERE Type != '2'`
```

## TrainingMemory — Contexto en RAM

El singleton `TrainingMemory` (`app/db/training_repo.py`):

- **Al iniciar la app**: lee `training_log.md` y carga las últimas 20 entradas en RAM
- **En cada feedback**: agrega la nueva sugerencia a RAM + append en disco
- **En cada request (training_mode=True)**: el contexto se inyecta en los prompts de los agentes

### Límites:
- Máximo **20 entradas** en RAM (las más recientes)
- El contexto inyectado se limita a ~**500 tokens** (sugerencias de prioridad alta/media)
- Máximo **10 turnos** del historial se pasan al training_agent por análisis

### Inyección en prompts:
Cuando `training_mode=True`, se agrega al system prompt de cada agente:
```
=== CONTEXTO DE ENTRENAMIENTO ACTIVO ===
Las siguientes son sugerencias de mejora basadas en feedback previo de usuarios.
Tené en cuenta estos patrones al generar tu respuesta:
⚠️ CORRECCIÓN (data_agent): Query sin filtro Type → Agregar WHERE Type != '2'
✅ PATRÓN EXITOSO (business_rules): Formato de hora como "entre las X y X+1 hs"
```

## Deshabilitar Training Mode en Producción

### Opción 1: Desde el frontend
Desactivar el switch "Modo Entrenamiento" en la UI. Esto envía `training_mode: false`
en cada request, lo que:
- No solicita feedback al usuario
- No inyecta contexto de entrenamiento en los prompts
- No activa el training_agent ante feedback

### Opción 2: Cambiar el default en el schema
En `app/models/schemas.py`, cambiar:
```python
training_mode: bool = True   # ← cambiar a False
```

### Opción 3: Variable de entorno
Agregar en `.env`:
```
TRAINING_MODE_DEFAULT=false
```
Y modificar `config.py` para leerla.

## Consideraciones de Seguridad

- El training_agent **NUNCA modifica** archivos de código ni `business_rules.md`
- Solo escribe en `context/training_log.md` (append mode)
- Las sugerencias son **revisadas por un humano** antes de aplicarse
- El contexto en RAM es **efímero** y se reconstruye en cada reinicio de la app
- Los datos del feedback del usuario no se envían a servicios externos más allá de Claude (Anthropic API)
