from .test_generate_data import generate_new_data, clear_tables
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, text
from app.main import app
from app.database import get_db
from faker import Faker
from app.models import *
from app.crud import generate_invite_token


# Создаем тестовую базу данных
SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://cloud_user:&S8KuD3Gy3Gt@nasasupi.beget.app/test_chat"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
fake = Faker()


@pytest.fixture(scope="function")
def db_session():
    db = TestingSessionLocal()
    clear_tables(db)
    generate_new_data(db)
    yield db
    db.close()

@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)


# Тест регистрации пользователя
def test_register(client):
    response = client.post("/register", json={"username": "testuser", "password": "testpass"})
    assert response.status_code == 200
    assert response.json() == {"message": "Пользователь успешно зарегистрирован"}
    response1 = client.post("/register", json={"username": "te", "password": ""})
    assert response1.status_code == 422
    response_data = response1.json().get("detail", [])
    assert "Никнейм должен содержать не менее 4 символов." in response_data
    assert "Пароль должен содержать не менее 5 символов." in response_data


# Тест аутентификации
def test_login(client):
    client.post("/register", json={"username": "testuser", "password": "testpass"})
    response = client.post("/login", json={"username": "testuser", "password": "testpass"})
    assert response.status_code == 200
    assert "access_token" in response.json()
    response = client.post("/login", json={"username": "testuser", "password": "wrong_password"})
    assert response.status_code == 400
    assert response.json() == {
        "detail": "Неправильный пароль/логин или пользователь не зарегистрирован."
    }


# Тест создания канала
def test_create_channel(client, db_session):
    client.post("/register", json={"username": "testuser", "password": "testpass"})
    response = client.post("/login", json={"username": "testuser", "password": "testpass"})
    token = response.json()["access_token"]

    response = client.post("/channels/create", headers={"token": token}, json={"channel_name": "test_channel"})
    assert response.status_code == 200
    assert "channel_invite" in response.json()
    channel_invite = response.json()["channel_invite"]
    assert response.json() == {
    "message": "Канал успешно создан",
    "channel_name": "test_channel",
    "channel_invite": channel_invite
    }

    response = client.post("/channels/create", headers={"token": token}, json={"channel_name": "test_channel"})
    assert response.json() == {
    "detail": "Канал с таким именем уже существует."
    }

    fake_token = generate_invite_token()
    response = client.post("/channels/create", headers={"token": fake_token}, json={"channel_name": "test_channel"})
    assert response.json() == {
    "detail": "Не авторизован."
    }

    blocked_user = db_session.query(User).filter(User.is_blocked == True).first()
    unhashed_password = db_session.execute(
        text("SELECT unhashed_password FROM user_password_unhashed WHERE user_id = :user_id"),
        {"user_id": blocked_user.id}
    ).fetchone()[0]
    response = client.post("/login", json={"username": blocked_user.username, "password": unhashed_password})
    token = response.json()["access_token"]
    response = client.post("/channels/create", headers={"token": token}, json={"channel_name": "test_channel_2"})
    assert response.json() == {
    "detail": "Пользователь заблокирован."
    }


#Тест присоединения к каналу
def test_join_channel(client):
    client.post("/register", json={"username": "testuser", "password": "testpass"})
    client.post("/register", json={"username": "anotheruser", "password": "testpass"})

    # Создаем канал
    response = client.post("/login", json={"username": "testuser", "password": "testpass"})
    token = response.json()["access_token"]
    response = client.post("/channels/create", headers={"token": token}, json={"channel_name": "test_channel"})
    invite_token = response.json()["channel_invite"]

    # авторизуем второго пользователя
    response = client.post("/login", json={"username": "anotheruser", "password": "testpass"})
    token = response.json()["access_token"]

    # Присоединяемся к каналу
    response = client.post("/join/", headers={"invite-token": invite_token, "user-token": token})
    assert response.status_code == 200
    assert response.json()["message"] == "Вы успешно присоединились к каналу"


# Тест блокировки пользователя
def test_block_user(client, db_session):
    moderator = db_session.query(User).filter(User.role == "moderator", User.is_blocked == False).first()
    unhashed_password_moderator = db_session.execute(
        text("SELECT unhashed_password FROM user_password_unhashed WHERE user_id = :user_id"),
        {"user_id": moderator.id}
    ).fetchone()[0]
    user = db_session.query(User).filter(User.role == "user", User.is_blocked == False).first()
    unhashed_password_user = db_session.execute(
        text("SELECT unhashed_password FROM user_password_unhashed WHERE user_id = :user_id"),
        {"user_id": user.id}
    ).fetchone()[0]
    user_2 = db_session.query(User).filter(User.role == "user", User.id != user.id).first()

    # Нет прав на блокировку(не модератор)
    response = client.post("/login", json={"username": user.username, "password": unhashed_password_user})
    token = response.json()["access_token"]
    response = client.post("/users/block", headers={"token": token}, params={"user_name": user_2.username})
    assert response.status_code == 403
    assert response.json()["detail"] == "Недостаточно прав для блокировки пользователя"

    # Вход под модератором
    response = client.post("/login", json={"username": moderator.username, "password": unhashed_password_moderator})
    token = response.json()["access_token"]

    # Блокировка пользователя
    response = client.post("/users/block", headers={"token": token}, params={"user_name": user.username})
    assert response.status_code == 200
    assert response.json()["message"] == f'Пользователь {user.username} успешно заблокирован'

    # Блокировка пользователя повторно
    response = client.post("/users/block", headers={"token": token}, params={"user_name": user.username})
    assert response.status_code == 400
    assert response.json()["detail"] == "Пользователь уже заблокирован"

    # Блокировка несуществующего пользователя
    username = "Не существующий пользователь."
    response = client.post("/users/block", headers={"token": token}, params={"user_name": username})
    assert response.status_code == 404
    assert response.json()["detail"] == "Пользователь не найден"