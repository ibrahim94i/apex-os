"""Account mode — Demo / Real switching."""

from fastapi import APIRouter

from app.schemas.account import AccountModeSchema, AccountModeUpdateSchema
from app.services.account_service import account_service

account_router = APIRouter()


@account_router.get("/account/mode", response_model=AccountModeSchema)
async def get_account_mode() -> AccountModeSchema:
    status = await account_service.get_status()
    return AccountModeSchema(**status)


@account_router.patch("/account/mode", response_model=AccountModeSchema)
async def set_account_mode(body: AccountModeUpdateSchema) -> AccountModeSchema:
    status = await account_service.set_mode(body.mode)
    return AccountModeSchema(**status)
