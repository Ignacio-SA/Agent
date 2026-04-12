# Arquitectura de Consultas SQL (Fabric vs SQLite)

El chatbot utiliza una arquitectura de **dos fases** para las consultas de datos. Esta separacion es fundamental para la seguridad y la velocidad: no se le permite al asistente de IA ejecutar codigo ciegamente contra la nube real, sino que juega en una "caja de arena" temporal local (SQLite).

A continuacion se explica cada tipo de consulta que ocurre en todo el proyecto.

---

## FASE 1: Consultas en Microsoft Fabric (Nube)
Estas consultas se hacen en lenguaje **T-SQL** contra tu Data Warehouse en Azure. Son controladas 100% por el backend y el IA **no tiene poder** para alterarlas.

### `EXEC sp_GetSalesForChatbot`
**Donde ocurre:** `app/db/sales_repo.py`
**Para que sirve:** Al iniciar una pregunta del usuario, el backend llama a este Stored Procedure. 
**Como funciona:**
```sql
EXEC sp_GetSalesForChatbot @FranchiseCode=?, @Year=?, @DateFrom=?, @DateTo=?
```
Es una consulta parametrizada que trae todos los tickets y detalles de una franquicia. **Sirve como una gran descarga ("export")** de datos hacia el servidor del chatbot. 
*Nota:* Es la UNICA vez que se consulta a la nube durante una conversacion de ventas.

---

## FASE 2: Consultas en SQLite en Memoria (Local Temporal)
Una vez que `Fabric` devuelve los datos en bruto, el `DataAgent` los carga en una memoria RAM ultrarrapida usando SQLite local. 

Estas consultas utilizan formato **SQLite**.

### 1. Creacion de la tabla y carga de datos
**Donde ocurre:** `app/agents/data_agent.py`
El backend crea una tabla en RAM al vuelo y le inserta las filas que trajo de Fabric:
```sql
-- Creacion
CREATE TABLE ventas ("id" TEXT, "FranchiseeCode" TEXT, ...)
-- Inserciones iterativas
INSERT INTO ventas VALUES (?, ?, ?, ...)
```

### 2. Generacion de AI (Text-To-SQL)
**Donde ocurre:** `app/agents/data_agent.py`
**Para que sirve:** Aqui entra el Chatbot. El LLM (Claude) traduce la pregunta del usuario en una consulta que solo ataca a esta tabla `ventas` temporal.
**Como funciona (Ejemplos generados por IA):**
*   "Cual fue el producto mas vendido de hoy?" -> 
    `SELECT ArticleDescription, SUM(Quantity) ... WHERE DATE(SaleDateTimeUtc) = '2026-04-09' GROUP BY ArticleDescription ORDER BY SUM(Quantity) DESC LIMIT 1`
*   **Aclaracion:** El sistema instruye estrictamente al IA usar funciones exclusivas de SQLite (ej. `strftime` en vez de `YEAR()`, o `DATE()` en vez de `GETDATE()`).

**Cual es la ventaja:** El IA puede equivocarse todo lo que quiera. Estara interrogando una tabla que "muere" (se borra de la RAM) apenas devuelve la respuesta. Es rapido y muy seguro.

---

## Consultas extra: La Memoria Local (Historial)
El proyecto usa otro pequeño archivo SQLite real (que se guarda en el disco `memory.db`) para guardar de que hablaron.

**Donde ocurre:** `app/db/memory_repo.py`
*   **Guardar mensajes:**
    ```sql
    INSERT INTO chat_messages (session_id, role, content, agent_type, created_at) VALUES (?, ?, ?, ?, ?)
    ```
*   **Actualizar resumenes de charla (Upsert):**
    ```sql
    UPDATE chatbot_memory SET context=?, summary=?, updated_at=? WHERE session_id=?
    ```
*   **Recuperar charlas:**
    ```sql
    SELECT * FROM chatbot_memory WHERE session_id = ? ORDER BY updated_at DESC
    ```

**Conclusion:**
1. Fabric: T-SQL ultra estructurado y protegido para extraer el bruto.
2. Memoria SQLite: Terreno de juegos rapido y desechable donde el IA arma sus "SELECTS" de analisis con funciones de SQLite.
