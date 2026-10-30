import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class CodeIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class RoleIn(BaseModel):
    role: Literal["ADMIN", "USER"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: str
    two_fa_enabled: bool
    created_at: datetime


class PreAuthOut(BaseModel):
    """Resposta do passo 1 do login (password certa, falta o 2º fator)."""

    status: Literal["MFA_REQUIRED", "MFA_SETUP_REQUIRED"]
    pre_auth_token: str
    expires_in: int


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_uri: str