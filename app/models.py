from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, Table, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import sqlalchemy


Base = sqlalchemy.orm.declarative_base()


channel_users = Table(
    "channel_users",
    Base.metadata,
    Column("channel_id", ForeignKey("channels.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True)
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)
    role = Column(String, default="user")  # Роли: user, moderator
    is_blocked = Column(Boolean, default=False)
    channels = relationship("Channel", secondary="channel_users", back_populates="users")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

    channel_id = Column(Integer, ForeignKey("channels.id"))
    sender = relationship("User", foreign_keys=[sender_id])
    channel = relationship("Channel", back_populates="messages")


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True)
    invite_token = Column(String, unique=True, index=True)  #ссылка-приглашение
    owner_id = Column(Integer, ForeignKey("users.id"))  # Владелец канала (создатель канала)

    users = relationship("User", secondary="channel_users", back_populates="channels")
    messages = relationship("Message", back_populates="channel")