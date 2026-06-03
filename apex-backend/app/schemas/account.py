"""Account mode API schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class AccountModeSchema(BaseModel):
    mode: str
    balance: float
    label_ar: str
    balance_editable: bool = False


class AccountModeUpdateSchema(BaseModel):
    mode: Literal["demo", "real"]
    balance: float | None = Field(default=None, gt=0)


class AccountBalanceUpdateSchema(BaseModel):
    balance: float = Field(gt=0)
