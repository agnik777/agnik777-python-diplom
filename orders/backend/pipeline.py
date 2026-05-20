# backend/pipeline.py
"""
Кастомные шаги pipeline для social-auth.
Сохраняем аватар из Яндекса, активируем пользователя, выдаём токен.
"""

from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
import logging


logger = logging.getLogger(__name__)
User = get_user_model()

def associate_by_email_or_create(backend, strategy, *args, **kwargs):
    """
    Связываем пользователя по email или создаем нового,
    если пользователя с таким email не существует.
    """
    user = kwargs.get('user')
    details = kwargs.get('details')
    response = kwargs.get('response')

    if not user and details.get('email'):
        try:
            user = User.objects.get(email=details['email'])
        except ObjectDoesNotExist:
            pass  # Сохранится в social_core.pipeline.user.create_user

    return {'user': user}

def save_yandex_data(backend, strategy, details, response, *args, **kwargs):
    """
    Сохраняем данные из Яндекса:
    - аватарку
    - имя/фамилию
    - email (если пустой)
    - создаем/обновляем токен
    """
    user = kwargs.get('user')
    if not user:
        return

    try:
        # 1️⃣ Сохраняем avatar_url
        avatar_id = response.get('default_avatar_id')
        is_default = response.get('is_default_avatar', True)

        if avatar_id and not is_default:
            user.avatar_url = f'https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200'
        elif not user.avatar_url:
            user.avatar_url = None  # Сбрасываем, если аватара нет

        # 2️⃣ Обновляем имя/фамилию
        user.first_name = response.get('first_name', user.first_name)
        user.last_name = response.get('last_name', user.last_name)

        # 3️⃣ Если email не задан — берем из Яндекса
        if not user.email:
            user.email = response.get('default_email',
                                      f'yandex_{response["id"]}@local.social')

        user.save()

        # 4️⃣ Создаем/обновляем токен
        token, created = Token.objects.get_or_create(user=user)
        logger.info(
            f"Successfully saved Yandex data for user {user.email}. "
            f"Token: {token.key[:8]}... (created: {created})"
        )

    except Exception as e:
        logger.error(f"Error saving Yandex data: {e}")
        raise  # Прерываем pipeline на ошибке
