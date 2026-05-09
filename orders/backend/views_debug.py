# backend/views_debug.py
"""
Debug views — для тестирования Sentry и мониторинга.
"""

import logging
import random

import sentry_sdk
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle

from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiExample,
)


logger = logging.getLogger(__name__)


class SentryDebugView(APIView):
    """
    Эндпоинт для тестирования интеграции с Sentry.
    Намеренно вызывает исключение и отправляет его в Sentry.

    Использование:
        GET /api/debug/sentry/ — вызывает ZeroDivisionError
        GET /api/debug/sentry/?type=value — вызывает ValueError
        GET /api/debug/sentry/?type=key — вызывает KeyError
        GET /api/debug/sentry/?type=attr — вызывает AttributeError
        GET /api/debug/sentry/?type=import — вызывает ImportError
        GET /api/debug/sentry/?type=custom — кастомное исключение
        GET /api/debug/sentry/?type=nested — вложенные вызовы
        GET /api/debug/sentry/?type=slow — долгий запрос (5 сек)
        GET /api/debug/sentry/?type=log — отправка лога в Sentry
        GET /api/debug/sentry/?type=message — отправка сообщения
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]
    authentication_classes = []  # Не требует аутентификации

    @extend_schema(
        summary='Тестирование Sentry',
        description=(
            'Намеренно вызывает исключение для проверки интеграции с Sentry.\n\n'
            'Параметр `type` определяет тип ошибки:\n'
            '- `zero` (по умолчанию) — ZeroDivisionError\n'
            '- `value` — ValueError\n'
            '- `key` — KeyError\n'
            '- `attr` — AttributeError\n'
            '- `import` — ImportError\n'
            '- `custom` — кастомное исключение\n'
            '- `nested` — вложенные вызовы\n'
            '- `slow` — долгий запрос (5 сек)\n'
            '- `log` — отправка лога в Sentry\n'
            '- `message` — отправка сообщения в Sentry'
        ),
        parameters=[
            {
                'name': 'type',
                'in': 'query',
                'description': 'Тип ошибки',
                'required': False,
                'schema': {
                    'type': 'string',
                    'default': 'zero',
                    'enum': [
                        'zero', 'value', 'key', 'attr',
                        'import', 'custom', 'nested',
                        'slow', 'log', 'message',
                    ],
                },
            },
        ],
        responses={
            200: OpenApiResponse(
                description='Успешный ответ (если ошибка не возникла)',
            ),
            500: OpenApiResponse(
                description='Ошибка (отправлена в Sentry)',
            ),
        },
        examples=[
            OpenApiExample(
                name='ZeroDivisionError',
                value={'error': 'ZeroDivisionError', 'detail': 'division by zero'},
                response_only=True,
            ),
            OpenApiExample(
                name='Message',
                value={'status': 'ok', 'message': 'Сообщение отправлено в Sentry'},
                response_only=True,
            ),
        ],
    )
    def get(self, request, *args, **kwargs):
        error_type = request.query_params.get('type', 'zero')

        with sentry_sdk.start_transaction(
            op='debug',
            name=f'GET /api/debug/sentry/?type={error_type}',
        ):
            sentry_sdk.set_tag('debug_type', error_type)
            sentry_sdk.set_context('debug_info', {
                'error_type': error_type,
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'ip': request.META.get('REMOTE_ADDR', ''),
            })

            if error_type == 'zero':
                # ZeroDivisionError
                logger.warning('Тестовое предупреждение перед ошибкой')
                result = 1 / 0

            elif error_type == 'value':
                # ValueError
                raise ValueError('Неверное значение параметра')

            elif error_type == 'key':
                # KeyError
                data = {'a': 1}
                value = data['non_existent_key']

            elif error_type == 'attr':
                # AttributeError
                obj = None
                obj.some_method()

            elif error_type == 'import':
                # ImportError
                import non_existent_module

            elif error_type == 'custom':
                # Кастомное исключение
                class CustomBusinessError(Exception):
                    def __init__(self, message, code):
                        self.message = message
                        self.code = code
                        super().__init__(self.message)

                raise CustomBusinessError(
                    message='Нарушение бизнес-логики',
                    code='BIZ-001',
                )

            elif error_type == 'nested':
                # Вложенные вызовы с несколькими ошибками
                def inner_function():
                    return 1 / 0

                def middle_function():
                    try:
                        inner_function()
                    except ZeroDivisionError:
                        raise ValueError('Ошибка в middle_function')

                def outer_function():
                    middle_function()

                outer_function()

            elif error_type == 'slow':
                # Долгий запрос (для performance monitoring)
                import time
                time.sleep(5)
                return Response({
                    'status': 'ok',
                    'message': 'Медленный запрос выполнен',
                })

            elif error_type == 'log':
                # Отправка лога в Sentry
                logger.error(
                    'Критическая ошибка в бизнес-процессе',
                    extra={
                        'user_id': request.user.id if request.user.is_authenticated else None,
                        'action': 'test_error',
                        'details': {
                            'order_id': random.randint(1000, 9999),
                            'amount': round(random.uniform(100, 10000), 2),
                        },
                    }
                )
                return Response({
                    'status': 'ok',
                    'message': 'Лог отправлен в Sentry',
                })

            elif error_type == 'message':
                # Отправка кастомного сообщения
                from sentry_sdk import capture_message
                capture_message(
                    'Тестовое сообщение из API',
                    level='info',
                )
                sentry_sdk.set_context('custom_data', {
                    'source': 'sentry_debug_view',
                    'timestamp': __import__('datetime').datetime.now().isoformat(),
                })
                return Response({
                    'status': 'ok',
                    'message': 'Сообщение отправлено в Sentry',
                })

            else:
                return Response(
                    {'error': f'Неизвестный тип ошибки: {error_type}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response({'status': 'ok'})
