"""Smart Advisor (المستشار الذكي) API routes."""

from fastapi import APIRouter, HTTPException

from app.schemas.advisor import AdvisorChatRequest, AdvisorChatResponse, AdvisorContextResponse
from app.services.advisor_service import advisor_chat, get_advisor_context
from app.utils.llm_client import LLMCircuitOpenError, LLMClientError

advisor_router = APIRouter(tags=["advisor"])


@advisor_router.get("/advisor/context", response_model=AdvisorContextResponse)
async def advisor_context() -> AdvisorContextResponse:
    """Current APEX internal data snapshot for all active assets."""
    return await get_advisor_context()


@advisor_router.post("/advisor/chat", response_model=AdvisorChatResponse)
async def advisor_chat_endpoint(body: AdvisorChatRequest) -> AdvisorChatResponse:
    """Ask the Smart Advisor — GPT-4o-mini with web search, Arabic in/out."""
    try:
        history = [{"role": m.role, "content": m.content} for m in body.history]
        return await advisor_chat(
            body.message.strip(),
            symbol=body.symbol,
            history=history,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMCircuitOpenError as exc:
        raise HTTPException(status_code=503, detail="المستشار غير متاح مؤقتاً — حاول لاحقاً") from exc
    except LLMClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"خطأ في المستشار: {exc}") from exc
