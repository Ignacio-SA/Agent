import sqlite3
from datetime import datetime

from anthropic import Anthropic

from ..config import settings
from ..db.sales_repo import sales_repo


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
        cols_def = ", ".join([f"{c} TEXT" for c in columns])
        conn.execute(f"CREATE TABLE ventas ({cols_def})")

        placeholders = ", ".join(["?" for _ in columns])
        for row in sales:
            conn.execute(
                f"INSERT INTO ventas VALUES ({placeholders})",
                [str(v) if v is not None else None for v in row.values()],
            )
        conn.commit()
        return conn

    def _generate_sql(self, user_message: str, total_rows: int, today: str) -> str:
        """LLM genera el SQL apropiado para la pregunta del usuario."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            system=f"""Eres un experto en SQL. Genera UNA sola consulta SQL para responder la pregunta del usuario.

La tabla se llama 'ventas' y tiene estas columnas:
- id: identificador de la venta
- FranchiseeCode: código del franquiciado
- ShiftCode: código de turno
- PosCode: código del punto de venta (POS)
- UserName: nombre del vendedor
- SaleDateTimeUtc: fecha y hora de la venta (texto ISO)
- Quantity: cantidad vendida
- ArticleId: código del artículo
- ArticleDescription: descripción del artículo
- TypeDetail: tipo de detalle
- UnitPriceFix: precio unitario

Total de registros en la tabla: {total_rows}
Fecha de hoy: {today}

Reglas IMPORTANTES:
- Responde SOLO con la consulta SQL, sin explicaciones ni markdown ni bloques de código
- La base de datos es SQLite — usa SOLO funciones SQLite:
  * Para año: strftime('%Y', SaleDateTimeUtc)
  * Para mes: strftime('%m', SaleDateTimeUtc)
  * Para año-mes: strftime('%Y-%m', SaleDateTimeUtc)
  * Para fecha: DATE(SaleDateTimeUtc)
  * NUNCA uses YEAR(), MONTH(), DATEPART() — no existen en SQLite
- Para "hoy" usa: DATE(SaleDateTimeUtc) = '{datetime.now().strftime("%Y-%m-%d")}'
- Para totales usa COUNT o SUM según corresponda
- Limita resultados con LIMIT 50 si es un detalle
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

    def _format_response(self, user_message: str, sql: str, columns: list, rows: list) -> str:
        """LLM formatea los resultados en lenguaje natural."""
        results_text = f"Columnas: {columns}\nResultados ({len(rows)} filas): {rows[:30]}"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=800,
            system="Eres un asistente de ventas. Presenta los resultados de forma clara y estructurada en español. Usa formato markdown con tablas o listas cuando sea útil.",
            messages=[{
                "role": "user",
                "content": f"Pregunta: {user_message}\nSQL ejecutado: {sql}\n{results_text}"
            }],
        )
        return response.content[0].text

    def process_data_request(self, user_message: str, franchise_code: str, context: str = "") -> str:
        today = datetime.now().strftime("%Y-%m-%d")

        # 1. Obtener datos del SP
        sales = sales_repo.get_sales(franchise_code)

        # 2. Cargar en SQLite en memoria
        mem_conn = self._load_into_memory(sales)

        # 3. LLM genera SQL
        sql = self._generate_sql(user_message, len(sales), today)

        # 4. Ejecutar SQL
        columns, rows = self._execute_sql(mem_conn, sql)
        mem_conn.close()

        # 5. LLM formatea la respuesta
        return self._format_response(user_message, sql, columns, rows)


data_agent = DataAgent()
