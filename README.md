```markdown
```
# Orders API

API для управления заказами. Проект построен на **Django 5.2**, **Django REST Framework 3.14** и **Celery** для фоновых задач.

---

## 📋 Содержание

- [Стек технологий](#-стек-технологий)
- [Структура проекта](#-структура-проекта)
- [Установка и запуск](#-установка-и-запуск)
- [API Эндпоинты](#-api-эндпоинты)
- [Фоновые задачи (Celery)](#-фоновые-задачи-celery)
- [Кэширование](#-кэширование)
- [Мониторинг ошибок (Sentry)](#-мониторинг-ошибок-sentry)
- [Админ-панель (Baton)](#-админ-панель-baton)
- [OpenAPI / Swagger](#-openapi--swagger)
- [Переменные окружения](#-переменные-окружения)

---

## 🛠 Стек технологий

| Компонент           | Технология                              |
|---------------------|-----------------------------------------|
| **Язык**            | Python 3.12+                            |
| **Фреймворк**       | Django 5.2.12                           |
| **API**             | Django REST Framework 3.14              |
| **Фоновые задачи**  | Celery 5.3.6 + Redis                    |
| **Планировщик**     | Celery Beat + django-celery-beat        |
| **База данных**     | SQLite (по умолчанию) / PostgreSQL      |
| **Кэш**             | Redis + Cacheops                        |
| **Документация API**| drf-spectacular + Swagger/Redoc         |
| **Авторизация**     | Token-аутентификация + Яндекс OAuth2    |
| **Мониторинг**      | Sentry                                  |
| **Админка**         | Django Baton 5.1                        |
| **Изображения**     | Pillow + django-imagekit                |
| **Email**           | SMTP (mail.ru)                          |

---

## 📁 Структура проекта

```
orders/
├── orders/                        # Конфигурация Django-проекта
│   ├── __init__.py
│   ├── asgi.py                    # ASGI-конфигурация
│   ├── celery.py                  # Настройки Celery
│   ├── settings.py                # Основные настройки проекта
│   ├── urls.py                    # Корневые URL-маршруты
│   └── wsgi.py                    # WSGI-конфигурация
├── backend/                       # Основное приложение
│   ├── migrations/                # Миграции базы данных
│   ├── __init__.py
│   ├── admin.py                   # Настройки админ-панели
│   ├── apps.py                    # Конфигурация приложения
│   ├── file_loader.py             # Загрузка файлов (URL, локальные)
│   ├── image_tasks.py             # Celery-задачи для изображений
│   ├── models.py                  # Модели данных
│   ├── permissions.py             # Кастомные права доступа
│   ├── pipeline.py                # Pipeline для социальной аутентификации
│   ├── serializers.py             # DRF-сериализаторы
│   ├── tasks.py                   # Celery-задачи (email, очистка)
│   ├── tests.py                   # Тесты
│   ├── throttles.py               # Кастомные лимиты запросов
│   ├── urls.py                    # URL-маршруты приложения
│   ├── utils.py                   # Вспомогательные функции
│   ├── views.py                   # API-представления
│   ├── views_debug.py             # Дебаг-представления
│   └── yaml_processor.py          # Обработка YAML-прайсов
├── static/                        # Статические файлы
├── staticfiles/                   # Собранные статические файлы
├── media/                         # Медиафайлы (загрузки)
├── manage.py                      # Утилита управления Django
└── requirements.txt               # Зависимости проекта
```

---

## 🚀 Установка и запуск

### 1. Клонирование репозитория

```bash
git clone <URL_репозитория>
cd orders
```

### 2. Создание виртуального окружения

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка окружения

Создайте файл `.env` в корне проекта:

```dotenv
# Django
SECRET_KEY=django-insecure-ваш-секретный-ключ
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Email (SMTP mail.ru)
MY_EMAIL=your-email@mail.ru
EMAIL_PASSWORD=your-email-password

# Redis (для Celery и кэша)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
REDIS_URL=redis://localhost:6379/1

# Яндекс OAuth2 (опционально)
YANDEX_APP_ID=ваш-id-приложения
YANDEX_APP_SECRET=ваш-секрет-приложения

# Sentry (опционально)
SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0
```

### 5. Применение миграций

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Сбор статических файлов

```bash
python manage.py collectstatic
```

### 7. Создание суперпользователя

```bash
python manage.py createsuperuser
```

### 8. Запуск сервера разработки

```bash
python manage.py runserver
```

Сервер будет доступен по адресу: **http://localhost:8000**

### 9. Запуск Celery

**Воркер** (обработка фоновых задач):

```bash
celery -A orders worker -l info
```

**Планировщик** (периодические задачи):

```bash
celery -A orders beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

**Мониторинг Flower** (опционально):

```bash
celery -A orders flower --port=5555
```

---

## 📡 API Эндпоинты

### 🔐 Аутентификация

| Метод | URL | Описание |
|-------|-----|----------|
| `POST` | `/api/register/` | Регистрация нового пользователя |
| `GET` | `/api/confirm-email/<token_key>/` | Подтверждение email |
| `POST` | `/api/login/` | Вход в систему |
| `POST` | `/api/logout/` | Выход из системы (удаление токена) |
| `GET` | `/api/social-auth/complete/` | Завершение авторизации через Яндекс |
| `GET` | `/api/social-auth/error/` | Ошибка авторизации через Яндекс |

### 🏪 Магазины

| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/api/shops/` | Список активных магазинов |
| `GET` | `/api/shops/categories/` | Магазины с категориями |
| `PATCH` | `/api/shops/<pk>/permissions/` | Изменение прав доступа магазина (только владелец) |
| `GET` | `/api/shops/orders/` | Заказы магазинов владельца |

### 📦 Товары

| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/api/products/search/` | Поиск товаров с фильтрацией |
| `GET` | `/api/products/<id>/` | Детальная информация о товаре |

**Параметры поиска товаров:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `shop_name` | `string` | Название магазина (частичное совпадение) |
| `category_name` | `string` | Название категории (частичное совпадение) |
| `product_name` | `string` | Название товара (частичное совпадение) |
| `min_price` | `float` | Минимальная розничная цена |
| `max_price` | `float` | Максимальная розничная цена |
| `in_stock_only` | `bool` | Только товары в наличии |
| `page` | `int` | Номер страницы (пагинация) |

### 🛒 Корзина

| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/api/cart/` | Просмотр корзины |
| `POST` | `/api/cart/` | Добавление товара в корзину |
| `PUT` | `/api/cart/item/<item_id>/` | Изменение количества товара |
| `DELETE` | `/api/cart/item/<item_id>/` | Удаление товара из корзины |

### 📋 Заказы

| Метод | URL | Описание |
|-------|-----|----------|
| `POST` | `/api/orders/create/` | Создание заказа из корзины |
| `POST` | `/api/orders/confirm/` | Подтверждение заказа |
| `GET` | `/api/orders/` | Список заказов пользователя |
| `GET` | `/api/orders/<pk>/` | Детальная информация о заказе |

### 👤 Профиль пользователя

| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/api/profile/phone/` | Получение телефона |
| `POST` | `/api/profile/phone/` | Создание/обновление телефона |
| `GET` | `/api/profile/contacts/` | Список контактов |
| `POST` | `/api/profile/contacts/` | Создание контакта |
| `GET/PUT/PATCH/DELETE` | `/api/profile/contacts/<id>/` | CRUD контакта |
| `GET` | `/api/avatar/` | Получить аватар |
| `POST` | `/api/avatar/upload/` | Загрузить аватар |
| `DELETE` | `/api/avatar/delete/` | Удалить аватар |

### 🤝 Партнёрские операции

| Метод | URL | Описание |
|-------|-----|----------|
| `POST` | `/api/partner/update/` | Обновление прайса через YAML |

**Поддерживаемые источники YAML:**
- Загрузка файла через `multipart/form-data`
- URL (`http://` / `https://`)
- Локальный путь (`file://` или абсолютный путь)

### 🖼 Изображения товаров

| Метод | URL | Описание |
|-------|-----|----------|
| `GET/POST` | `/api/product-images/` | Список / загрузка изображения |
| `GET/PUT/PATCH/DELETE` | `/api/product-images/<id>/` | CRUD изображения |
| `GET` | `/api/product-images/by-product/<product_info_id>/` | Изображения товара |
| `POST` | `/api/product-images/bulk-upload/` | Массовая загрузка |
| `POST` | `/api/product-images/<id>/set-main/` | Установить как главное |
| `POST` | `/api/product-images/<id>/regenerate/` | Перегенерировать миниатюры |

---

## ⚙️ Фоновые задачи (Celery)

### Email-уведомления

| Задача | Описание |
|--------|----------|
| `send_confirmation_email_task` | Отправка письма для подтверждения email |
| `send_order_created_email_task` | Уведомление о создании заказа |
| `send_order_confirmed_email_task` | Уведомление о подтверждении заказа |
| `send_order_status_changed_email_task` | Уведомление об изменении статуса |
| `send_all_shop_owner_emails_task` | Уведомление владельцам магазинов |

### Обработка изображений

| Задача | Описание |
|--------|----------|
| `generate_product_thumbnails` | Генерация миниатюр для одного изображения |
| `bulk_generate_thumbnails` | Массовая генерация миниатюр |

### Периодические задачи (Celery Beat)

| Задача | Расписание | Описание |
|--------|------------|----------|
| `cleanup_expired_tokens_task` | Ежедневно в 3:00 | Очистка устаревших токенов |
| `cleanup_expired_baskets_task` | Ежедневно в 4:00 | Очистка устаревших корзин |

### Очереди задач

| Очередь | Назначение |
|---------|------------|
| `default` | Основные задачи (очистка, уведомления владельцам) |
| `email` | Отправка email-писем |

---

## 💾 Кэширование

### Cacheops (автоматическое кэширование запросов)

| Модель | Операции | Время жизни |
|--------|----------|-------------|
| `Shop` | Все | 30 минут |
| `Category` | Все | 30 минут |
| `ProductInfo` | Все | 10 минут |
| `Product` | Все | 10 минут |
| `ProductParameter` | Все | 10 минут |
| Остальные модели `backend.*` | `get`, `fetch` | 5 минут |

### Redis Cache

- **Бэкенд:** `django-redis`
- **База:** Redis `1` (отдельно от Celery)
- **Сжатие:** Zlib
- **Таймаут по умолчанию:** 15 минут

---

## 🐛 Мониторинг ошибок (Sentry)

- **Фильтрация:** Игнорируются `Http404`, `PermissionDenied`, `Throttled`
- **Очистка данных:** Пароли, токены и ключи заменяются на `***`
- **Частота трассировки:** 100% в разработке, 20% в продакшене
- **Профилирование:** 100% в разработке, 10% в продакшене

---

## 🎨 Админ-панель (Baton)

Доступна по адресу: **`/admin/`**

**Группировка разделов:**

| Раздел | Модели |
|--------|--------|
| 👥 Пользователи | User, Contact, Phone, ConfirmEmailToken, Group |
| 📦 Товары и каталог | Shop, Category, Product, ProductInfo, Parameter, ProductParameter, ProductImage |
| 🚚 Заказы | Order, OrderItem |
| 📋 Логи и аудит | LogEntry |

---

## 📖 OpenAPI / Swagger

Документация API генерируется автоматически с помощью **drf-spectacular**.

| Интерфейс | URL |
|-----------|-----|
| Swagger UI | `/api/docs/` |
| Redoc | `/api/redoc/` |
| Схема (JSON) | `/api/schema/` |

---

## 🔐 Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `SECRET_KEY` | Секретный ключ Django | **обязательно** |
| `DEBUG` | Режим отладки | `False` |
| `ALLOWED_HOSTS` | Разрешённые хосты (через запятую) | `*` |
| `MY_EMAIL` | Email для отправки писем | — |
| `EMAIL_PASSWORD` | Пароль от email | — |
| `CELERY_BROKER_URL` | URL брокера Celery | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | URL бэкенда результатов Celery | `redis://localhost:6379/0` |
| `REDIS_URL` | URL для кэша Redis | `redis://localhost:6379/1` |
| `YANDEX_APP_ID` | ID приложения Яндекса для OAuth2 | — |
| `YANDEX_APP_SECRET` | Секрет приложения Яндекса | — |
| `SENTRY_DSN` | DSN для Sentry | — |

---

## 📄 Лицензия

Проект распространяется под лицензией MIT.
