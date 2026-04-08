import traceback
from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..agents.data_agent import data_agent
from ..agents.interaction import interaction_agent
from ..agents.memory_agent import memory_agent
from ..agents.orchestrator import orchestrator
from ..models.schemas import ChatRequest, ChatResponse, HistoryEntry

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    POST /chat - Procesa un mensaje del usuario
    Usa el orquestador para decidir qué agente responde
    """
    try:
        # Obtener memoria previa
        memory = memory_agent.retrieve_memory(request.session_id)
        memory_context = memory.get("summary", "") if memory else ""

        # Orquestador decide qué agente
        decision = orchestrator.decide_agent(request.message, memory_context)
        agent_type = decision.get("agent_type", "interaction")

        # Invocar agente correspondiente
        if agent_type == "data":
            response_text = data_agent.process_data_request(request.message, request.franchise_id, memory_context)
        elif agent_type == "memory":
            response_text = f"Recordando: {memory_context}"
        else:  # interaction
            response_text = interaction_agent.respond(request.message, memory_context)

        # Guardar memoria con la conversación actual
        conversation = [
            {"role": "user", "content": request.message},
            {"role": "assistant", "content": response_text},
        ]
        user_id = request.user_id or request.franchise_id
        memory_agent.save_memory(request.session_id, user_id, conversation)

        return ChatResponse(
            session_id=request.session_id,
            response=response_text,
            agent_type=agent_type,
            timestamp=datetime.now(),
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{session_id}", response_model=list[HistoryEntry])
async def get_history(session_id: str):
    """
    GET /chat/history/{session_id} - Obtiene historial de sesión
    """
    try:
        memory = memory_agent.retrieve_memory(session_id)
        if not memory:
            return []

        return [
            HistoryEntry(
                session_id=session_id,
                user_message="[Previous conversation]",
                bot_response=memory.get("summary", ""),
                agent_type="memory",
                timestamp=memory.get("updated_at", datetime.now()),
            )
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
