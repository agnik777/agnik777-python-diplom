```markdown
```
# Backend интернет-магазина

Django REST API для управления интернет-магазином с поддержкой множества

поставщиков, корзины, заказов и YAML-импорта товаров.

---

## 📋 Содержание

- [Установка и запуск](#установка-и-запуск)
- [Модели данных](#модели-данных)
- [API Endpoints](#api-endpoints)
  - [Аутентификация](#1-аутентификация)
  - [Магазины и категории](#2-магазины-и-категории)
  - [Товары](#3-товары)
  - [Корзина](#4-корзина)
  - [Заказы](#5-заказы)
  - [Контакты и телефон](#6-контакты-и-телефон)
  - [Импорт YAML](#7-импорт-yaml-для-владельцев-магазинов)
  - [Изменение разрешения на заказы магазина](#8-изменение-разрешения-на-заказы-магазина)
  - [Получение заказов с товарами владельца магазинов](#9-получение-заказов-с-товарами-владельца-магазинов)
- [Статусы заказов](#статусы-заказов)

---

## Установка и запуск

### 1. Клонирование репозитория

```bash
git clone <url-репозитория>
cd <папка_проекта>
```

### 2. Создание виртуального окружения

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```env
DEBUG=True
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///db.sqlite3
BACKEND_URL=http://localhost:8000
EMAIL_HOST=smtp.yandex.ru
EMAIL_PORT=465
EMAIL_USE_SSL=True
EMAIL_HOST_USER=your-email@yandex.ru
EMAIL_HOST_PASSWORD=your-password
DEFAULT_FROM_EMAIL=your-email@yandex.ru
```

### 5. Применение миграций и запуск

```bash
python manage.py migrate
python manage.py runserver
```

Сервер будет доступен по адресу: **http://localhost:8000**


### 6. Админ-панель доступна по адресу `/admin/` 
(логин/пароль — создайте суперпользователя).

---

## Модели данных

| Модель | Назначение |
|---|---|
| `User` | Пользователь (покупатель/владелец магазина) |
| `Shop` | Магазин поставщика |
| `Category` | Категория товаров |
| `Product` | Продукт (абстрактное название) |
| `ProductInfo` | Конкретное предложение товара в магазине |
| `Parameter` | Параметр товара (цвет, размер и т.д.) |
| `ProductParameter` | Значение параметра для конкретного товара |
| `Order` | Заказ / корзина |
| `OrderItem` | Товар в заказе |
| `Contact` | Адрес доставки |
| `Phone` | Телефон пользователя |
| `ConfirmEmailToken` | Токен подтверждения email |

---

## API Endpoints

### 1. Аутентификация

#### 🔹 Регистрация пользователя

```
POST /api/register/
```

**Тело запроса:**
```json
{
    "first_name": "Иван",
    "last_name": "Иванов",
    "email": "ivan@example.com",
    "password": "securepassword123"
}
```

**Ответ (201 Created):**
```json
{
    "first_name": "Иван",
    "last_name": "Иванов",
    "email": "ivan@example.com"
}
```

> После регистрации на email приходит письмо со ссылкой для подтверждения.

---

#### 🔹 Подтверждение email

```
GET /api/confirm-email/{token_key}/
```

**Ответ (200 OK):**
```json
{
    "detail": "Email успешно подтверждён."
}
```

> По умлчанию тип пользователя "Покупатель".
> 
> Администратор может изменить тип пользователя на "Владелец магазина"
---

#### 🔹 Вход в систему

```
POST /api/login/
```

**Тело запроса:**
```json
{
    "email": "ivan@example.com",
    "password": "securepassword123"
}
```

**Ответ (200 OK):**
```json
{
    "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
    "user_id": 1,
    "email": "ivan@example.com"
}
```

> Полученный токен необходимо передавать в заголовке
> 
> `Authorization: Token <token>` для всех защищенных эндпоинтов.

---

### 2. Магазины и категории

#### 🔹 Список активных магазинов

```
GET /api/shops/
```

**Ответ (200 OK):**
```json
[
    {
        "id": 1,
        "name": "Магазин электроники",
        "url": "https://shop.example.com",
        "owner": 2,
        "owner_email": "owner@example.com"
    }
]
```

---

#### 🔹 Магазины с категориями

```
GET /api/shops/categories/
```

**Параметры (опционально):**
- `category_id` — фильтр по ID категории
- `shop_name` — поиск по названию магазина

**Ответ (200 OK):**
```json
[
    {
        "id": 1,
        "name": "Магазин электроники",
        "url": "https://shop.example.com",
        "owner": 2,
        "owner_email": "owner@example.com",
        "permissions_order": true,
        "categories": [
            {"id": 1, "name": "Смартфоны"},
            {"id": 2, "name": "Ноутбуки"}
        ]
    }
]
```

---

### 3. Товары

#### 🔹 Поиск товаров

```
GET /api/products/search/
```

**Параметры (опционально):**

| Параметр | Тип | Описание |
|---|---|---|
| `shop_name` | string | Название магазина (частичное совпадение) |
| `category_name` | string | Название категории (частичное совпадение) |
| `product_name` | string | Название товара (частичное совпадение) |
| `min_price` | integer | Минимальная цена |
| `max_price` | integer | Максимальная цена |
| `in_stock_only` | boolean | Только в наличии (`true`/`false`) |
| `page` | integer | Номер страницы (пагинация) |

**Пример запроса:**
```
GET /api/products/search/?category_name=Смартфоны&min_price=10000&max_price=50000&in_stock_only=true
```

**Ответ (200 OK):**
```json
{
    "count": 25,
    "next": "http://localhost:8000/api/products/search/?page=2",
    "previous": null,
    "results": [
        {
            "id": 1,
            "product": 1,
            "product_name": "Смартфон X",
            "external_id": 12345,
            "full_name": "Смартфон X 128GB Black",
            "shop": 1,
            "shop_name": "Магазин электроники",
            "quantity": 10,
            "retail_price": 29990,
            "wholesale_price": 24990,
            "sell_up_to": "2025-12-31",
            "parameters": [
                {
                    "id": 1,
                    "product_info": 1,
                    "parameter": 1,
                    "parameter_name": "Цвет",
                    "value": "Черный"
                }
            ],
            "parameters_dict": {
                "Цвет": "Черный",
                "Память": "128GB"
            }
        }
    ]
}
```

---

#### 🔹 Детальная информация о товаре

```
GET /api/products/{id}/
```

**Ответ (200 OK):** аналогично одному объекту из поиска.

---

### 4. Корзина

> Все эндпоинты корзины требуют аутентификации (`Authorization: Token <token>`)
> 
> и доступны только для пользователей с типом `buyer` "Покупатель".

#### 🔹 Просмотр корзины

```
GET /api/cart/
```

**Ответ (200 OK):**
```json
{
    "id": 5,
    "status": "basket",
    "dt": "2024-01-15T14:30:00Z",
    "contact": 1,
    "contact_info": {
        "city": "Москва",
        "street": "Тверская",
        "house": "10",
        "apartment": "5"
    },
    "order_items": [
        {
            "id": 1,
            "product": 1,
            "product_name": "Смартфон X",
            "full_name": "Смартфон X 128GB Black",
            "shop_name": "Магазин электроники",
            "external_id": 12345,
            "retail_price": 29990,
            "quantity": 2,
            "item_total": 59980,
            "max_available": 10
        }
    ],
    "shop_totals": {
        "Магазин электроники": 59980
    },
    "basket_total": 59980
}
```

---

#### 🔹 Добавление товара в корзину

```
POST /api/cart/
```

**Тело запроса:**
```json
{
    "product_id": 1
}
```

**Ответ (200 OK):**
```json
{
    "message": "Товар добавлен в корзину",
    "item": {
        "id": 1,
        "product": 1,
        "product_name": "Смартфон X",
        "full_name": "Смартфон X 128GB Black",
        "shop_name": "Магазин электроники",
        "external_id": 12345,
        "retail_price": 29990,
        "quantity": 1,
        "item_total": 29990,
        "max_available": 10
    }
}
```

> Если товар уже есть в корзине — количество увеличивается на 1.

---

#### 🔹 Изменение количества товара

```
PUT /api/cart/items/{item_id}/
```

**Тело запроса:**
```json
{
    "quantity": 3
}
```

**Ответ (200 OK):**
```json
{
    "message": "Количество товара обновлено",
    "item": { "...обновленный объект..." }
}
```

---

#### 🔹 Удаление товара из корзины

```
DELETE /api/cart/items/{item_id}/
```

**Ответ (200 OK):**
```json
{
    "message": "Товар удален из корзины"
}
```

---

### 5. Заказы

#### 🔹 Создание заказа из корзины

```
POST /api/orders/create/
```

**Тело запроса:**
```json
{
    "contact_id": 1
}
```

**Ответ (201 Created):**
```json
{
    "detail": "Заказ успешно создан",
    "order_id": 5,
    "status": "new",
    "order": { "...детальная информация о заказе..." }
}
```

> При создании заказа отправляются email-уведомления:
> - Покупателю — о создании заказа
> - Владельцам магазинов — о новых товарах в заказе

---

#### 🔹 Подтверждение заказа

```
POST /api/orders/confirm/
```

**Тело запроса:**
```json
{
    "order_id": 5
}
```

**Ответ (200 OK):**
```json
{
    "detail": "Заказ успешно подтвержден",
    "order_id": 5,
    "status": "confirmed",
    "order": { "...детальная информация о заказе..." }
}
```

> Подтвердить можно только заказ со статусом `new`.

---

#### 🔹 Список заказов пользователя

```
GET /api/orders/
```

**Ответ (200 OK):**
```json
[
    {
        "id": 5,
        "status": "new",
        "dt": "2024-01-15T14:30:00Z",
        "total_amount": 59980,
        "items_count": 2
    }
]
```

---

#### 🔹 Детальная информация о заказе

```
GET /api/orders/{id}/
```

**Ответ (200 OK):**
```json
{
    "id": 5,
    "status": "new",
    "dt": "2024-01-15T14:30:00Z",
    "contact": 1,
    "contact_info": {
        "id": 1,
        "city": "Москва",
        "street": "Тверская",
        "house": "10",
        "structure": null,
        "apartment": "5"
    },
    "order_items": [ "...товары..." ],
    "shop_totals": [
        {
            "shop_name": "Магазин электроники",
            "total": 59980,
            "items": [
                {
                    "product_name": "Смартфон X 128GB Black",
                    "quantity": 2,
                    "price": 29990,
                    "item_total": 59980
                }
            ]
        }
    ],
    "total_amount": 59980,
    "phone": "+79991234567"
}
```

---

### 6. Контакты и телефон

#### 🔹 Получение телефона

```
GET /api/phone/
```

**Ответ (200 OK):**
```json
{
    "id": 1,
    "phone": "79991234567"
}
```

---

#### 🔹 Создание/обновление телефона

```
POST /api/phone/
```

**Тело запроса:**
```json
{
    "phone": "+7 (999) 123-45-67"
}
```

**Ответ (200 OK):**
```json
{
    "detail": "Телефон успешно сохранен",
    "phone": {
        "id": 1,
        "phone": "79991234567"
    }
}
```

> Номер очищается от нецифровых символов автоматически.

---

#### 🔹 Список контактов

```
GET /api/contacts/
```

**Ответ (200 OK):**
```json
[
    {
        "id": 1,
        "city": "Москва",
        "street": "Тверская",
        "house": "10",
        "structure": null,
        "apartment": "5"
    }
]
```

---

#### 🔹 Создание контакта

```
POST /api/contacts/
```

**Тело запроса:**
```json
{
    "city": "Санкт-Петербург",
    "street": "Невский проспект",
    "house": "20",
    "structure": "2",
    "apartment": "15"
}
```

**Ответ (201 Created):**
```json
{
    "id": 2,
    "city": "Санкт-Петербург",
    "street": "Невский проспект",
    "house": "20",
    "structure": "2",
    "apartment": "15"
}
```

> Ограничения:
> - Не более 5 контактов на пользователя
> - Адрес должен быть уникальным для пользователя
> - Поля `city`, `street`, `house` обязательны

---

#### 🔹 Получение/обновление/удаление контакта

```
GET /api/contacts/{id}/
PUT /api/contacts/{id}/
PATCH /api/contacts/{id}/
DELETE /api/contacts/{id}/
```

> При удалении проверяется, не используется ли контакт в заказах.

---

### 7. Импорт YAML (для владельцев магазинов)

> Требует аутентификации и прав владельца магазина (`type: 'shop'`).

#### 🔹 Загрузка прайс-листа

```
POST /api/partner/update/
```

**Варианты передачи данных:**

**1. Загрузить файл:**
```
Content-Type: multipart/form-data
file: @price.yaml
```

**2. Указать URL:**
```json
{
    "url": "https://example.com/price.yaml"
}
```

**3. Указать локальный путь:**
```json
{
    "url": "file:///home/user/price.yaml"
}
```

**Формат YAML:**
```yaml
shop: Магазин электроники
url: https://shop.example.com
categories:
  - id: 1
    name: Смартфоны
  - id: 2
    name: Ноутбуки
goods:
  - id: 100
    name: Смартфон X
    category: 1
    full_name: Смартфон X 128GB Black
    quantity: 10
    retail_price: 29990
    wholesale_price: 24990
    parameters:
      Цвет: Черный
      Память: 128GB
  - id: 101
    name: Ноутбук Pro
    category: 2
    full_name: Ноутбук Pro 15" M2
    quantity: 5
    retail_price: 89990
```

**Ответ (200 OK):**
```json
{
    "Status": true,
    "Message": "Данные успешно обновлены",
    "Details": {
        "categories_created": 2,
        "categories_updated": 0,
        "products_created": 2,
        "products_updated": 0
    }
}
```

---

### 8. Изменение разрешения на заказы магазина

#### `PATCH /shops/{id}/permissions/`

Обновляет флаг `permissions_order` — разрешён ли приём заказов для конкретного магазина.

**Заголовки:**
| Параметр | Значение |
|---|---|
| `Authorization` | `Token <token>` |

**Тело запроса (JSON):**
```json
{
  "permissions_order": false
}
```

**Успешный ответ — `200 OK`:**
```json
{
  "permissions_order": false
}
```

**Ошибки:**

| Код | Описание |
|---|---|
| `400 Bad Request` | Некорректные данные |
| `403 Forbidden` | Пользователь не является владельцем магазина |
| `404 Not Found` | Магазин с указанным ID не найден |

**Пример cURL:**
```bash
curl -X PATCH http://127.0.0.1:8000/api/shops/5/permissions/ \
  -H "Authorization: Token ваш_токен" \
  -H "Content-Type: application/json" \
  -d '{"permissions_order": false}'
```

---

### 9. Получение заказов с товарами владельца магазинов

#### `GET /shops/orders/`

Возвращает список заказов, содержащих товары из магазинов авторизованного владельца.  
В каждом заказе отображаются **только те товары**, которые принадлежат магазинам владельца, а **не весь заказ целиком**.

**Заголовки:**
| Параметр | Значение |
|---|---|
| `Authorization` | `Token <token>` |

**Успешный ответ — `200 OK`:**
```json
[
  {
    "id": 42,
    "dt": "2026-04-26T15:30:00+03:00",
    "status": "new",
    "order_items": [
      {
        "product_name": "Молоко Простоквашино 1л",
        "shop_name": "Мой магазин",
        "quantity": 3,
        "retail_price": 89,
        "total_price": 267
      }
    ],
    "total_sum": 267,
    "contact_info": {
      "city": "Москва",
      "street": "Ленина",
      "house": "10",
      "structure": "",
      "apartment": "5",
      "user_name": "Иван Иванов",
      "user_email": "ivan@example.com"
    }
  }
]
```

**Поля ответа:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | `int` | ID заказа |
| `dt` | `string` (ISO 8601) | Дата и время создания заказа |
| `status` | `string` | Статус заказа |
| `order_items` | `array` | Список товаров из магазинов владельца |
| `total_sum` | `int` | Сумма только по товарам владельца |
| `contact_info` | `object` | Контактные данные покупателя |

**Поля `order_items`:**

| Поле | Тип | Описание |
|---|---|---|
| `product_name` | `string` | Полное название товара |
| `shop_name` | `string` | Название магазина |
| `quantity` | `int` | Количество |
| `retail_price` | `int` | Розничная цена за единицу |
| `total_price` | `int` | Общая стоимость (`quantity × retail_price`) |

**Поля `contact_info`:**

| Поле | Тип | Описание |
|---|---|---|
| `city` | `string` | Город |
| `street` | `string` | Улица |
| `house` | `string` | Дом |
| `structure` | `string` | Корпус |
| `apartment` | `string` | Квартира |
| `user_name` | `string` | Имя и фамилия покупателя |
| `user_email` | `string` | Email покупателя |

**Ошибки:**

| Код | Описание |
|---|---|
| `401 Unauthorized` | Пользователь не аутентифицирован |
| `404 Not Found` | У пользователя нет магазинов |

**Пример cURL:**
```bash
curl http://127.0.0.1:8000/api/shops/orders/ \
  -H "Authorization: Token ваш_токен"
```

---

## Статусы заказов

| Статус | Описание |
|---|---|
| `basket` | Корзина (не заказ) |
| `new` | Создан, ожидает подтверждения |
| `confirmed` | Подтвержден покупателем |
| `assembled` | Собран продавцом |
| `sent` | Отправлен |
| `delivered` | Доставлен в пункт выдачи |
| `canceled` | Отменен |
| `returned` | Возвращен |

---

## Примеры использования (curl)

### Регистрация
```bash
curl -X POST http://localhost:8000/api/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"pass123","first_name":"Иван","last_name":"Иванов"}'
```

### Вход
```bash
curl -X POST http://localhost:8000/api/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"pass123"}'
```

### Поиск товаров (с авторизацией)
```bash
curl "http://localhost:8000/api/products/search/?category_name=Смартфоны&in_stock_only=true" \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
```

### Добавление в корзину
```bash
curl -X POST http://localhost:8000/api/cart/ \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b" \
  -H "Content-Type: application/json" \
  -d '{"product_id": 1}'
```

### Оформление заказа
```bash
curl -X POST http://localhost:8000/api/orders/create/ \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b" \
  -H "Content-Type: application/json" \
  -d '{"contact_id": 1}'
```

```