"""
Управление сессиями базы данных
"""

from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import os
import logging

from .models import Base

logger = logging.getLogger(__name__)


class DatabaseSessionManager:
    """Менеджер сессий базы данных"""

    def __init__(self, database_url: str = None):
        if database_url is None:
            # Приоритетно используем переменную окружения APP_DATA_DIR (устанавливается webui.py после упаковки PyInstaller)
            data_dir = os.environ.get('APP_DATA_DIR') or os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'data'
            )
            db_path = os.path.join(data_dir, 'database.db')
            # Убеждаемся, что директория существует
            os.makedirs(data_dir, exist_ok=True)
            database_url = f"sqlite:///{db_path}"

        self.database_url = database_url
        self.engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
            echo=False,  # Установите True для просмотра всех SQL запросов
            pool_pre_ping=True  # Предварительная проверка пула соединений
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_db(self) -> Generator[Session, None, None]:
        """
        Контекстный менеджер для получения сессии базы данных
        Пример использования:
            with get_db() as db:
                # Выполнение операций с базой данных через db
                pass
        """
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        Контекстный менеджер области транзакции
        Пример использования:
            with session_scope() as session:
                # Операции с базой данных
                pass
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def create_tables(self):
        """Создание всех таблиц"""
        Base.metadata.create_all(bind=self.engine)

    def drop_tables(self):
        """Удаление всех таблиц (используйте осторожно)"""
        Base.metadata.drop_all(bind=self.engine)

    def migrate_tables(self):
        """
        Миграция базы данных — добавление отсутствующих столбцов
        Используется для обновления структуры таблиц без удаления данных
        """
        if not self.database_url.startswith("sqlite"):
            logger.info("Не SQLite база данных, пропуск автоматической миграции")
            return

        # Новые столбцы для проверки и добавления
        migrations = [
            # (имя таблицы, имя столбца, тип столбца)
            ("accounts", "cpa_uploaded", "BOOLEAN DEFAULT 0"),
            ("accounts", "cpa_uploaded_at", "DATETIME"),
            ("accounts", "source", "VARCHAR(20) DEFAULT 'register'"),
            ("accounts", "subscription_type", "VARCHAR(20)"),
            ("accounts", "subscription_at", "DATETIME"),
        ]

        with self.engine.connect() as conn:
            for table_name, column_name, column_type in migrations:
                try:
                    # Проверка существования столбца
                    result = conn.execute(text(
                        f"SELECT * FROM pragma_table_info('{table_name}') WHERE name='{column_name}'"
                    ))
                    if result.fetchone() is None:
                        # Столбец не существует, добавляем его
                        logger.info(f"Добавление столбца {table_name}.{column_name}")
                        conn.execute(text(
                            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                        ))
                        conn.commit()
                        logger.info(f"Столбец {table_name}.{column_name} успешно добавлен")
                except Exception as e:
                    logger.warning(f"Ошибка при миграции столбца {table_name}.{column_name}: {e}")


# Глобальный экземпляр менеджера сессий базы данных
_db_manager: DatabaseSessionManager = None


def init_database(database_url: str = None) -> DatabaseSessionManager:
    """
    Инициализация менеджера сессий базы данных
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseSessionManager(database_url)
        _db_manager.create_tables()
        # Выполнение миграции базы данных
        _db_manager.migrate_tables()
    return _db_manager


def get_session_manager() -> DatabaseSessionManager:
    """
    Получение менеджера сессий базы данных
    """
    if _db_manager is None:
        raise RuntimeError("База данных не инициализирована, сначала вызовите init_database()")
    return _db_manager


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Быстрая функция получения сессии базы данных
    """
    manager = get_session_manager()
    db = manager.SessionLocal()
    try:
        yield db
    finally:
        db.close()