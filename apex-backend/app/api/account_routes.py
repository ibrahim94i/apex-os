"""Account mode — Demo / Real switching and balance management."""

from fastapi import APIRouter, HTTPException

from app.schemas.account import (
    AccountBalanceUpdateSchema,
    AccountModeSchema,
    AccountModeUpdateSchema,
)
from app.services.account_service import account_service

account_router = APIRouter()


@account_router.get("/account/mode", response_model=AccountModeSchema)
async def get_account_mode() -> AccountModeSchema:
    status = await account_service.get_status()
    return AccountModeSchema(**status)


@account_router.patch("/account/mode", response_model=AccountModeSchema)
async def set_account_mode(body: AccountModeUpdateSchema) -> AccountModeSchema:
    status = await account_service.set_mode(body.mode, body.balance)
    return AccountModeSchema(**status)


@account_router.patch("/account/balance", response_model=AccountModeSchema)
async def set_account_balance(body: AccountBalanceUpdateSchema) -> AccountModeSchema:
    mode = await account_service.get_mode()
    if mode != "real":
        raise HTTPException(status_code=400, detail="Balance editable only in real account mode")
    status = await account_service.set_real_balance(body.balance)
    return AccountModeSchema(**status)
