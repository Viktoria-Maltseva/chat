from faker import Faker
import random
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import sqlalchemy.orm 
from app.models import *
from sqlalchemy.exc import OperationalError
from app.auth import hash_password


fake = Faker()


Base = sqlalchemy.orm.declarative_base()
SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://cloud_user:&S8KuD3Gy3Gt@nasasupi.beget.app/test_chat"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def generate_users(num_users):
    users = []
    for _ in range(2):
        password = fake.password()
        user = {
            "username": fake.user_name(),
            "password": password,
            "hashed_password": hash_password(password),
            "role": "user",
            "is_blocked": False
        }
        users.append(user)
    password = fake.password()
    user = {
        "username": fake.user_name(),
        "password": password,
        "hashed_password": hash_password(password),
        "role": "moderator",
        "is_blocked": False
    }
    users.append(user)
    for _ in range(num_users - 3):
        password = fake.password()
        user = {
            "username": fake.user_name(),
            "password": password,
            "hashed_password": hash_password(password),
            "role": random.choice(["user", "moderator"]),
            "is_blocked": random.choice([True, False])
        }
        users.append(user)
    return users


def generate_channels(num_channels, users):
    channels = []
    for _ in range(num_channels):
        owner = random.choice(users)
        participants = random.sample(users, k=random.randint(1, len(users)))
        if owner not in participants:
            participants[0] = owner

        channel = {
            "name": fake.word() + "_channel",
            "invite_token": fake.uuid4(),
            "owner_id": owner["username"],
            "users": participants
        }
        channels.append(channel)
    return channels


def generate_messages(num_messages, users, channels):
    messages = []
    for _ in range(num_messages):
        message = {
            "content": fake.text(max_nb_chars=200),
            "sender_id": random.choice(users)["username"],
            "timestamp": fake.date_time_this_year(),
            "channel_id": random.choice(channels)["name"]
        }
        messages.append(message)
    return messages


def save_to_db(users, channels, messages, db: Session):
    db_users = [User(username=user["username"], password=user["hashed_password"], role=user["role"], is_blocked=user["is_blocked"]) for user in users]
    db.add_all(db_users)
    db.commit()  # Коммит нужен для получения id пользователей
    for db_user, user in zip(db_users, users):
        insert_query = text("""
        INSERT INTO user_password_unhashed (user_id, unhashed_password)
        VALUES (:user_id, :hashed_password)
        """)
        db.execute(insert_query, {"user_id": db_user.id, "hashed_password": user["password"]})
    db.commit()
    user_ids = {user.username: db.query(User).filter_by(username=user.username).first().id for user in db_users}
    for channel in channels:
        owner_id = user_ids[channel["owner_id"]]  # Получаем id владельца
        db_channel = Channel(
            name=channel["name"],
            invite_token=channel["invite_token"],
            owner_id=owner_id
        )
        db.add(db_channel)
        db.commit()  # Коммитим, чтобы канал получил id

        # Добавляем участников в канал
        for participant in channel["users"]:
            db.execute(channel_users.insert().values(channel_id=db_channel.id, user_id=user_ids[participant["username"]]))
    db.commit()
    # Сохраняем сообщения
    for msg in messages:
        db_message = Message(
            content=msg["content"],
            sender_id=user_ids[msg["sender_id"]],
            timestamp=msg["timestamp"],
            channel_id=db.query(Channel).filter_by(name=msg["channel_id"]).first().id
        )
        db.add(db_message)
    db.commit()


def clear_tables(db):
    db.execute(text("DELETE FROM channel_users"))
    db.execute(text("DELETE FROM messages"))
    db.execute(text("DELETE FROM channels"))
    db.execute(text("DELETE FROM users"))
    db.commit()


def create_tables_if_not_exists(engine, db: Session) -> None:
    try:
        # Создание всех таблиц, если они еще не существуют
        Base.metadata.create_all(bind=engine)
        create_table_query = text("""
        CREATE TABLE IF NOT EXISTS user_password_unhashed (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            unhashed_password VARCHAR NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)
        db.execute(create_table_query)
        db.commit()
    except OperationalError as e:
        print(f"Ошибка при создании таблиц: {e}")


def generate_new_data(db: Session):
    num_users = 10
    num_channels = 4
    num_messages = 50
    users = generate_users(num_users)
    channels = generate_channels(num_channels, users)
    messages = generate_messages(num_messages, users, channels)
    create_tables_if_not_exists(engine, db)
    # db.execute(text("ALTER SEQUENCE users_id_seq RESTART WITH 1"))
    # db.execute(text("ALTER SEQUENCE channels_id_seq RESTART WITH 1"))
    # db.execute(text("ALTER SEQUENCE messages_id_seq RESTART WITH 1"))
    save_to_db(users, channels, messages, db)