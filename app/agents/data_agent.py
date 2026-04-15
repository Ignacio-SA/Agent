import os
import re
import sqlite3
import struct
from datetime import datetime, timedelta, timezone

from anthropic import Anthropic

from ..config import settings
from ..db.sales_repo import sales_repo

_RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "context", "business_rules.md")


def _load_business_rules() -> str:
    try:
        with open(_RULES_PATH, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


class DataAgent:
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-haiku-4-5-20251001"

    def _load_into_memory(self, sales: list[dict]) -> sqlite3.Connection:
        """Carga los datos del SP en una tabla SQLite en memoria."""
        conn = sqlite3.connect(":memory:")
        if not sales:
            conn.execute("""
                CREATE TABLE ventas (
                    id TEXT, FranchiseeCode TEXT, ShiftCode TEXT, PosCode TEXT,
                    UserName TEXT, SaleDateTimeUtc TEXT, Quantity REAL,
                    ArticleId TEXT, ArticleDescription TEXT, TypeDetail TEXT, UnitPriceFix REAL
                )
            """)
            return conn

        columns = list(sales[0].keys())
        cols_def = ", ".join([f'"{c}" TEXT' for c in columns])
        conn.execute(f"CREATE TABLE ventas ({cols_def})")

        def fmt(v):
            if v is None:
                return None
            # DATETIMEOFFSET llega como bytes raw del ODBC driver (20 bytes)
            # Formato: year(h) month(H) day(H) hour(H) minute(H) second(H) fraction_ns(I) tz_h(h) tz_m(h)
            if isinstance(v, (bytes, bytearray)) and len(v) == 20:
                year, month, day, hour, minute, second, fraction, tz_h, tz_m = struct.unpack('<hHHHHHIhh', v)
                microsecond = fraction // 1000
                tz = timezone(timedelta(hours=tz_h, minutes=tz_m))
                dt = datetime(year, month, day, hour, minute, second, microsecond, tzinfo=tz)
                # Guardar en hora local (ya viene en -03:00 gracias a SWITCHOFFSET)
                return dt.strftime("%Y-%m-%d %H:%M:%S.%f")
            if hasattr(v, "strftime"):
                return v.strftime("%Y-%m-%d %H:%M:%S.%f")
            # Limpiar timezone offset de strings
            return re.sub(r'\s*[+-]\d{2}:\d{2}$', '', str(v))

        placeholders = ", ".join(["?" for _ in columns])
        for row in sales:
            conn.execute(
                f"INSERT INTO ventas VALUES ({placeholders})",
                [fmt(v) for v in row.values()],
            )
        conn.commit()
        return conn

    def _generate_sql(self, user_message: str, total_rows: int, today: str) -> str:
        """LLM genera el SQL apropiado para la pregunta del usuario."""
        business_rules = _load_business_rules()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            temperature=0,
            system=f"""Eres un experto en SQL. Genera UNA sola consulta SQL para responder la pregunta del usuario.

Total de registros en la tabla: {total_rows}
Fecha de hoy: {today}

Reglas IMPORTANTES de SQL (SQLite):
- Responde SOLO con la consulta SQL, sin explicaciones ni markdown ni bloques de código
- La base de datos es SQLite — usa SOLO funciones SQLite:
  * Para año: strftime('%Y', SaleDateTimeUtc)
  * Para mes: strftime('%m', SaleDateTimeUtc)
  * Para año-mes: strftime('%Y-%m', SaleDateTimeUtc)
  * Para fecha: DATE(SaleDateTimeUtc)
  * NUNCA uses YEAR(), MONTH(), DATEPART() — no existen en SQLite
- Para "hoy" usa: DATE(SaleDateTimeUtc) = '{datetime.now().strftime("%Y-%m-%d")}'
- Para "ayer" usa: DATE(SaleDateTimeUtc) = date('{datetime.now().strftime("%Y-%m-%d")}', '-1 day')
- Para totales usa COUNT o SUM según corresponda
- NO uses LIMIT salvo que el usuario pida explícitamente un "top N" o "los N más..."

---
{business_rules}
""",
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip().strip("```sql").strip("```").strip()

    def _execute_sql(self, mem_conn: sqlite3.Connection, sql: str) -> tuple[list, list]:
        """Ejecuta el SQL generado y retorna columnas + filas."""
        try:
            cursor = mem_conn.execute(sql)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return columns, rows
        except Exception as e:
            return [], [("Error en SQL", str(e))]

    def _compute_summary(self, mem_conn: sqlite3.Connection) -> str:
        """Calcula todas las métricas en Python (sin LLM) para evitar inconsistencias."""
        try:
            totals = mem_conn.execute("""
                SELECT COUNT(DISTINCT id),
                       ROUND(SUM(CAST(Quantity AS REAL) * CAST(UnitPriceFix AS REAL)), 2),
                       COUNT(DISTINCT UserName)
                FROM ventas
            """).fetchone()

            by_vendor = mem_conn.execute("""
                SELECT UserName,
                       COUNT(DISTINCT id),
                       ROUND(SUM(CAST(Quantity AS REAL) * CAST(UnitPriceFix AS REAL)), 2)
                FROM ventas
                GROUP BY UserName ORDER BY 3 DESC
            """).fetchall()

            top_products = mem_conn.execute("""
                SELECT ArticleDescription,
                       SUM(CAST(Quantity AS REAL)),
                       ROUND(SUM(CAST(Quantity AS REAL) * CAST(UnitPriceFix AS REAL)), 2)
                FROM ventas
                GROUP BY ArticleDescription ORDER BY 2 DESC LIMIT 10
            """).fetchall()

            hourly = mem_conn.execute("""
                SELECT strftime('%H', SaleDateTimeUtc),
                       COUNT(DISTINCT id)
                FROM ventas
                GROUP BY 1 ORDER BY 2 DESC LIMIT 5
            """).fetchall()

            def fmt(n):
                return f"${n:,.0f}".replace(",", ".")

            lines = [
                "=== DATOS PRE-CALCULADOS (usar exactamente estos números) ===",
                "",
                f"RESUMEN GENERAL:",
                f"- Transacciones: {totals[0]}",
                f"- Total ventas: {fmt(totals[1])}",
                f"- Vendedores activos: {totals[2]}",
                "",
                "POR VENDEDOR:",
            ]
            for v in by_vendor:
                lines.append(f"  • {v[0]}: {v[1]} transacciones | {fmt(v[2])}")

            lines += ["", "TOP PRODUCTOS (por unidades):"]
            for p in top_products:
                lines.append(f"  • {p[0]}: {p[1]:.0f} unidades | {fmt(p[2])}")

            lines += ["", "HORAS MÁS ACTIVAS (transacciones únicas):"]
            for h in hourly:
                lines.append(f"  • {h[0]}:00 hs — {h[1]} transacciones")

            return "\n".join(lines)
        except Exception:
            return ""

    def _format_response(self, user_message: str, sql: str, columns: list, rows: list, summary: str) -> str:
        """LLM formatea los resultados en lenguaje natural."""
        business_rules = _load_business_rules()

        # Para respuestas con muchas filas, usar solo los datos pre-calculados
        if len(rows) > 20:
            data_content = f"(Datos detallados omitidos — usar solo los datos pre-calculados del sistema)"
        else:
            data_content = f"Columnas: {columns}\nResultados: {rows}"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=0,
            system=f"""Eres un asistente de ventas. Presenta los resultados de forma clara y estructurada en español. Usa formato markdown con tablas o listas cuando sea útil.

INSTRUCCIÓN CRÍTICA: Los siguientes datos fueron calculados con precisión en Python. Úsalos EXACTAMENTE como aparecen. NO recalcules ni modifiques ningún número.

{summary}

Reglas de presentación:
{business_rules}""",
            messages=[{
                "role": "user",
                "content": f"Pregunta: {user_message}\n{data_content}"
            }],
        )
        return response.content[0].text

    def _extract_date_range(self, user_message: str) -> tuple[datetime | None, datetime | None]:
        """Extrae el rango de fechas del mensaje para pasarlo al SP."""
        now = datetime.now()
        today = now.date()

        response = self.client.messages.create(
            model=self.model,
            max_tokens=60,
            temperature=0,
            system=f"""Hoy es {today}. Extrae el rango de fechas del mensaje.
Responde SOLO con JSON: {{"date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD"}}
Si no hay fecha específica responde: {{"date_from": null, "date_to": null}}""",
            messages=[{"role": "user", "content": user_message}],
        )

        import json
        try:
            text = response.content[0].text.strip()
            start = text.find("{")
            data = json.loads(text[start:text.rfind("}") + 1])
            date_from = datetime.strptime(data["date_from"], "%Y-%m-%d") if data.get("date_from") else None
            date_to = datetime.strptime(data["date_to"] + " 23:59:59", "%Y-%m-%d %H:%M:%S") if data.get("date_to") else None
            return date_from, date_to
        except Exception:
            return None, None

    def _dump_to_local_sql_server(self, sales: list):
        """Tool de Diagnóstico Definitiva: Impacta batch a localhost\\SQLEXPRESS"""
        if not sales:
            return
        try:
            import pyodbc
            connection_string = "Driver={ODBC Driver 17 for SQL Server};Server=localhost\\SQLEXPRESS;Database=BasePruebaMCP;Trusted_Connection=yes;"
            conn = pyodbc.connect(connection_string, autocommit=True)
            cursor = conn.cursor()
            
            cursor.execute("IF OBJECT_ID('ventas_chatbot_debug', 'U') IS NOT NULL DROP TABLE ventas_chatbot_debug;")
            columns = list(sales[0].keys())
            cols_def = ", ".join([f"[{c}] NVARCHAR(MAX)" for c in columns])
            cursor.execute(f"CREATE TABLE ventas_chatbot_debug ({cols_def});")
            
            placeholders = ",".join(["?" for _ in columns])
            insert_q = f"INSERT INTO ventas_chatbot_debug VALUES ({placeholders})"
            
            for row in sales:
                vals = [str(v) if v is not None else None for v in row.values()]
                cursor.execute(insert_q, vals)
                
            print(f"[DataAgent] DUMPER: {len(sales)} filas impactadas exitosamente en localhost\\SQLEXPRESS -> BasePruebaMCP.dbo.ventas_chatbot_debug")
            conn.close()
        except Exception as e:
            print(f"[DataAgent] Omitiendo Dumper local (ignorado o sin acceso). Razón: {e}")

    def process_data_request(self, user_message: str, franchise_code: str, context: str = "") -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        
        print("\n[DataAgent] --- INICIO FLUJO TEXT-TO-SQL ---")

        # 1. Extraer rango de fechas del mensaje para filtrar en el SP
        date_from, date_to = self._extract_date_range(user_message)
        print(f"[DataAgent] (Paso 1) Extracción de Fechas/Horarios: {date_from} -> {date_to}")

        # 2. Obtener datos del SP (solo el rango necesario)
        print(f"[DataAgent] (Paso 2) Llamada de consulta al Store Procedure para franquicia '{franchise_code}'...")
        sales = sales_repo.get_sales(franchise_code, date_from=date_from, date_to=date_to)
        
        # Si se desea depurar en SSMS local, descomentar:
        self._dump_to_local_sql_server(sales)

        # 3. Cargar en SQLite en memoria
        print(f"[DataAgent] (Paso 3) Volcando tablas ({len(sales)} filas) hacia SQLite RAM temporal")
        if sales:
            print("[DataAgent] Vista previa tabular (primeros 5 renglones exactos de Azure):")
            keys = list(sales[0].keys())
            column_widths = {k: min(20, max(len(str(k)), 10)) for k in keys}
            
            header = " | ".join([str(k).ljust(column_widths[k])[:column_widths[k]] for k in keys])
            print(f"   {header}")
            print(f"   {'-'*len(header)}")
            
            for r in sales[:5]:
                row_str = " | ".join([str(v).ljust(column_widths[k])[:column_widths[k]] for k, v in r.items()])
                print(f"   {row_str}")
                
        mem_conn = self._load_into_memory(sales)

        # 4. LLM genera SQL
        print("[DataAgent] (Paso 4) Consultando SQL nativo al modelo...")
        sql = self._generate_sql(user_message, len(sales), today)
        print(f"[DataAgent] Código generado puro:\n-----\n{sql}\n-----")

        # 5. Ejecutar SQL
        print("[DataAgent] (Paso 5) Ejecutando SQL sobre SQLite local...")
        columns, rows = self._execute_sql(mem_conn, sql)
        print(f"[DataAgent] Ejecución exitosa. Filas retornadas del motor: {len(rows)}")

        # 6. Calcular métricas en Python (sin LLM)
        summary = self._compute_summary(mem_conn)
        mem_conn.close()

        # 7. LLM formatea la respuesta
        print("[DataAgent] (Paso 6) Llamado final para traducción humano-natural...")
        res = self._format_response(user_message, sql, columns, rows, summary)
        print("[DataAgent] --- FIN FLUJO TEXT-TO-SQL ---\n")
        return res


data_agent = DataAgent()
