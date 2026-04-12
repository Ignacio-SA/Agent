import json
from datetime import datetime

from anthropic import Anthropic

from ..config import settings
from ..db.training_repo import training_memory


class TrainingAgent:
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-haiku-4-5-20251001"

    def process_feedback(self, session_id: str, history: list[dict], feedback_message: str) -> dict:
        """
        Analiza el ciclo consulta→respuesta→feedback y genera sugerencias.
        Retorna el dict de sugerencia generado.
        """
        history_text = self._format_history(history)
        recent_entries = training_memory.get_recent_entries(5)
        recent_context = self._format_recent_entries(recent_entries)

        system_prompt = f"""Eres un analista de calidad de un chatbot de ventas para franquiciados.
Tu trabajo es analizar el ciclo de feedback del usuario y generar sugerencias de mejora.

El chatbot tiene estos componentes críticos:
- data_agent: genera y ejecuta queries SQL sobre datos de ventas. Usa business_rules.md como guía.
- orchestrator: clasifica mensajes en data_query, interaction, feedback, off_topic.
- interaction: responde saludos y preguntas generales sobre el negocio.
- business_rules: reglas de negocio inyectadas en el data_agent.

Analiza el historial y el feedback. Responde SOLO con JSON válido:
{{
  "type": "positivo" o "negativo",
  "user_message": "la pregunta original del usuario",
  "agent_response": "resumen breve de la respuesta del agente",
  "feedback": "el feedback textual del usuario",
  "component": "data_agent" | "orchestrator" | "interaction" | "business_rules",
  "cause": "descripción de la causa raíz del problema o del acierto",
  "suggestion": "sugerencia concreta de mejora o patrón a mantener",
  "priority": "alta" | "media" | "baja"
}}

Criterios de prioridad:
- alta: datos incorrectos, queries fallidas, clasificación errónea
- media: respuestas imprecisas o incompletas, formato mejorable
- baja: preferencias de estilo, sugerencias menores

{recent_context}"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": f"Historial de la sesión:\n{history_text}\n\nFeedback actual del usuario: \"{feedback_message}\"\n\nAnaliza y responde SOLO con el JSON."
                }],
            )

            text = response.content[0].text.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            suggestion = json.loads(text[start:end])

            suggestion["session_id"] = session_id
            suggestion["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M")

            training_memory.add_suggestion(suggestion)
            return suggestion

        except Exception as e:
            fallback = {
                "session_id": session_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "type": "negativo",
                "user_message": feedback_message,
                "agent_response": "N/A",
                "feedback": feedback_message,
                "component": "unknown",
                "cause": f"Error al analizar feedback: {e}",
                "suggestion": "Revisar manualmente este feedback",
                "priority": "media",
            }
            training_memory.add_suggestion(fallback)
            return fallback

    def _format_history(self, history: list[dict]) -> str:
        """Formatea el historial de mensajes para el prompt."""
        lines = []
        for msg in history[-10:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            agent = msg.get("agent_type", "")
            label = "Usuario" if role == "user" else f"Agente ({agent})" if agent else "Agente"
            lines.append(f"[{label}]: {content}")
        return "\n".join(lines)

    def _format_recent_entries(self, entries: list[dict]) -> str:
        """Formatea entradas recientes como contexto adicional."""
        if not entries:
            return ""

        lines = ["Sugerencias previas relevantes (para no repetir análisis):"]
        for e in entries:
            comp = e.get("component", "?")
            sug = e.get("suggestion", "?")
            lines.append(f"- [{comp}] {sug}")
        return "\n".join(lines)


training_agent = TrainingAgent()
