from anthropic import Anthropic

from ..config import settings


class InteractionAgent:
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-haiku-4-5-20251001"

    def respond(self, user_message: str, memory_context: str = "") -> str:
        """
        Claude Haiku responde conversacionalmente
        """
        system_prompt = """Eres un asistente de ventas para franquiciados.
IMPORTANTE: No inventes información. Solo puedes responder sobre:
- Consultas de ventas y datos del negocio (para eso usa el agente de datos)
- Preguntas generales de conversación

Si el usuario pregunta sobre modelos de negocio, inversiones, requisitos u otro tema que no conoces, dile que no tienes esa información disponible y sugiérele que consulte con el administrador de la franquicia."""

        if memory_context:
            system_prompt += f"\n\nContexto de sesión anterior: {memory_context}"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        return response.content[0].text


interaction_agent = InteractionAgent()
