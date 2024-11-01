from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from . import crud, database
from passlib.context import CryptContext
from .models import User
from typing import Union


SECRET_KEY = "3fvcGXlqlB2DIjGx"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def authenticate_user(db: Session, username: str, password: str) -> Union[User, bool]:
    user = crud.get_user(db, username)
    if not user or not crud.pwd_context.verify(password, user.password):
        return False
    return user


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str, db: Session = Depends(database.get_db)) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("username")
    except JWTError:
        raise HTTPException(
        status_code=403,
        detail="Токен не действителен",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = crud.get_user(db, username=username)
    if user is None:
        raise HTTPException(
        status_code=403,
        detail="Пользователя не существует",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return user


def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None  