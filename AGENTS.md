# AGENTS.md — Chatbot Multi-Agente

## Overview
FastAPI multi-agent chatbot for franchise sales analysis. Connects to Microsoft Fabric Warehouse and uses Claude (Anthropic) for natural language-to-SQL.

**Python:** 3.12 | **Framework:** FastAPI + Pydantic v2 | **AI:** Anthropic Claude (Sonnet for orchestration, Haiku for agents)

---

## Build, Test, and Run Commands

```bash
# Install dependencies
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Run the application
uvicorn app.main:app --reload

# Run all tests
pytest

# Run a single test
pytest tests/test_chat.py::test_health_check
pytest tests/test_chat.py -k "test_name_here"

# Validate setup
python validate_setup.py
```

---

## Code Style Guidelines

### Imports
- Use **relative imports** within `app` (e.g., `from ..config import settings`)
- Order: standard library → third-party → relative
```python
import os
import json
from datetime import datetime

from fastapi import FastAPI
from anthropic import Anthropic

from ..config import settings
```

### Formatting
- 4-space indentation (no formatter configured)
- Max line length: ~100 chars
- **No comments** unless explaining non-obvious logic

### Type Annotations
- Use type hints on function signatures
- Use Pydantic `BaseModel` for API schemas
- Union syntax: `str | None` (Python 3.10+), not `Optional[str]`

### Naming Conventions
| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `OrchestratorAgent`, `DataAgent` |
| Functions/methods | snake_case | `decide_agent()`, `process_data_request()` |
| Variables | snake_case | `memory_context`, `franchise_code` |
| Constants | UPPER_SNAKE | `MAX_TOKENS`, `DB_AUTH_MODE` |
| Private methods | _prefix | `_load_business_rules()` |
| Module-level singletons | snake_case | `orchestrator`, `data_agent` |

### Error Handling
- Bare `except` only with fallback behavior
- Raise specific exceptions with descriptive messages
- In routers: catch and return `HTTPException(status_code=500, detail=str(e))`

### FastAPI Patterns
- Use `APIRouter` with prefix and tags
- Return Pydantic models as response models
- All endpoints are `async`

### Pydantic v2
- Import from `pydantic` (not `pydantic.v1`)
- Use `pydantic_settings.BaseSettings` for configuration

### Agent Patterns
- Singleton pattern: module-level instance at bottom of file
```python
class DataAgent:
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)

data_agent = DataAgent()
```

### SQLite Patterns
- Use `:memory:` for temporary databases
- Always use **parameterized queries** (never f-string SQL)
- Set `row_factory = sqlite3.Row` for dict-like access

### SQL Conventions
- Quote column names that are keywords: `"Type"`, `"id"`
- Use CASE INSENSITIVE: `LOWER(column) LIKE LOWER('%texto%')`
- Filter promotional headers: `WHERE "Type" != '2'`

### Anthropic API
- Use `client.messages.create()` (not legacy completions)
- Set `temperature=0` for deterministic outputs

### Business Rules
- Stored in `context/business_rules.md`
- Read at runtime (not cached)
```python
_RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "context", "business_rules.md")
```

---

## Project Structure

```
Agent/
├── app/
│   ├── main.py            # FastAPI entry point
│   ├── config.py        # Settings via pydantic_settings
│   ├── agents/        # Agent classes (orchestrator, data_agent, etc.)
│   ├── routers/       # API endpoints
│   ├── db/           # Database connections and repos
│   └── models/       # Pydantic schemas
├── context/
│   └── business_rules.md
├── sql/
│   └── sp_GetSalesForChatbot.sql
├── tests/
│   └── test_chat.py
└── requirements.txt
```

---

## Critical Implementation Notes

### DATETIMEOFFSET Handling
pyodbc returns 20-byte binary. Decode with:
```python
struct.unpack('<hHHHHHIhh', v)  # year, month, day, hour, minute, second, fraction_ns, tz_h, tz_m
```

### Environment Variables
- Load via `python-dotenv` (`load_dotenv()` in `config.py`)
- Validate critical vars at startup

### Authentication Modes (DB_AUTH_MODE)
- `sql` — Username/password
- `activedirectoryinteractive` — Azure AD with MFA
- `activedirectoryintegrated` — Windows integrated auth

---

## Testing Guidelines

- Use `fastapi.testclient.TestClient`
- Mock external services (Anthropic, DB) where possible
- Test endpoint existence with status code checks