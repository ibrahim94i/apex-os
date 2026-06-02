"""Account mode API schemas."""

from typing import Literal

from pydantic import BaseModel


class AccountModeSchema(BaseModel):
    mode: str
    balance: float
    label_ar: str


class AccountModeUpdateSchema(BaseModel):
    mode: Literal["demo", "real"]
