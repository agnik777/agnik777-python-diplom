# backend/social_pipeline.py
"""
Кастомные шаги pipeline для social-auth.
Сохраняем аватар из Яндекса, активируем пользователя, выдаём токен.
"""

from rest_framework.authtoken.models import Token


def save_yandex_avatar(backend, strategy, details, response, user=None, *args, **kwargs):
    """
    Сохраняем аватар из профиля Яндекса в поле avatar_url.
    Активируем пользователя (is_active=True), если он создан через соцсеть.
    """
    if not user:
        return

    # Активируем пользователя (для новых — сразу активен)
    if not user.is_active:
        user.is_active = True

    # Сохраняем аватар из Яндекса
    if backend.name == 'yandex-oauth2':
        # Яндекс возвращает default_avatar_id — формируем URL
        avatar_id = response.get('default_avatar_id', '')
        if avatar_id:
            user.avatar_url = f'https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200'

        # Если email не пришёл (бывает редко), генерируем
        if not user.email and 'email' not in details:
            ya_id = response.get('id', '')
            user.email = f'yandex_{ya_id}@social.local'

    user.save()

    # Создаём или получаем токен
    token, _ = Token.objects.get_or_create(user=user)

    # Сохраняем токен в стратегии, чтобы вернуть его в ответе
    strategy.session['social_auth_token'] = token.key
