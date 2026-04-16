import json

from anthropic import Anthropic

from ..config import settings
from ..db.training_repo import training_memory


class OrchestratorAgent:
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key, max_retries=3)
        self.model = "claude-sonnet-4-6"

    def decide_agent(self, user_message: str, memory_context: str = "", training_mode: bool = False) -> dict:
        """
        Claude Sonnet decide cuál sub-agente activar.
        Retorna: {agent_type, reasoning, params}
        """
        print(f"[Orchestrator] Mensaje recibido a la espera de derivación: '{user_message}'")
        system_prompt = """Eres un orquestador de un chatbot de ventas para franquiciados. Clasifica el mensaje:

1. "data" — consultas de ventas, productos, artículos, precios, turnos, POS, reportes, métricas del negocio.
2. "interaction" — saludos, preguntas sobre cómo usar el chatbot, conversación mínima relacionada con el negocio.
3. "feedback" — el usuario da feedback sobre una respuesta anterior:
   - Corrección explícita: "eso está mal", "no era eso", "te equivocaste", "incorrecto"
   - Aprobación explícita: "perfecto", "exacto", "eso era", "muy bien", "correcto"
   - Reformulación correctiva: "quise decir...", "en realidad era...", "lo que necesitaba era..."
   - Cualquier reacción directa a la respuesta anterior del bot
4. "off_topic" — todo lo demás: programación, clima, traducción, noticias, matemáticas, temas sin relación con el negocio.

Si hay duda entre "data" e "interaction", usar "data".
Si hay duda entre "feedback" y otro tipo, considerar el contexto de los últimos mensajes.

Responde SOLO con JSON: {"agent_type": "", "reasoning": "", "should_use_memory": bool}"""

        context = f"Contexto de memoria: {memory_context}" if memory_context else ""

        training_context = ""
        if training_mode:
            tc = training_memory.get_context_for_prompt()
            if tc:
                training_context = f"\n\n=== CONTEXTO DE ENTRENAMIENTO ACTIVO ===\nLas siguientes son sugerencias de mejora basadas en feedback previo de usuarios.\nTené en cuenta estos patrones al clasificar:\n{tc}"

        full_system = system_prompt + training_context

        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            temperature=0,
            system=full_system,
            messages=[{"role": "user", "content": f"{context}\nMensaje del usuario: {user_message}\n\nResponde SOLO con el JSON, sin texto adicional."}],
        )

        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}

        try:
            text = response.content[0].text.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            result = json.loads(text[start:end])

            agent = result.get('agent_type', 'unknown')
            reason = result.get('reasoning', 'No reason provided')
            print(f"[Orchestrator] Agente Final seleccionado: {agent.upper()}")
            print(f"[Orchestrator] Razón Pensada por el Modelo: {reason}")

            result.update(usage)
            return result
        except Exception:
            print("[Orchestrator] Falló el parseo JSON del LLM. Procediendo con el Ruteo por Keyword Fallback.")
            pass

        # Fallback por palabras clave si el LLM no retorna JSON válido
        keywords_feedback = ["está mal", "no era eso", "te equivocaste", "incorrecto",
                             "perfecto", "exacto", "eso era", "muy bien", "correcto",
                             "quise decir", "en realidad era", "lo que necesitaba"]
        keywords_data = ["venta", "ventas", "producto", "artículo", "reporte", "turno",
                         "pos", "cantidad", "precio", "franquicia", "ingreso", "ticket"]
        keywords_interaction = ["hola", "gracias", "ayuda", "cómo funciona", "que puedes hacer"]
        msg_lower = user_message.lower()
        if any(k in msg_lower for k in keywords_feedback):
            print("[Orchestrator] Ruteo por Default/Keyword Fallback activado -> FEEDBACK")
            return {"agent_type": "feedback", "reasoning": "keyword fallback", "should_use_memory": True}
        if any(k in msg_lower for k in keywords_data):
            print("[Orchestrator] Ruteo por Default/Keyword Fallback activado -> DATA")
            return {"agent_type": "data", "reasoning": "keyword fallback", "should_use_memory": False, **usage}
        if any(k in msg_lower for k in keywords_interaction):
            print("[Orchestrator] Ruteo por Default/Keyword Fallback activado -> INTERACTION")
            return {"agent_type": "interaction", "reasoning": "keyword fallback", "should_use_memory": False, **usage}

        print("[Orchestrator] Ruteo por Default Fallback activado -> OFF_TOPIC")
        return {"agent_type": "off_topic", "reasoning": "Default fallback", "should_use_memory": False, **usage}

    def get_training_context_for_agent(self, training_mode: bool) -> str:
        """Genera el bloque de contexto de entrenamiento para inyectar en otros agentes."""
        if not training_mode:
            return ""
        tc = training_memory.get_context_for_prompt()
        if not tc:
            return ""
        return f"\n\n=== CONTEXTO DE ENTRENAMIENTO ACTIVO ===\nLas siguientes son sugerencias de mejora basadas en feedback previo de usuarios.\nTené en cuenta estos patrones al generar tu respuesta:\n{tc}"


orchestrator = OrchestratorAgent()
