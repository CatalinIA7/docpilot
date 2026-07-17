import os
from datetime import datetime, timedelta, timezone
from typing import Any

from argon2 import PasswordHasher
from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import SessionLocal
from models import User
from schemas import UserRegister


SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

ph = PasswordHasher(time_cost=3, memory_cost=65536, hash_len=32, parallelism=4, salt_len=16)


def get_db_session() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return ph.verify(hashed_password, plain_password)


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def get_current_user_from_token(db: Session, token: str) -> User | None:
    try:
        payload = decode_access_token(token)
        email = payload.get("sub")
    except JWTError:
        return None

    if not email:
        return None

    return get_user_by_email(db, email)


def get_current_user_dependency(authorization: str | None = None, db: Session | None = None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = authorization.removeprefix("Bearer ").strip()
    if db is None:
        db = SessionLocal()

    user = get_current_user_from_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    return user


def create_user(db: Session, payload: UserRegister) -> User:
    user = User(email=str(payload.email), password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()
