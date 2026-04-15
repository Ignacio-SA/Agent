import random
import traceback
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..agents.data_agent import data_agent
from ..agents.interaction import interaction_agent
from ..agents.memory_agent import memory_agent
from ..agents.orchestrator import orchestrator
from ..agents.training_agent import training_agent
from ..models.schemas import ChatRequest, ChatResponse, HistoryEntry

router = APIRouter(prefix="/chat", tags=["chat"])

FEEDBACK_PROMPTS = [
    "\n\n---\n💬 *¿Esta respuesta fue útil? Podés decirme si hay algo para mejorar.*",
    "\n\n---\n📝 *¿La información fue correcta y completa? Tu feedback me ayuda a mejorar.*",
    "\n\n---\n✅ *¿Esto era lo que necesitabas? Cualquier corrección es bienvenida.*",
]

FEEDBACK_THANKS = [
    "¡Gracias por el feedback! Tomé nota para mejorar mis respuestas. ¿Hay algo más en lo que pueda ayudarte?",
    "¡Anotado! Tu feedback me ayuda a ser más preciso. ¿Necesitás algo más?",
    "¡Gracias por la devolución! Lo tengo en cuenta. ¿En qué más puedo ayudarte?",
]


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    POST /chat - Procesa un mensaje del usuario
    Usa el orquestador para decidir qué agente responde
    """
    try:
        print(f"\n[{'='*40}]")
        print(f"[Router Global] Nueva petición recibida (Session ID: {request.session_id})")
        print(f"[{'-'*40}]")

        # Obtener memoria previa
        memory = memory_agent.retrieve_memory(request.session_id)
        memory_context = memory.get("summary", "") if memory else ""
        if memory_context:
            print(f"[MemoryAgent] Historial previo contextual rescatado y adjuntado: '{memory_context}'")
        else:
            print("[MemoryAgent] Sin historial previo. Sesión limpia.")

        # Orquestador decide qué agente (con training_mode)
        decision = orchestrator.decide_agent(
            request.message, memory_context, request.training_mode
        )
        agent_type = decision.get("agent_type", "interaction")

        # Contexto de entrenamiento para inyectar en agentes
        training_ctx = orchestrator.get_training_context_for_agent(request.training_mode)

        # Invocar agente correspondiente
        if agent_type == "feedback":
            response_text = await _handle_feedback(request)
        elif agent_type == "data":
            enriched_context = memory_context + training_ctx
            response_text = data_agent.process_data_request(
                request.message, request.franchise_id, enriched_context
            )
        elif agent_type == "memory":
            response_text = f"Recordando: {memory_context}"
        elif agent_type == "off_topic":
            response_text = "Solo puedo ayudarte con consultas de ventas o datos del negocio. Consultá con el administrador para otros temas."
        else:  # interaction
            enriched_context = memory_context + training_ctx
            response_text = interaction_agent.respond(request.message, enriched_context)

        # Agregar solicitud de feedback si training_mode y no es feedback
        if request.training_mode and agent_type != "feedback":
            response_text += random.choice(FEEDBACK_PROMPTS)

        # Guardar mensajes individuales
        from ..db.memory_repo import memory_repo as repo
        repo.save_message(request.session_id, "user", request.message)
        repo.save_message(request.session_id, "assistant", response_text, agent_type)

        # Guardar memoria/resumen
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


async def _handle_feedback(request: ChatRequest) -> str:
    """Procesa feedback: extrae historial, llama al training_agent, responde."""
    try:
        from ..db.memory_repo import memory_repo as repo
        messages = repo.get_messages(request.session_id)

        print("\n[Feedback Global] --- INICIO FLUJO DE RECOLECCIÓN DE FEEDBACK ---")
        print(f"[Feedback Global] Mensaje recibido del usuario interpretado como feedback: '{request.message}'")
        
        history = []
        for msg in messages[-10:]:
            history.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
                "agent_type": msg.get("agent_type", ""),
            })
            
        print(f"[Feedback Global] Reconstruyendo el contexto... se enviarán {len(history)} mensajes del historial reciente al agente.")

        training_agent.process_feedback(
            session_id=request.session_id,
            history=history,
            feedback_message=request.message,
        )
        print("[Feedback Global] --- FIN FLUJO DE RECOLECCIÓN DE FEEDBACK ---\n")
    except Exception as e:
        print(f"[Training] Error procesando feedback: {e}")
        traceback.print_exc()

    return random.choice(FEEDBACK_THANKS)


@router.get("/sessions/")
async def list_sessions():
    """GET /chat/sessions/ - Lista todas las sesiones guardadas"""
    try:
        from ..db.memory_repo import memory_repo as repo
        return repo.list_all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """GET /chat/sessions/{session_id}/messages - Historial completo de mensajes"""
    try:
        from ..db.memory_repo import memory_repo as repo
        return repo.get_messages(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """DELETE /chat/sessions/{session_id} - Elimina una sesión y sus mensajes"""
    try:
        from ..db.memory_repo import memory_repo as repo
        deleted = repo.delete(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
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
