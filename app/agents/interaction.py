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
        system_prompt = """Eres un asistente de ventas para franquiciados. Responde SOLO preguntas sobre:
- Saludos y conversación básica relacionada con el negocio
- Dudas sobre cómo usar este asistente

Si el mensaje NO está relacionado con ventas, el negocio de la franquicia o el uso de este chatbot, responde ÚNICAMENTE: "Solo puedo ayudarte con consultas de ventas o datos del negocio. Consultá con el administrador para otros temas."

No expliques por qué. No ofrezcas alternativas. No traduzcas ni resuelvas tareas externas."""

        if memory_context:
            system_prompt += f"\n\nContexto: {memory_context}"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        return response.content[0].text


interaction_agent = InteractionAgent()
