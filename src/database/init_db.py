"""
Инициализация базы данных и начальных данных
"""

from .session import init_database
from .models import Base


def initialize_database(database_url: str = None):
    """
    Инициализация базы данных
    Создание всех таблиц и установка конфигурации по умолчанию
    """
    # Инициализация подключения к базе данных и таблиц
    db_manager = init_database(database_url)

    # Создание таблиц
    db_manager.create_tables()

    # Инициализация настроек по умолчанию (импорт из модуля settings для избежания циклического импорта)
    from ..config.settings import init_default_settings
    init_default_settings()

    return db_manager


def reset_database(database_url: str = None):
    """
    Сброс базы данных (удаление всех таблиц и повторное создание)
    Предупреждение: все данные будут потеряны!
    """
    db_manager = init_database(database_url)

    # Удаление всех таблиц
    db_manager.drop_tables()
    print("Все таблицы удалены")

    # Повторное создание всех таблиц
    db_manager.create_tables()
    print("Все таблицы созданы заново")

    # Инициализация настроек по умолчанию
    from ..config.settings import init_default_settings
    init_default_settings()

    print("Сброс базы данных завершён")
    return db_manager


def check_database_connection(database_url: str = None) -> bool:
    """
    Проверка работоспособности подключения к базе данных
    """
    try:
        db_manager = init_database(database_url)
        with db_manager.get_db() as db:
            # Попытка выполнить простой запрос
            db.execute("SELECT 1")
        print("Подключение к базе данных в норме")
        return True
    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
        return False


if __name__ == "__main__":
    # При прямом запуске этого скрипта — инициализация базы данных
    import argparse

    parser = argparse.ArgumentParser(description="Скрипт инициализации базы данных")
    parser.add_argument("--reset", action="store_true", help="Сброс базы данных (удаление всех данных)")
    parser.add_argument("--check", action="store_true", help="Проверка подключения к базе данных")
    parser.add_argument("--url", help="Строка подключения к базе данных")

    args = parser.parse_args()

    if args.check:
        check_database_connection(args.url)
    elif args.reset:
        confirm = input("Предупреждение: все данные будут удалены! Подтвердить сброс? (y/N): ")
        if confirm.lower() == 'y':
            reset_database(args.url)
        else:
            print("Операция отменена")
    else:
        initialize_database(args.url)
