# file_loader.py
import os
import requests
from django.conf import settings
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from requests.exceptions import RequestException


class FileLoader:
    """
    Класс для загрузки файлов из различных источников
    """

    # Разрешенные пути для локальных файлов
    ALLOWED_LOCAL_PATHS = getattr(settings, 'YAML_IMPORT_ALLOWED_PATHS', [
        '/data/imports/',
        '/var/www/uploads/',
        './imports/',
        './uploads/',
    ])

    @staticmethod
    def download_from_url(url):
        """
        Загрузка YAML файла по HTTP/HTTPS URL

        Args:
            url: URL файла

        Returns:
            bytes: Содержимое файла

        Raises:
            ValidationError: Если URL невалиден
            RequestException: Если ошибка загрузки
        """
        # Валидация URL
        validate_url = URLValidator()
        validate_url(url)

        # Настройки таймаута
        timeout = getattr(settings, 'YAML_DOWNLOAD_TIMEOUT', 30)

        # Загрузка файла
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        # Проверка типа контента
        content_type = response.headers.get('Content-Type', '')
        allowed_mime_types = getattr(settings, 'YAML_ALLOWED_MIME_TYPES', [
            'application/x-yaml',
            'text/yaml',
            'text/x-yaml',
            'application/yaml',
        ])

        # Проверяем MIME тип или расширение в URL
        content_type_valid = any(mime in content_type.lower() for mime in allowed_mime_types)
        url_extension_valid = url.lower().endswith(('.yaml', '.yml'))

        if not content_type_valid and not url_extension_valid:
            raise ValidationError('URL должен вести на YAML файл')

        return response.content

    @staticmethod
    def read_local_file(file_path):
        """
        Чтение локального YAML файла с проверкой безопасности

        Args:
            file_path: Путь к файлу

        Returns:
            bytes: Содержимое файла

        Raises:
            FileNotFoundError: Если файл не найден
            ValidationError: Если файл невалиден
            PermissionError: Если доступ запрещен
        """
        # Нормализация пути
        normalized_path = FileLoader._normalize_and_validate_path(file_path)

        # Проверка существования файла
        if not os.path.exists(normalized_path):
            raise FileNotFoundError(f"Файл не найден: {normalized_path}")

        # Проверка расширения файла
        if not normalized_path.lower().endswith(('.yaml', '.yml')):
            raise ValidationError('Файл должен иметь расширение .yaml или .yml')

        # Проверка размера файла
        max_size = getattr(settings, 'YAML_MAX_FILE_SIZE', 10 * 1024 * 1024)
        file_size = os.path.getsize(normalized_path)
        if file_size > max_size:
            raise ValidationError(f'Размер файла превышает {max_size / 1024 / 1024}MB')

        # Чтение файла
        with open(normalized_path, 'rb') as f:
            return f.read()

    @staticmethod
    def _normalize_and_validate_path(file_path):
        """
        Нормализация и валидация пути к файлу

        Args:
            file_path: Входной путь

        Returns:
            str: Абсолютный нормализованный путь

        Raises:
            PermissionError: Если путь не безопасен
        """
        # Преобразуем в абсолютный путь
        if os.path.isabs(file_path):
            abs_path = file_path
        else:
            # Относительный путь - относительно BASE_DIR Django
            abs_path = os.path.join(settings.BASE_DIR, file_path)

        # Нормализуем путь
        normalized_path = os.path.normpath(abs_path)

        # Проверка безопасности пути
        FileLoader._validate_path_security(normalized_path)

        return normalized_path

    @staticmethod
    def _validate_path_security(file_path):
        """
        Проверка безопасности пути к файлу

        Args:
            file_path: Путь для проверки

        Raises:
            PermissionError: Если путь не безопасен
        """
        abs_path = os.path.abspath(file_path)

        # Проверяем все разрешенные пути
        allowed_paths = FileLoader.ALLOWED_LOCAL_PATHS.copy()

        # Добавляем MEDIA_ROOT если настроен
        if hasattr(settings, 'MEDIA_ROOT'):
            allowed_paths.append(settings.MEDIA_ROOT)

        # Добавляем STATIC_ROOT если настроен
        if hasattr(settings, 'STATIC_ROOT'):
            allowed_paths.append(settings.STATIC_ROOT)

        # Проверяем каждый разрешенный путь
        for allowed_path in allowed_paths:
            allowed_abs = os.path.abspath(allowed_path)
            try:
                # Проверяем, находится ли файл внутри разрешенной директории
                if os.path.commonpath([abs_path, allowed_abs]) == allowed_abs:
                    return  # Путь разрешен
            except ValueError:
                # Нет общего пути
                continue

        # Если не нашли разрешенный путь
        raise PermissionError(
            f"Доступ к пути запрещен: {file_path}\n"
            f"Разрешенные пути: {FileLoader.ALLOWED_LOCAL_PATHS}"
        )
