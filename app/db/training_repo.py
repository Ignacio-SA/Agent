import os
import re
from datetime import datetime


_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "context", "training_log.md")


class TrainingMemory:
    def __init__(self):
        self._context: list[dict] = []
        self._log_path: str = _LOG_PATH
        self._max_context_entries: int = 20

    def load_from_disk(self) -> None:
        """Lee training_log.md al iniciar la app y carga las últimas N entradas."""
        if not os.path.exists(self._log_path):
            return

        try:
            with open(self._log_path, encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return

        entries = self._parse_entries(content)
        self._context = entries[-self._max_context_entries:]

    def _parse_entries(self, content: str) -> list[dict]:
        """Parsea el archivo training_log.md y devuelve lista de dicts."""
        raw_entries = re.split(r"(?=^## \[)", content, flags=re.MULTILINE)
        entries = []

        for raw in raw_entries:
            raw = raw.strip()
            if not raw.startswith("## ["):
                continue

            entry = {}

            header_match = re.search(
                r"## \[(.+?)\] Sesión: (.+?) \| Tipo: (.+)", raw
            )
            if header_match:
                entry["timestamp"] = header_match.group(1)
                entry["session_id"] = header_match.group(2)
                entry["type"] = header_match.group(3).strip()

            chat_match = re.search(
                r"\*\*Chat analizado:\*\*\s*\n(.*?)(?=\n\*\*Componente)",
                raw,
                re.DOTALL,
            )
            if chat_match:
                entry["chat"] = chat_match.group(1).strip()

            component_match = re.search(
                r"\*\*Componente afectado:\*\*\s*(.+)", raw
            )
            if component_match:
                entry["component"] = component_match.group(1).strip()

            cause_match = re.search(
                r"\*\*Causa raíz identificada:\*\*\s*\n(.*?)(?=\n\*\*Sugerencia)",
                raw,
                re.DOTALL,
            )
            if cause_match:
                entry["cause"] = cause_match.group(1).strip()

            suggestion_match = re.search(
                r"\*\*Sugerencia de cambio:\*\*\s*\n(.*?)(?=\n\*\*Prioridad)",
                raw,
                re.DOTALL,
            )
            if suggestion_match:
                entry["suggestion"] = suggestion_match.group(1).strip()

            priority_match = re.search(r"\*\*Prioridad:\*\*\s*(.+)", raw)
            if priority_match:
                entry["priority"] = priority_match.group(1).strip()

            entry["raw"] = raw
            entries.append(entry)

        return entries

    def add_suggestion(self, suggestion: dict) -> None:
        """Agrega sugerencia a RAM y hace append en training_log.md."""
        self._context.append(suggestion)
        if len(self._context) > self._max_context_entries:
            self._context = self._context[-self._max_context_entries:]

        md_entry = self._format_entry(suggestion)
        try:
            os.makedirs(os.path.dirname(self._log_path), exist_ok=True)

            if not os.path.exists(self._log_path):
                with open(self._log_path, "w", encoding="utf-8") as f:
                    f.write("# Training Log — Registro de Entrenamiento\n\n")

            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(md_entry)
        except Exception as e:
            print(f"[TrainingMemory] Error escribiendo log: {e}")

    def _format_entry(self, suggestion: dict) -> str:
        """Formatea una sugerencia como entrada markdown para el log."""
        now = suggestion.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))
        session = suggestion.get("session_id", "unknown")
        entry_type = suggestion.get("type", "negativo")
        user_msg = suggestion.get("user_message", "N/A")
        agent_resp = suggestion.get("agent_response", "N/A")
        feedback = suggestion.get("feedback", "N/A")
        component = suggestion.get("component", "unknown")
        cause = suggestion.get("cause", "N/A")
        change = suggestion.get("suggestion", "N/A")
        priority = suggestion.get("priority", "media")

        return f"""
## [{now}] Sesión: {session} | Tipo: {entry_type}

**Chat analizado:**
- Usuario preguntó: "{user_msg}"
- Agente respondió: "{agent_resp}"
- Feedback recibido: "{feedback}"

**Componente afectado:** {component}

**Causa raíz identificada:**
{cause}

**Sugerencia de cambio:**
{change}

**Prioridad:** {priority}
---
"""

    def get_context_for_prompt(self) -> str:
        """Devuelve string formateado con las sugerencias relevantes para inyectar."""
        if not self._context:
            return ""

        relevant = [e for e in self._context if e.get("priority") in ("alta", "media")]
        if not relevant:
            relevant = self._context[-5:]
        else:
            relevant = relevant[-10:]

        lines = []
        for entry in relevant:
            component = entry.get("component", "")
            suggestion = entry.get("suggestion", entry.get("raw", ""))
            cause = entry.get("cause", "")
            entry_type = entry.get("type", "")

            if entry_type == "positivo":
                lines.append(f"✅ PATRÓN EXITOSO ({component}): {suggestion}")
            else:
                lines.append(f"⚠️ CORRECCIÓN ({component}): {cause} → {suggestion}")

        return "\n".join(lines)

    def get_recent_entries(self, n: int = 5) -> list[dict]:
        """Devuelve las últimas N sugerencias para el training_agent."""
        return self._context[-n:]


training_memory = TrainingMemory()
