from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Используем абсолютный путь к БД для избежания проблем с заменой файла
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")
# Для абсолютного пути в SQLite нужно использовать 3 слеша
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    # Отключаем пул соединений для SQLite, чтобы при замене файла использовался новый
    poolclass=None,  # SQLite не использует пул по умолчанию
    echo=False  # Установите True для отладки SQL запросов
)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=True  # Обновляет объекты после коммита
)

Base = declarative_base()
