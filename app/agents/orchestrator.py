import json

from anthropic import Anthropic

from ..config import settings


class OrchestratorAgent:
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-6"

    def decide_agent(self, user_message: str, memory_context: str = "") -> dict:
        """
        Claude Sonnet decide cuál sub-agente activar
        Retorna: {agent_type, reasoning, params}
        """
        system_prompt = """Eres un orquestador de agentes. Analiza el mensaje del usuario
y decide qué agente debe responder:

1. "data" - Si el mensaje menciona ventas, productos, artículos, reportes, cantidades, precios, turnos, POS, franquicia, o cualquier dato de negocio. PRIORIDAD ALTA.
2. "interaction" - Solo para conversación puramente general sin ninguna mención de datos o ventas.
3. "memory" - Solo si el usuario pide explícitamente recordar algo de conversaciones anteriores.

IMPORTANTE: Si el mensaje mezcla saludo con consulta de ventas, usar "data".

Responde SIEMPRE en JSON con: {"agent_type": "", "reasoning": "", "should_use_memory": bool}"""

        context = f"Contexto de memoria: {memory_context}" if memory_context else ""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": f"{context}\nMensaje del usuario: {user_message}\n\nResponde SOLO con el JSON, sin texto adicional."}],
        )

        try:
            text = response.content[0].text.strip()
            # Extraer JSON aunque venga con texto extra
            start = text.find("{")
            end = text.rfind("}") + 1
            result = json.loads(text[start:end])
            return result
        except:
            pass

        # Fallback por palabras clave si el LLM no retorna JSON válido
        keywords_data = ["venta", "ventas", "producto", "artículo", "reporte", "turno",
                         "pos", "cantidad", "precio", "franquicia", "ingreso", "ticket"]
        msg_lower = user_message.lower()
        if any(k in msg_lower for k in keywords_data):
            return {"agent_type": "data", "reasoning": "keyword fallback", "should_use_memory": False}

        return {"agent_type": "interaction", "reasoning": "Default fallback", "should_use_memory": False}


orchestrator = OrchestratorAgent()
