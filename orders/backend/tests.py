from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from django.core.cache import cache
from unittest.mock import patch

User = get_user_model()

@override_settings(
    REST_FRAMEWORK={
        'DEFAULT_THROTTLE_RATES': {
            'register': '3/hour',
            'login': '5/minute',
            'confirm_email': '10/minute',
            'partner_update': '2/hour',
            'anon': '100/day',
            'user': '1000/day',
        },
        'TEST_REQUEST_DEFAULT_FORMAT': 'json',
    }
)
class ThrottlingTestCase(TestCase):
    """
    Тесты для проверки работы тротлинга на эндпоинтах.
    """

    def setUp(self):
        self.client = APIClient()
        # ✅ Правильный сброс кеша
        cache.clear()

    # ──────────────── Регистрация ────────────────

    def test_register_throttle_blocks_after_limit(self):
        """
        Проверяем, что после 3 запросов на регистрацию
        4-й получает 429 Too Many Requests.
        """
        url = reverse('register')

        # Первые 3 запроса
        for i in range(3):
            response = self.client.post(
                url,
                {
                    'email': f'test{i}@example.com',
                    'password': 'pass12345',
                    'first_name': 'Test',
                    'last_name': 'User'
                },
                format='json'
            )
            self.assertNotEqual(
                response.status_code,
                status.HTTP_429_TOO_MANY_REQUESTS,
                f'Запрос {i+1} не должен быть заблокирован'
            )

        # 4-й запрос — должен быть заблокирован
        response = self.client.post(
            url,
            {
                'email': 'blocked@example.com',
                'password': 'pass12345',
                'first_name': 'Test',
                'last_name': 'User'
            },
            format='json'
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS
        )

    # ──────────────── Вход ────────────────

    def test_login_throttle_blocks_after_limit(self):
        """
        Проверяем, что после 5 запросов на вход
        6-й получает 429 Too Many Requests.
        """
        # Создаём пользователя
        User.objects.create_user(
            email='testuser@example.com',
            password='testpass123',
            is_active=True
        )

        url = reverse('login')

        # 5 запросов с неверным паролем
        for i in range(5):
            response = self.client.post(
                url,
                {'email': 'testuser@example.com', 'password': 'wrongpass'},
                format='json'
            )
            self.assertNotEqual(
                response.status_code,
                status.HTTP_429_TOO_MANY_REQUESTS,
                f'Запрос {i+1} на вход не должен быть заблокирован'
            )

        # 6-й запрос — должен быть заблокирован
        response = self.client.post(
            url,
            {'email': 'testuser@example.com', 'password': 'testpass123'},
            format='json'
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS
        )

    # ──────────────── Подтверждение email ────────────────

    def test_confirm_email_throttle_blocks_after_limit(self):
        """
        Проверяем, что после 10 запросов на подтверждение email
        11-й получает 429.
        """
        # Создаём пользователя с токеном
        user = User.objects.create_user(
            email='confirm@example.com',
            password='testpass123',
            is_active=False
        )
        from .models import ConfirmEmailToken
        token = ConfirmEmailToken.objects.create(user=user)

        url = reverse('confirm-email', kwargs={'token_key': token.key})

        # 10 запросов к одному токену
        for i in range(10):
            response = self.client.get(url)
            self.assertNotEqual(
                response.status_code,
                status.HTTP_429_TOO_MANY_REQUESTS,
                f'Запрос {i+1} на подтверждение не должен быть заблокирован'
            )

        # Создаём новый токен для 11-го запроса
        token2 = ConfirmEmailToken.objects.create(user=user)
        url2 = reverse('confirm-email', kwargs={'token_key': token2.key})

        response = self.client.get(url2)
        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS
        )

    # ──────────────── Импорт прайса ────────────────

    @patch('backend.views.YAMLProcessor.parse_yaml')
    @patch('backend.views.YAMLProcessor.process_data')
    @patch('backend.views.FileLoader.download_from_url')
    def test_partner_update_throttle_blocks_after_limit(
        self, mock_download, mock_process, mock_parse
    ):
        """
        Проверяем, что после 2 успешных импортов прайса
        3-й получает 429 Too Many Requests.
        """
        # Создаём пользователя-поставщика
        user = User.objects.create_user(
            email='partner@example.com',
            password='testpass123',
            is_active=True,
            type='owner'
        )
        from .models import Shop
        Shop.objects.create(
            name='Test Shop',
            owner=user,
            permissions_order=True
        )

        self.client.force_authenticate(user=user)

        # Настраиваем моки
        mock_download.return_value = b'shop: test\ngoods: []'
        mock_parse.return_value = {
            'shop': 'Test Shop',
            'categories': [],
            'goods': []
        }
        mock_process.return_value = {
            'created_categories': 0,
            'created_products': 0,
            'updated_products': 0
        }

        url = reverse('partner-update')

        # 2 запроса — должны пройти
        for i in range(2):
            response = self.client.post(
                url,
                {'url': 'http://example.com/price.yaml'},
                format='json'
            )
            self.assertNotEqual(
                response.status_code,
                status.HTTP_429_TOO_MANY_REQUESTS,
                f'Запрос {i+1} импорта не должен быть заблокирован'
            )

        # 3-й запрос — должен быть заблокирован
        response = self.client.post(
            url,
            {'url': 'http://example.com/price2.yaml'},
            format='json'
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS
        )

    # ──────────────── Разные IP не мешают друг другу ────────────────

    def test_different_ips_have_separate_limits(self):
        """
        Проверяем, что для разных IP-адресов лимиты считаются отдельно.
        """
        url = reverse('register')

        # Первый IP — 3 запроса
        for i in range(3):
            response = self.client.post(
                url,
                {
                    'email': f'ip1_{i}@example.com',
                    'password': 'pass12345',
                    'first_name': 'Test',
                    'last_name': 'User'
                },
                format='json',
                REMOTE_ADDR='192.168.1.1'
            )
            self.assertNotEqual(
                response.status_code,
                status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Второй IP — тоже 3 запроса
        for i in range(3):
            response = self.client.post(
                url,
                {
                    'email': f'ip2_{i}@example.com',
                    'password': 'pass12345',
                    'first_name': 'Test',
                    'last_name': 'User'
                },
                format='json',
                REMOTE_ADDR='192.168.1.2'
            )
            self.assertNotEqual(
                response.status_code,
                status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Первый IP — 4-й запрос заблокирован
        response = self.client.post(
            url,
            {
                'email': 'ip1_blocked@example.com',
                'password': 'pass12345',
                'first_name': 'Test',
                'last_name': 'User'
            },
            format='json',
            REMOTE_ADDR='192.168.1.1'
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS
        )

        # Второй IP — 4-й запрос тоже заблокирован
        response = self.client.post(
            url,
            {
                'email': 'ip2_blocked@example.com',
                'password': 'pass12345',
                'first_name': 'Test',
                'last_name': 'User'
            },
            format='json',
            REMOTE_ADDR='192.168.1.2'
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS
        )