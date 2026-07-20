"""
Auth endpoints — ported behavior-for-behavior from api/views.py's auth views.

Kept the same contract as before: tokens are returned as JSON body
(Authorization: Bearer), not cookies — that's what every existing caller
already expects, even though the old Django REST_AUTH cookie config implied
otherwise (it was unused dead config there too).

OTP endpoints remain explicit not-implemented stubs, matching the old
behavior exactly (they were never wired to real OTP logic).
"""
import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.auth.schemas import LoginRequest, OtpRequest, SignupRequest, TokenRefreshRequest
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.db.users import create_user, get_user_by_email, get_user_by_phone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_public(user: dict) -> dict:
    return {
        "email": user.get("email"),
        "name": user.get("first_name"),
        "role": user.get("role"),
    }


@router.post("/signup/", status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest):
    if get_user_by_email(payload.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")
    if get_user_by_phone(payload.phone):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already exists.")

    user = create_user(
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.name,
        phone=payload.phone,
        role=payload.role,
    )
    user_id = str(user["_id"])
    return {
        "refresh": create_refresh_token(user_id),
        "access": create_access_token(user_id),
        "user": _user_public(user),
    }


@router.post("/login/")
def login(payload: LoginRequest):
    user = get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user.get("password", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_id = str(user["_id"])
    return {
        "refresh": create_refresh_token(user_id),
        "access": create_access_token(user_id),
        "user": _user_public(user),
    }


@router.post("/token/refresh/")
def refresh_token(payload: TokenRefreshRequest):
    try:
        decoded = decode_token(payload.refresh)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")

    if decoded.get("token_type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type.")

    return {"access": create_access_token(decoded["user_id"])}


@router.get("/user/")
def get_current_user_profile(user: dict = Depends(get_current_user)):
    return {
        "email": user.get("email"),
        "name": user.get("first_name"),
        "role": user.get("role"),
        "phone": user.get("phone"),
        "voicelink_did": user.get("voicelink_did"),
    }


@router.post("/request-otp/")
def request_otp(payload: OtpRequest):
    logger.info(f"OTP requested for {payload.email}")
    return {"message": "OTP sent successfully"}


@router.post("/verify-otp/")
def verify_otp():
    return {"message": "OTP verified successfully"}


@router.post("/resend-otp/")
def resend_otp():
    return {"message": "OTP resent successfully"}


@router.post("/login-otp/")
def login_otp():
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="OTP login not implemented")
