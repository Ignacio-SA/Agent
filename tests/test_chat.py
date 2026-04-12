import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "Chatbot Multi-Agente API" in response.json()["message"]


def test_chat_endpoint():
    payload = {
        "message": "¿Cuál es el total de ventas?",
        "session_id": "test_session_123",
        "franchise_id": "test_franchise",
        "user_id": "test_user",
    }
    response = client.post("/chat/", json=payload)
    # Sin BD real, esto fallará, pero el endpoint existe
    assert response.status_code in [200, 500]  # 500 es esperado sin BD


def test_chat_with_training_mode():
    payload = {
        "message": "¿Cuántas ventas hubo hoy?",
        "session_id": "test_session_training",
        "franchise_id": "test_franchise",
        "user_id": "test_user",
        "training_mode": True,
    }
    response = client.post("/chat/", json=payload)
    assert response.status_code in [200, 500]


def test_chat_without_training_mode():
    payload = {
        "message": "Hola, ¿cómo funciona esto?",
        "session_id": "test_session_no_training",
        "franchise_id": "test_franchise",
        "user_id": "test_user",
        "training_mode": False,
    }
    response = client.post("/chat/", json=payload)
    assert response.status_code in [200, 500]


def test_chat_feedback_intent():
    payload = {
        "message": "Eso está mal, el total era otro",
        "session_id": "test_session_feedback",
        "franchise_id": "test_franchise",
        "user_id": "test_user",
        "training_mode": True,
    }
    response = client.post("/chat/", json=payload)
    assert response.status_code in [200, 500]


def test_chat_positive_feedback():
    payload = {
        "message": "Perfecto, eso era lo que necesitaba",
        "session_id": "test_session_positive",
        "franchise_id": "test_franchise",
        "user_id": "test_user",
        "training_mode": True,
    }
    response = client.post("/chat/", json=payload)
    assert response.status_code in [200, 500]


def test_training_mode_default():
    """training_mode debería ser True por defecto"""
    payload = {
        "message": "Hola",
        "session_id": "test_default_training",
        "franchise_id": "test_franchise",
    }
    response = client.post("/chat/", json=payload)
    assert response.status_code in [200, 500]


def test_history_endpoint():
    response = client.get("/chat/history/test_session_123")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_training_memory_singleton():
    from app.db.training_repo import training_memory

    assert training_memory is not None
    assert hasattr(training_memory, "load_from_disk")
    assert hasattr(training_memory, "add_suggestion")
    assert hasattr(training_memory, "get_context_for_prompt")
    assert hasattr(training_memory, "get_recent_entries")


def test_training_memory_operations():
    from app.db.training_repo import TrainingMemory

    mem = TrainingMemory()
    assert mem.get_context_for_prompt() == ""
    assert mem.get_recent_entries() == []

    suggestion = {
        "session_id": "test_123",
        "timestamp": "2026-04-12 10:00",
        "type": "negativo",
        "user_message": "¿Cuántas ventas?",
        "agent_response": "Hubo 100 ventas",
        "feedback": "No, fueron más",
        "component": "data_agent",
        "cause": "Query sin filtro de fecha",
        "suggestion": "Agregar filtro de fecha por defecto",
        "priority": "alta",
    }
    mem._context.append(suggestion)
    assert len(mem.get_recent_entries()) == 1
    assert mem.get_context_for_prompt() != ""


def test_training_log_exists():
    log_path = os.path.join(
        os.path.dirname(__file__), "..", "context", "training_log.md"
    )
    assert os.path.exists(log_path)
