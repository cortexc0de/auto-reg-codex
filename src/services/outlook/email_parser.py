"""
Разбор писем и извлечение кодов подтверждения
"""

import logging
import re
from typing import Optional, List, Dict, Any

from ...config.constants import (
    OTP_CODE_SIMPLE_PATTERN,
    OTP_CODE_SEMANTIC_PATTERN,
    OPENAI_EMAIL_SENDERS,
    OPENAI_VERIFICATION_KEYWORDS,
)
from .base import EmailMessage


logger = logging.getLogger(__name__)


class EmailParser:
    """
    Парсер писем
    Для идентификации верификационных писем OpenAI и извлечения кодов подтверждения
    """

    def __init__(self):
        # Компиляция регулярных выражений
        self._simple_pattern = re.compile(OTP_CODE_SIMPLE_PATTERN)
        self._semantic_pattern = re.compile(OTP_CODE_SEMANTIC_PATTERN, re.IGNORECASE)

    def is_openai_verification_email(
        self,
        email: EmailMessage,
        target_email: Optional[str] = None,
    ) -> bool:
        """
        Определить, является ли письмо верификационным от OpenAI

        Args:
            email: Объект письма
            target_email: Целевой почтовый адрес (для проверки получателя)

        Returns:
            Является ли письмо верификационным от OpenAI
        """
        sender = email.sender.lower()

        # 1. Отправитель должен быть OpenAI
        if not any(s in sender for s in OPENAI_EMAIL_SENDERS):
            logger.debug(f"Отправитель письма не OpenAI: {sender}")
            return False

        # 2. Тема или тело содержат ключевые слова верификации
        subject = email.subject.lower()
        body = email.body.lower()
        combined = f"{subject} {body}"

        if not any(kw in combined for kw in OPENAI_VERIFICATION_KEYWORDS):
            logger.debug(f"Письмо не содержит ключевых слов верификации: {subject[:50]}")
            return False

        # 3. Проверка получателя удалена: в IMAP-заголовках писем с псевдонимов получатель может не совпадать, определяем только по отправителю + ключевым словам
        logger.debug(f"Определено как верификационное письмо OpenAI: {subject[:50]}")
        return True

    def extract_verification_code(
        self,
        email: EmailMessage,
    ) -> Optional[str]:
        """
        Извлечь код подтверждения из письма

        Приоритет:
        1. Извлечение из темы (6-значное число)
        2. Извлечение из тела с семантическим regex (например, "code is 123456")
        3. Запасной вариант: любое 6-значное число

        Args:
            email: Объект письма

        Returns:
            Строка с кодом подтверждения, None если не найден
        """
        # 1. Приоритет темы
        code = self._extract_from_subject(email.subject)
        if code:
            logger.debug(f"Код подтверждения извлечён из темы: {code}")
            return code

        # 2. Семантическое совпадение в теле
        code = self._extract_semantic(email.body)
        if code:
            logger.debug(f"Код подтверждения извлечён семантически из тела: {code}")
            return code

        # 3. Запасной вариант: любое 6-значное число в теле
        code = self._extract_simple(email.body)
        if code:
            logger.debug(f"Код подтверждения извлечён запасным методом из тела: {code}")
            return code

        return None

    def _extract_from_subject(self, subject: str) -> Optional[str]:
        """Извлечь код подтверждения из темы"""
        match = self._simple_pattern.search(subject)
        if match:
            return match.group(1)
        return None

    def _extract_semantic(self, body: str) -> Optional[str]:
        """Семантическое извлечение кода подтверждения"""
        match = self._semantic_pattern.search(body)
        if match:
            return match.group(1)
        return None

    def _extract_simple(self, body: str) -> Optional[str]:
        """Простое извлечение кода подтверждения"""
        match = self._simple_pattern.search(body)
        if match:
            return match.group(1)
        return None

    def find_verification_code_in_emails(
        self,
        emails: List[EmailMessage],
        target_email: Optional[str] = None,
        min_timestamp: int = 0,
        used_codes: Optional[set] = None,
    ) -> Optional[str]:
        """
        Найти код подтверждения в списке писем

        Args:
            emails: Список писем
            target_email: Целевой почтовый адрес
            min_timestamp: Минимальная временная метка (для фильтрации старых писем)
            used_codes: Набор использованных кодов подтверждения (для дедупликации)

        Returns:
            Строка с кодом подтверждения, None если не найден
        """
        used_codes = used_codes or set()

        for email in emails:
            # Фильтрация по временной метке
            if min_timestamp > 0 and email.received_timestamp > 0:
                if email.received_timestamp < min_timestamp:
                    logger.debug(f"Пропуск старого письма: {email.subject[:50]}")
                    continue

            # Проверить, является ли это верификационным письмом от OpenAI
            if not self.is_openai_verification_email(email, target_email):
                continue

            # Извлечь код подтверждения
            code = self.extract_verification_code(email)
            if code:
                # Проверка дедупликации
                if code in used_codes:
                    logger.debug(f"Пропуск уже использованного кода подтверждения: {code}")
                    continue

                logger.info(
                    f"[{target_email or 'unknown'}] Найден код подтверждения: {code}, "
                    f"тема письма: {email.subject[:30]}"
                )
                return code

        return None

    def filter_emails_by_sender(
        self,
        emails: List[EmailMessage],
        sender_patterns: List[str],
    ) -> List[EmailMessage]:
        """
        Фильтровать письма по отправителю

        Args:
            emails: Список писем
            sender_patterns: Список шаблонов отправителей

        Returns:
            Отфильтрованный список писем
        """
        filtered = []
        for email in emails:
            sender = email.sender.lower()
            if any(pattern.lower() in sender for pattern in sender_patterns):
                filtered.append(email)
        return filtered

    def filter_emails_by_subject(
        self,
        emails: List[EmailMessage],
        keywords: List[str],
    ) -> List[EmailMessage]:
        """
        Фильтровать письма по ключевым словам темы

        Args:
            emails: Список писем
            keywords: Список ключевых слов

        Returns:
            Отфильтрованный список писем
        """
        filtered = []
        for email in emails:
            subject = email.subject.lower()
            if any(kw.lower() in subject for kw in keywords):
                filtered.append(email)
        return filtered


# Глобальный экземпляр парсера
_parser: Optional[EmailParser] = None


def get_email_parser() -> EmailParser:
    """Получить глобальный экземпляр парсера писем"""
    global _parser
    if _parser is None:
        _parser = EmailParser()
    return _parser
