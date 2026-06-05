"""Advisor API route tests."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.advisor import AdvisorChatResponse
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_advisor_chat_endpoint() -> None:
    mock_response = AdvisorChatResponse(
        reply="توصية: شراء — الدخول 4400 — SL 4380 — TP 4450 — مخاطرة متوسطة — ثقة 72%",
        symbol="XAUUSD",
        model="gpt-4o-mini",
        latency_ms=1500.0,
        web_search_used=False,
        apex_context=[],
        timestamp=datetime.now(timezone.utc),
    )
    with patch(
        "app.api.advisor_routes.advisor_chat",
        new=AsyncMock(return_value=mock_response),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/advisor/chat",
                json={"message": "ما توصيتك للذهب؟", "symbol": "XAUUSD", "history": []},
            )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "4400" in data["reply"] or "توصية" in data["reply"]
