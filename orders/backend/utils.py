# backend/utils.py
import yaml
from datetime import datetime
from collections import defaultdict

from django.http import JsonResponse
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q, Sum
from django.core.exceptions import ValidationError
from typing import List, Optional, Dict, Any
from requests.exceptions import RequestException
from .file_loader import FileLoader


class BaseEmailUtils:
    """Базовый класс с общей логикой для генерации писем."""

    @staticmethod
    def _format_order_items(order_items) -> List[str]:
        """Форматирует список товаров заказа."""
        return [
            f"- {item.product.full_name}: {item.quantity} шт. × {item.product.retail_price} ₽ = "
            f"{ProductUtils.calculate_item_total(item)} ₽"
            for item in order_items
        ]

    @staticmethod
    def _format_address(contact) -> str:
        """Форматирует адрес доставки."""
        lines = [
            f"Город: {contact.city}",
            f"Улица: {contact.street}",
            f"Дом: {contact.house}"
        ]
        if contact.structure:
            lines.append(f"Корпус: {contact.structure}")
        if contact.apartment:
            lines.append(f"Квартира: {contact.apartment}")
        return "\n".join(lines)

    @staticmethod
    def _send_email(subject: str, message: str, recipient_email: str) -> None:
        """Базовый метод отправки email."""
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )


class ProductUtils:
    """Утилиты для работы с товарами"""

    @staticmethod
    def parse_date(date_str):
        """
        Парсит дату из строки в формате:
        - 'YYYY-MM-DD'
        - 'DD.MM.YYYY'
        Возвращает объект date или None при ошибке.
        """
        if not date_str:
            return None

        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None

    @staticmethod
    def is_product_expired(product) -> bool:
        """
        Проверяет, просрочен ли товар.
        Возвращает True если товар просрочен, False если нет или дата не указана.
        """
        if not product.sell_up_to:
            return False
        sell_date = ProductUtils.parse_date(product.sell_up_to)
        if not sell_date:
            return False
        return sell_date < timezone.now().date()

    @staticmethod
    def get_available_products_queryset():
        """
        Возвращает QuerySet с доступными товарами.
        (магазин разрешает заказы, товар в наличии, не просрочен)
        """
        from .models import ProductInfo

        queryset = ProductInfo.objects.filter(
            shop__permissions_order=True,
            quantity__gt=0
        )
        return ProductUtils.exclude_expired_products(queryset)

    @staticmethod
    def exclude_expired_products(queryset):
        """Исключает просроченные товары из queryset (оптимизировано)."""
        today = timezone.now().date()
        exclude_conditions = Q()

        for product_info in queryset:
            sell_up_to = product_info.sell_up_to
            if not sell_up_to or sell_up_to.strip() == '':
                continue

            date_obj = ProductUtils.parse_date(sell_up_to)
            if date_obj and date_obj < today:
                exclude_conditions |= Q(id=product_info.id)

        return queryset.exclude(exclude_conditions)

    @staticmethod
    def calculate_item_total(item) -> int:
        """Рассчитывает стоимость позиции."""
        return item.quantity * item.product.retail_price

    @staticmethod
    def calculate_order_total(order_items) -> int:
        """Рассчитывает общую сумму заказа."""
        return sum(
            ProductUtils.calculate_item_total(item) for item in order_items)


class OrderUtils:
    """Утилиты для работы с заказами"""

    @staticmethod
    def add_item_to_basket(basket, product) -> Dict[str, Any]:
        """Добавляет товар в корзину"""
        from .models import OrderItem

        order_item, created = OrderItem.objects.get_or_create(
            order=basket,
            product=product,
            defaults={'quantity': 1}
        )

        if not created:
            # Товар уже был в корзине, увеличиваем количество
            available_qty = product.get_available_quantity()
            if order_item.quantity < available_qty:
                order_item.quantity += 1
                order_item.save()
                return {'success': True, 'message': 'Количество товара увеличено', 'item': order_item}
            else:
                return {'success': False, 'error': f'Доступно только {available_qty} единиц товара'}

        return {'success': True, 'message': 'Товар добавлен в корзину', 'item': order_item}

    @staticmethod
    def send_order_notifications(user, order, contact, phone) -> None:
        """Отправляет все уведомления при создании заказа."""
        EmailUtils.send_order_created_email(user, order, contact, phone)
        OrderUtils._send_shop_owner_emails(order)

    @staticmethod
    def send_order_confirmed_notifications(user, order, previous_status: str) -> None:
        """Отправляет все уведомления при подтверждении заказа."""
        EmailUtils.send_order_confirmed_email(user, order)
        EmailUtils.send_order_status_changed_email(user, order, previous_status)
        OrderUtils._send_shop_owner_emails(order)

    @staticmethod
    def _send_shop_owner_emails(order) -> None:
         """Отправляет email владельцам магазинов."""
         # Исправлен вызов: теперь передается 4 аргумента вместо 5 (убран shop_total)
         shops_data = OrderUtils._get_shops_data(order)
         for shop_data in shops_data.values():
             EmailUtils.send_shop_order_email(
                 shop_data['shop'].owner,
                 shop_data['shop'],
                 order,
                 shop_data['items']
             )

    @staticmethod
    def _get_shops_data(order) -> Dict[int, Dict]:
        """Группирует товары заказа по магазинам (оптимизировано)."""
        # Используем defaultdict для автоматической инициализации словаря для каждого магазина.
        # Ключ — ID магазина (целое число), а не строка.
        shops_data = defaultdict(lambda: {'items': [], 'total': 0})

        for item in order.order_items.all().select_related('product__shop'):
            shop = item.product.shop
            shops_data[shop.id]['shop'] = shop  # Сохраняем объект магазина один раз на итерацию цикла по ключу.
            shops_data[shop.id]['items'].append(item)

        # Расчет суммы по каждому магазину (можно было бы сделать через annotate в БД,
        # но для простоты и наглядности оставлен расчет на Python).
        for shop_id, data in shops_data.items():
            data['total'] = sum(
                ProductUtils.calculate_item_total(item) for item in data['items']
            )
        return dict(shops_data)


class EmailUtils(BaseEmailUtils):
    """Утилиты для отправки email. Наследует общую логику от BaseEmailUtils."""

    @staticmethod
    def send_order_created_email(user, order, contact, phone) -> None:
        """Email о создании заказа."""
        items_text = "\n".join(EmailUtils._format_order_items(order.order_items.all()))
        total = ProductUtils.calculate_order_total(order.order_items.all())

        message = f"""
    Здравствуйте, {user.first_name} {user.last_name}!
    Ваш заказ №{order.id} успешно создан.
    Статус заказа: {order.get_status_display()}

    Адрес доставки:
    {EmailUtils._format_address(contact)}
    Телефон для связи: {phone.phone}

    Состав заказа:
    {items_text}

    Общая сумма заказа: {total} ₽

    Для подтверждения заказа перейдите в личный кабинет.
    Спасибо за ваш заказ!
    """
        EmailUtils._send_email(f'Заказ №{order.id} создан', message, user.email)

    @staticmethod
    def send_order_confirmed_email(user, order) -> None:
        """Email о подтверждении заказа."""
        items_text = "\n".join(EmailUtils._format_order_items(order.order_items.all()))
        total = ProductUtils.calculate_order_total(order.order_items.all())

        message = f"""
    Здравствуйте, {user.first_name} {user.last_name}!
    Ваш заказ №{order.id} успешно подтвержден.
    Статус заказа: {order.get_status_display()}

    Адрес доставки:
    {EmailUtils._format_address(order.contact)}

    Состав заказа:
    {items_text}

    Общая сумма заказа: {total} ₽

    Мы свяжемся с вами для уточнения деталей доставки.
    Спасибо за ваш заказ!
    """
        EmailUtils._send_email(f'Заказ №{order.id} подтвержден', message, user.email)

    @staticmethod
    def send_shop_order_email(shop_owner, shop, order, items) -> None:
        """Email владельцу магазина о новом заказе. Принимает 4 аргумента."""
        items_text = "\n".join(EmailUtils._format_order_items(items))
        shop_total = sum(ProductUtils.calculate_item_total(item) for item in items)

        message = f"""
    Новый заказ №{order.id}
    Магазин: {shop.name}

    Информация о покупателе:
    Имя: {order.contact.user.first_name} {order.contact.user.last_name}
    Email: {order.contact.user.email}

    Адрес доставки:
    {EmailUtils._format_address(order.contact)}

    Товары для вашего магазина:
    {items_text}

    Общая сумма по вашему магазину: {shop_total} ₽
    Общий статус заказа: {order.get_status_display()}

    Пожалуйста, подготовьте товары к отправке.
    """
        EmailUtils._send_email(
            f'Новый заказ №{order.id} для магазина {shop.name}',
            message,
            shop_owner.email
        )

    @staticmethod
    def send_order_status_changed_email(user, order, previous_status: str) -> None:
        """Email об изменении статуса заказа."""
        items_text = "\n".join(EmailUtils._format_order_items(order.order_items.all()))
        total = ProductUtils.calculate_order_total(order.order_items.all())

        message = f"""
    Здравствуйте, {user.first_name} {user.last_name}!
    Статус вашего заказа №{order.id} был изменен.

    Предыдущий статус: {previous_status}
    Новый статус: {order.get_status_display()}

    Адрес доставки:
    {EmailUtils._format_address(order.contact)}

    Состав заказа:
    {items_text}

    Общая сумма заказа: {total} ₽
    """
        EmailUtils._send_email(
            f'Статус заказа №{order.id} изменен',
            message,
            user.email
        )


class FileUtils:
    """Утилиты для работы с файлами"""

    @staticmethod
    def load_yaml_content(url: Optional[str], file_path: Optional[str],
                          uploaded_file) -> bytes:
        """Загружает YAML контент из различных источников"""

        if uploaded_file:
            if not uploaded_file.name.lower().endswith(('.yaml', '.yml')):
                raise ValidationError('Файл должен быть в формате YAML '
                                      '(.yaml или .yml)')
            return uploaded_file.read()

        elif url and (url.startswith('http://') or url.startswith('https://')):
            return FileLoader.download_from_url(url)

        elif url and url.startswith('file://'):
            return FileLoader.read_local_file(url[7:])

        elif file_path:
            return FileLoader.read_local_file(file_path)

        elif url:
            return FileLoader.read_local_file(url)

        else:
            raise ValidationError(
                'Не указаны необходимые аргументы. '
                'Используйте один из параметров: url, '
                'file_path или загрузите файл'
            )


class ErrorHandler:
    """Утилиты для обработки ошибок"""

    ERROR_MAPPING = {
        ValidationError: (400, lambda e: f'Ошибка валидации: {str(e)}'),
        FileNotFoundError: (404, lambda e: f'Файл не найден: {str(e)}'),
        PermissionError: (403, lambda e: f'Ошибка доступа: {str(e)}'),
        yaml.YAMLError: (400, lambda e: f'Ошибка парсинга YAML: {str(e)}'),
        RequestException: (400, lambda e: f'Ошибка загрузки по URL: {str(e)}'),
    }

    @staticmethod
    def handle_error(error):
        """Обрабатывает ошибку и возвращает JsonResponse"""
        for error_type, (status_code, message_func) in (
                ErrorHandler.ERROR_MAPPING.items()):
            if isinstance(error, error_type):
                return JsonResponse(
                    {'Status': False, 'Error': message_func(error)},
                    status=status_code
                )

        return JsonResponse(
            {'Status': False, 'Error': f'Внутренняя ошибка: {str(error)}'},
            status=500
        )
