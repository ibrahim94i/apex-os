"""Trading journal and position manager API."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.journal import (
    JournalAnalysisSchema,
    JournalEntryCreateSchema,
    JournalEntrySchema,
    PositionManagerSchema,
)
from app.services.position_manager_service import position_manager_service
from app.services.trading_journal_service import trading_journal_service

journal_router = APIRouter()


@journal_router.get("/journal/entries", response_model=list[JournalEntrySchema])
async def list_journal_entries(
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
) -> list[JournalEntrySchema]:
    return await trading_journal_service.list_entries(session, limit)


@journal_router.post("/journal/entries", response_model=dict)
async def create_journal_entry(
    data: JournalEntryCreateSchema,
    session: AsyncSession = Depends(get_db),
) -> dict:
    entry, analysis = await trading_journal_service.create_entry(session, data)
    return {"entry": entry.model_dump(mode="json"), "analysis": analysis.model_dump(mode="json") if analysis else None}


@journal_router.get("/journal/analysis", response_model=JournalAnalysisSchema | None)
async def get_journal_analysis(
    session: AsyncSession = Depends(get_db),
) -> JournalAnalysisSchema | None:
    return await trading_journal_service.get_latest_analysis(session)


@journal_router.get("/position-manager/status", response_model=PositionManagerSchema)
async def get_position_manager_status(
    symbol: str = "XAUUSD",
    session: AsyncSession = Depends(get_db),
) -> PositionManagerSchema:
    return await position_manager_service.get_status(session, symbol)
