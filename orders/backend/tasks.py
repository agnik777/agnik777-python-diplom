# backend/tasks.py
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import logging

from .utils import (
    ProductUtils,
    EmailUtils,
    OrderUtils,
    ErrorHandler,
)

logger = logging.getLogger(__name__)

# ========== БАЗОВЫЕ ЗАДАЧИ ==========

@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='email')
def send_email_task(self, subject, message, recipient_email):
    """
    Базовая задача для отправки email.
    Использует EmailUtils._send_email.
    """
    try:
        EmailUtils._send_email(subject, message, recipient_email)
        logger.info(f'Email отправлен на {recipient_email}: {subject}')
        return {'success': True, 'recipient': recipient_email}
    except Exception as exc:
        logger.error(f'Ошибка отправки email на {recipient_email}: {exc}')
        raise self.retry(exc=exc)

@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def send_email_with_retry_task(self, subject, message, recipient_email):
    """
    Отправка email с увеличенным количеством повторов.
    Используется для критических уведомлений (подтверждение заказа).
    """
    try:
        EmailUtils._send_email(subject, message, recipient_email)
        logger.info(f'Критический email отправлен на '
                    f'{recipient_email}: {subject}')
        return {'success': True, 'recipient': recipient_email}
    except Exception as exc:
        logger.error(f'Критическая ошибка email на {recipient_email}: {exc}')
        raise self.retry(exc=exc)

# ========== ЗАДАЧИ ДЛЯ РЕГИСТРАЦИИ ==========

@shared_task(queue='email')
def send_confirmation_email_task(user_id, token_key):
    """
    Отправка письма с подтверждением регистрации.
    """
    from .models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f'Пользователь {user_id} не найден при отправке '
                     f'подтверждения')
        return {'success': False, 'error': 'User not found'}

    confirmation_url = f"{settings.BACKEND_URL}/api/confirm-email/{token_key}/"

    message = f"""
Здравствуйте, {user.first_name}!

Для подтверждения регистрации перейдите по ссылке:
{confirmation_url}

Ссылка действительна 24 часа.

Если вы не регистрировались, просто проигнорируйте это письмо.
"""
    send_email_task.delay(
        subject='Подтверждение регистрации',
        message=message.strip(),
        recipient_email=user.email,
    )

    return {'success': True, 'user_id': user_id}

# ========== ЗАДАЧИ ДЛЯ ЗАКАЗОВ ==========

@shared_task(queue='email')
def send_order_created_email_task(user_id, order_id):
    """
    Отправка письма покупателю о создании заказа.
    Использует EmailUtils из utils.py для форматирования.
    """
    from .models import User, Order

    try:
        user = User.objects.get(id=user_id)
        order = Order.objects.select_related('contact').get(id=order_id)
        items = order.order_items.all().select_related('product')
    except (User.DoesNotExist, Order.DoesNotExist) as e:
        logger.error(f'Ошибка при отправке уведомления о '
                     f'заказе {order_id}: {e}')
        return {'success': False, 'error': str(e)}

    items_text = "\n".join(EmailUtils._format_order_items(items))
    total = ProductUtils.calculate_order_total(items)
    address_text = EmailUtils._format_address(order.contact)

    message = f"""
Здравствуйте, {user.first_name} {user.last_name}!
Ваш заказ №{order.id} успешно создан.
Статус заказа: {order.get_status_display()}

Адрес доставки:
{address_text}

Состав заказа:
{items_text}

Общая сумма заказа: {total} ₽

Для подтверждения заказа перейдите в личный кабинет.
Спасибо за ваш заказ!
"""
    send_email_with_retry_task.delay(
        subject=f'Заказ №{order.id} создан',
        message=message.strip(),
        recipient_email=user.email,
    )

    return {'success': True, 'order_id': order_id}

@shared_task(queue='email')
def send_order_confirmed_email_task(user_id, order_id):
    """
    Отправка письма покупателю о подтверждении заказа.
    Использует EmailUtils из utils.py для форматирования.
    """
    from .models import User, Order

    try:
        user = User.objects.get(id=user_id)
        order = Order.objects.select_related('contact').get(id=order_id)
        items = order.order_items.all().select_related('product')
    except (User.DoesNotExist, Order.DoesNotExist) as e:
        logger.error(f'Ошибка при отправке подтверждения '
                     f'заказа {order_id}: {e}')
        return {'success': False, 'error': str(e)}

    items_text = "\n".join(EmailUtils._format_order_items(items))
    total = ProductUtils.calculate_order_total(items)
    address_text = EmailUtils._format_address(order.contact)

    message = f"""
Здравствуйте, {user.first_name} {user.last_name}!
Ваш заказ №{order.id} успешно подтвержден.
Статус заказа: {order.get_status_display()}

Адрес доставки:
{address_text}

Состав заказа:
{items_text}

Общая сумма заказа: {total} ₽

Мы свяжемся с вами для уточнения деталей доставки.
Спасибо за ваш заказ!
"""
    send_email_with_retry_task.delay(
        subject=f'Заказ №{order.id} подтвержден',
        message=message.strip(),
        recipient_email=user.email,
    )

    return {'success': True, 'order_id': order_id}

@shared_task(queue='email')
def send_order_status_changed_email_task(user_id, order_id, previous_status):
    """
    Отправка письма об изменении статуса заказа.
    Использует EmailUtils из utils.py для форматирования.
    """
    from .models import User, Order

    try:
        user = User.objects.get(id=user_id)
        order = Order.objects.select_related('contact').get(id=order_id)
        items = order.order_items.all().select_related('product')
    except (User.DoesNotExist, Order.DoesNotExist) as e:
        logger.error(f'Ошибка при отправке уведомления '
                     f'о статусе {order_id}: {e}')
        return {'success': False, 'error': str(e)}

    items_text = "\n".join(EmailUtils._format_order_items(items))
    total = ProductUtils.calculate_order_total(items)
    address_text = EmailUtils._format_address(order.contact)

    message = f"""
Здравствуйте, {user.first_name} {user.last_name}!
Статус вашего заказа №{order.id} был изменен.

Предыдущий статус: {previous_status}
Новый статус: {order.get_status_display()}

Адрес доставки:
{address_text}

Состав заказа:
{items_text}

Общая сумма заказа: {total} ₽
"""
    send_email_task.delay(
        subject=f'Статус заказа №{order.id} изменен',
        message=message.strip(),
        recipient_email=user.email,
    )

    return {'success': True, 'order_id': order_id}

@shared_task(queue='email')
def send_shop_owner_email_task(shop_owner_id, shop_name, order_id, items_data):
    """
    Отправка письма владельцу магазина о новом заказе.
    Использует EmailUtils из utils.py для форматирования.
    """
    from .models import User, Order

    try:
        shop_owner = User.objects.get(id=shop_owner_id)
        order = Order.objects.select_related('contact__user').get(id=order_id)
    except (User.DoesNotExist, Order.DoesNotExist) as e:
        logger.error(f'Ошибка при отправке уведомления владельцу магазина: {e}')
        return {'success': False, 'error': str(e)}

    # Формируем список товаров из items_data
    items_text_lines = []
    shop_total = 0
    for item_data in items_data:
        item_total = item_data['quantity'] * item_data['price']
        shop_total += item_total
        items_text_lines.append(
            f"- {item_data['name']}: {item_data['quantity']} шт. × "
            f"{item_data['price']} ₽ = {item_total} ₽"
        )
    items_text = "\n".join(items_text_lines)
    address_text = EmailUtils._format_address(order.contact)

    message = f"""
Новый заказ №{order.id}
Магазин: {shop_name}

Информация о покупателе:
Имя: {order.contact.user.first_name} {order.contact.user.last_name}
Email: {order.contact.user.email}

Адрес доставки:
{address_text}

Товары для вашего магазина:
{items_text}

Общая сумма по вашему магазину: {shop_total} ₽
Общий статус заказа: {order.get_status_display()}

Пожалуйста, подготовьте товары к отправке.
"""
    send_email_task.delay(
        subject=f'Новый заказ №{order.id} для магазина {shop_name}',
        message=message.strip(),
        recipient_email=shop_owner.email,
    )

    return {'success': True, 'shop_owner_id': shop_owner_id}

@shared_task(queue='email')
def send_all_shop_owner_emails_task(order_id):
    """
    Отправляет email всем владельцам магазинов,
    чьи товары присутствуют в заказе.
    Использует OrderUtils._get_shops_data из utils.py.
    """
    from .models import Order

    try:
        order = Order.objects.prefetch_related(
            'order_items__product__shop__owner'
        ).get(id=order_id)
    except Order.DoesNotExist as e:
        logger.error(f'Заказ {order_id} не найден: {e}')
        return {'success': False, 'error': str(e)}

    # Используем _get_shops_data из OrderUtils
    shops_data = OrderUtils._get_shops_data(order)

    for shop_id, data in shops_data.items():
        shop = data['shop']
        items_data = [
            {
                'name': item.product.full_name,
                'quantity': item.quantity,
                'price': item.product.retail_price,
            }
            for item in data['items']
        ]

        send_shop_owner_email_task.delay(
            shop_owner_id=shop.owner.id,
            shop_name=shop.name,
            order_id=order_id,
            items_data=items_data,
        )

    return {
        'success': True,
        'order_id': order_id,
        'shops_notified': len(shops_data),
    }

# ========== ПЕРИОДИЧЕСКИЕ ЗАДАЧИ ==========

@shared_task
def cleanup_expired_tokens_task():
    """
    Очистка просроченных токенов подтверждения email.
    """
    from .models import ConfirmEmailToken

    cutoff = timezone.now() - timedelta(hours=24)
    expired_tokens = ConfirmEmailToken.objects.filter(created_at__lt=cutoff)
    count = expired_tokens.count()
    expired_tokens.delete()

    logger.info(f'Очищено {count} просроченных токенов')
    return {'cleaned': count}

@shared_task
def cleanup_expired_baskets_task():
    """
    Очистка старых корзин (старше 7 дней).
    """
    from .models import Order

    cutoff = timezone.now() - timedelta(days=7)
    expired_baskets = Order.objects.filter(status='basket', dt__lt=cutoff)
    count = expired_baskets.count()
    expired_baskets.delete()

    logger.info(f'Очищено {count} просроченных корзин')
    return {'cleaned': count}
