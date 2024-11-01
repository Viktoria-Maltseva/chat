from sqlalchemy.orm import Session
import app.models as models, app.schemas as schemas
from passlib.context import CryptContext
from .models import User, channel_users
from typing import Optional
import secrets


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_user(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def create_user(db: Session, user: schemas.UserCreate, hashed_password) -> User:
    db_user = models.User(username=user, password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def add_user_to_channel(db: Session, user_id: int, channel_id: int):
    db.execute(channel_users.insert().values(user_id=user_id, channel_id=channel_id))
    db.commit()


def get_channel_by_invite_token(db: Session, invite_token: str):
    return db.query(models.Channel).filter(models.Channel.invite_token == invite_token).first()


def generate_invite_token() -> str:
    return secrets.token_urlsafe(16)


def is_user_in_channel(db: Session, user_id: int, channel_id: int) -> bool:
    return db.query(models.Channel).filter(
        models.Channel.id == channel_id,
        models.Channel.users.any(id=user_id)  # Проверка наличия пользователя
    ).first() is not None