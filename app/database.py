from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .models import Base
from sqlalchemy.exc import OperationalError


SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://cloud_user:&S8KuD3Gy3Gt@nasasupi.beget.app/chat_db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables_if_not_exists(engine) -> None:
    try:
        # Создание всех таблиц, если они еще не существуют
        Base.metadata.create_all(bind=engine)
        print("Таблицы созданы успешно")
    except OperationalError as e:
        print(f"Ошибка при создании таблиц: {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
