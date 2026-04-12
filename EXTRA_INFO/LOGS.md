# Registro de Cambios: Trazabilidad, Debugging Seguro y Correcciones

Este resumen documenta los cambios estructurales aplicados localmente frente a la rama `main`. El objetivo de estas implementaciones fue diagnosticar con precisión fallas del flujo Text-to-SQL, proveer completa visibilidad en consola de cada paso del agente y proteger excepciones internas.

## 1. Ruteo Global y Sistema de Memoria (`app/routers/chat.py`)
Se implementaron cabeceras visuales para demarcar el inicio o fin del ciclo de vida de un request.

* **Nuevos Logs agregados:**
  * `[Router Global]` Nueva petición recibida (informando el número de ID de sesión).
  * `[MemoryAgent]` Rescatando y exponiendo en consola si se adjuntó historial previo contextual (para saber exactamente de qué "se acuerda" la IA entre turnos).

## 2. Visión del Orquestador (`app/agents/orchestrator.py`)
Se añadió trazabilidad para interceptar la respuesta de *Claude Sonnet* (Orquestador principal) en el instante que decide la derivación:

* **Nuevos Logs agregados:**
  * `[Orchestrator]` Mensaje recibido a la espera de derivación.
  * `[Orchestrator]` Exposición pública del "Agente Final" seleccionado y, fundamental para auditar, **la Razón Pensada por el Modelo** (el razonamiento psicológico por el que el LLM optó por *data* vs *interaction*).
  * Logs secundarios detallando si el ruteo se dio por *Default/Keyword Fallback* en caso de que falle la API principal.

## 3. Radiografía Text-to-SQL y Extracción de Datos (`app/agents/data_agent.py`)
Dado que `DataAgent` es el motor central lógico y el factor de riesgo, se instrumentó un verbose a nivel de "Pasos", junto a una protección masiva.

* **Añadidos Principales y Trazabilidad:**
  * **(Paso 1)** `[DataAgent]` Extracción y parseo de las de Fechas/Horarios extraídas por la Inteligencia Artificial.
  * **(Paso 2)** `[DataAgent]` Llamada de consulta al Store Procedure (Fabric) para la Franquicia identificada.
  * **(Paso 3)** `[DataAgent]` Volcado de tablas hacia la SQLite RAM temporal, acompañada de una **vista previa tabular dinámica** en consola que imprime visualmente los primeros 5 renglones exactos que recibe de Azure.
  * **(Paso 4)** `[DataAgent]` Impresión inmediata del Código de Inteligencia Artificial (SQL) puro generado por el LLM.
  * **(Paso 5)** `[DataAgent]` Ejecución estricta del SQL recién creado y cantidad de filas devueltas generadas de regreso del motor SQLite local.
  * **(Paso 6)** `[DataAgent]` Llamado final para traducción humano-natural y respuesta al chat web.

* **Dumper Local Estricto (Tool de Diagnóstico Definitiva):**
  * Se inyectó código en `_dump_to_local_sql_server(self, sales: list)` que intercepta el *batch* devuelto por MS Fabric y lo impacta usando PyODBC dentro de un servidor SQL **local** (`localhost\SQLEXPRESS`). 
  * Este paso crea y sobreescribe dinámicamente `[BasePruebaMCP].[dbo].[ventas_chatbot_debug]`. La finalidad es que el desarrollador pueda reproducir consultas SQLite desde SSMS/ADS y certificar que la data es correcta.

## 4. Estabilidad y Protecciones Críticas (Drivers y SQLite)
* **`app/db/connection.py`**:
  * Se restauró (o blindó) el uso de la directiva explícita `add_output_converter(-155, lambda x: x)` en la lógica de pyODBC. Esto evita fallos fatales de tipo `ODBC SQL type -155 is not yet supported` provistos fundamentalmente por el parseo incorrecto de columnas `DATETIMEOFFSET`. Ahora se leen como bytes crudos y se dejan formatear localmente sin petar el flujo.
* **`app/db/memory_repo.py`**:
  * Se insertó un control estricto que intercepta en seco a `content` (`if content is None: content = ""`).
  * *Motivo:* Si por algún error subyacente del LLM la cadena retornaba como "Null", el motor SQlite que guardaba los resúmenes del chat crasheaba con la directiva *NOT NULL Constraint Failed*. Esta pequeña línea lo vuelve anti-roturas.

## 5. Edición Provisional de Negocio (`context/business_rules.md`)
* Se removió temporalmente la obligación algorítmica de encadenar `WHERE Type = '1'` para consultas generales. Al haber disonancia con los importes que otorga la BD Fabric por default (cuyas variables difirieron de lo que la regla de negocio mandaba como único estándar), quitamos el candado para permitir que la Inteligencia Artificial analice sumatorias y conteos brutos.
