# Guía Completa: Entendiendo la Magia del SQL del Proyecto

Si querés entender cómo este Asistente Virtual puede responder a las preguntas de una franquicia sin destruir la base de datos ni tardar años en contestar, estás en el lugar correcto.

Este documento explica el "detrás de escena" paso a paso: desde que la data en bruto está en la nube (Microsoft Fabric) hasta que la Inteligencia Artificial (Claude) analiza los resultados en un espacio 100% seguro.

---

## 1. El Flujo de los Datos: La Estrategia en "Dos Pasos"

El proyecto fue diseñado de una forma inteligente para mezclar los mundos de Data Engineering y de IA separando responsabilidades:

1.  **Fase de Nube ("Extraer"):** La aplicación Python va hasta la base de datos real (Fabric) y extrae de forma ultra-rápida y masiva solo la data pertinente de ese usuario de forma estandarizada.
2.  **Fase de Memoria Temporal ("Analizar"):** La app "tira" la data en una tabla que existe solo adentro de la memoria RAM del servidor. Luego encierra al bot de inteligencia artificial ahí dentro y le dice: *"Jugá con estos datos y devolveme respuestas"*. 

---

## 2. Fase de Nube: El Stored Procedure en Fabric

Un **Stored Procedure (o Procedimiento Almacenado)** es código SQL pre-programado y guardado en la propia base de datos. Imaginalo como una "función" o un script en la nube. 
En lugar de mandar un testamento de código a través de internet en cada pregunta que hace el usuario, Python manda un comando minúsculo: `"Che Fabric, corré esta función y pasale el ID de la franquicia"`.

### ¿Por qué lo usamos?
*   **Seguridad:** El IA jamás toca la base de código real de Azure/Fabric. No hay forma de que el IA escriba un `DROP TABLE` por error.
*   **Velocidad:** Fabric precalcula la mejor forma estadística de correr ese código y lo hace hiper-rápido.
*   **Encapsulamiento:** Toda la lógica sucia (conversión de fechas, cruces complejos) se la come Fabric y le devuelve Python todo limpito.

### El análisis del Stored Procedure `sp_GetSalesForChatbot`

Este es el encargado de buscar la data bruta de las ventas. Hace el trabajo pesado en 3 frentes importantes:

#### A. El Cruce Clásico (**Header** vs **Detalle**)
Las ventas casi siempre se modelan en dos tablas separadas:
1.  La **Tabla de Cabecera (El Ticket General):** Guarda que el ticket #123 fue hecho a tal hora, en el cajero "Matias" y de la Franquicia "Palermo". El proyecto la llama `dt_silver_ingested_cosmos_sales_header`. (Alias `h`)
2.  La **Tabla de Detalle/Productos:** Guarda que el ticket #123 llevó 2 Coca-Colas y 1 Hamburguesa. El proyecto la llama `vw_Silver_Cloud_NewDetails`. (Alias `d`)

El Procedimiento hace un cruce uniendo el identificador común:
```sql
FROM [dbo].[dt_silver_ingested_cosmos_sales_header] h
JOIN [dbo].[vw_Silver_Cloud_NewDetails] d ON h.id = d.SaleDocId
```

#### B. El Filtro Único por Franquicia
Se encarga de no exponer info ajena:
```sql
WHERE h.FranchiseCode = @FranchiseCode     -- @FranchiseCode viene como parámetro desde Python
```

#### C. Corrección del Huso Horario
Fabric suele trabajar con fecha Universal (`UTC +0`). El Procedimiento es inteligente y usa la función `SWITCHOFFSET` para modificar *al vuelo* el huso horario para que las fechas queden en el formato local de Argentina (UTC-3):
```sql
SWITCHOFFSET(TRY_CONVERT(DATETIMEOFFSET, d.SaleDateTimeUtc), '-03:00')
```

---

## 3. La Fase de Memoria: El nacimiento de la Tabla Plana

Luego de que Fabric procesa el Procedimiento Almacenado, devuelve muchísimas filas y la aplicación Python las vuelca usando la librería "SQLite" hacia una tabla armada en la Memoria RAM. Esta tabla temporal se llama, de forma súper genérica: **`ventas`**.

### ¿Qué es una Tabla Plana?
Como en Fabric unimos la "cabecera" con las líneas de "detalle", el resultado final hace que los datos generales se repitan tantas veces como items llevó el cliente. 

**Ejemplo representativo de cómo se ve la tabla en Memoria RAM (`ventas`):**

| id (Ticket) | UserName | FranchiseeCode | SaleDateTimeUtc | ArticleDescription | Quantity | UnitPriceFix | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| \#0001 | Matias | FRA_100 | 2026-04-09 15:30:00 | Coca Cola Regular | 2 | 1500.00 | 1 |
| \#0001 | Matias | FRA_100 | 2026-04-09 15:30:00 | Hamburguesa con Queso | 1 | 4000.00 | 1 |
| \#0002 | Romina | FRA_100 | 2026-04-09 15:32:00 | Papas Fritas Chicas | 1 | 900.00 | 1 |

_¡Fijate como el ticket #0001 generó DOS filas! La info del turno y la fecha son idénticas._

---

## 4. El Cerebro entra al ring (A.K.A Text-To-SQL)

¡Toda esta estructura fue armada para el momento estelar de la IA (modelo Claude Haiku)! 

El bot vive adentro de esta memoria y el sistema se apoya en una técnica moderna de Inteligencia Artificial que se llama **Text-To-SQL**: Es agarrar cualquier pregunta hablada en español que haga el dueño de la franquicia en el chat, e instruir al modelo a que **escriba por su cuenta la Query SQLite que responde esa pregunta.**

### Ejemplos Completos y Prácticos:

**Conversación #1:**
*   👤 **El dueño escribe:** *"Hicimos plata hoy? Cuantas cosas vendí a la mañana?"*
*   🤖 **El agente de Datos piensa la query SQLite:** (Suponiendo que el modelo detecta que 'mañana' es el shift '1')
    ```sql
    SELECT SUM(Quantity), SUM(Quantity * UnitPriceFix) 
    FROM ventas 
    WHERE DATE(SaleDateTimeUtc) = '2026-04-09' AND ShiftCode = '1'
    ```
*   💾 **La Query se ejecuta en la RAM y devuelve:** `[ (145, 235000.0) ]`
*   🤖 **El agente lee ese resultado y lo formatea para el usuario:** *"¡Excelente día! En el turno mañana vendimos 145 artículos consiguiendo sumar un total de $235.000."*

**Conversación #2:**
*   👤 **El dueño escribe:** *"Che, el articulo coca regular lo vendio matias hoy?"*
*   🤖 **El agente de Datos piensa la query:** (Acá vemos la importancia del Business Rules del proyecto que dice que siempre debemos usar comodines `LIKE`)
    ```sql
    SELECT COUNT(*) 
    FROM ventas 
    WHERE LOWER(ArticleDescription) LIKE LOWER('%coca%regular%') 
      AND LOWER(UserName) LIKE LOWER('%matias%')
      AND DATE(SaleDateTimeUtc) = '2026-04-09'
    ```
*   💾 **Resultado en RAM:** `[(2)]`
*   🤖 **Respuesta formal:** *"Sí, revisé los registros y se vendieron 2 Coca Cola Regular operadas por el usuario Matias el día de hoy."*

### Final de la ejecución
Una vez que el backend armó el mensaje y se lo mandó de vuelta a la página web, **se acaba el tiempo de vida de la SQLite.** El Python elimina de la memoria RAM la tabla `ventas` y todo su contenido, asegurando un consumo mínimo del servidor e impidiendo que alguien pueda inyectarle cosas perniciosas y persistentes a la herramienta.
