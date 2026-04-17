# views.py
import yaml
import requests
from datetime import timedelta

from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone
from requests import get
from rest_framework.views import APIView
from yaml import load as load_yaml, Loader
from .models import (Shop, Category, Product, ProductInfo, Parameter,
                     ProductParameter, ConfirmEmailToken)
from requests.exceptions import RequestException
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .permissions import IsShopOwner
from .serializers import YAMLImportSerializer
from .yaml_processor import YAMLProcessor
from .file_loader import FileLoader
from .serializers import UserRegistrationSerializer, UserLoginSerializer
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.conf import settings


class UserRegistrationView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        # Создаем токен
        token = ConfirmEmailToken.objects.create(user=user)
        self.send_confirmation_email(user, token.key)

    def send_confirmation_email(self, user, token_key):
        confirmation_url = f"{settings.BACKEND_URL}/api/confirm-email/{token_key}/"
        message = f"""
        Здравствуйте, {user.first_name}!

        Для подтверждения регистрации перейдите по ссылке:
        {confirmation_url}
        
        Ссылка действительна 24 часа.

        Если вы не регистрировались, просто проигнорируйте это письмо.
        """
        send_mail(
            subject='Подтверждение регистрации',
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )


class ConfirmEmailView(APIView):
    def get(self, request, token_key):
        try:
            # Поиск токена и пользователя через связь в ConfirmEmailToken
            token = ConfirmEmailToken.objects.get(key=token_key)
            if timezone.now() - token.created_at > timedelta(hours=24):
                token.delete()
                return Response(
                    {'detail': 'Токен устарел.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user = token.user
            # Активация пользователя (используем поле is_active из вашей модели User)
            user.is_active = True
            user.save(using=user._state.db)  # Явно указываем базу, как в UserManager
            token.delete()
            return Response(
                {'detail': 'Email успешно подтверждён.'},
                status=status.HTTP_200_OK
            )
        except ConfirmEmailToken.DoesNotExist:
            return Response(
                {'detail': 'Неверный или устаревший токен.'},
                status=status.HTTP_400_BAD_REQUEST
            )


class UserLoginView(generics.GenericAPIView):
    serializer_class = UserLoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        # Проверяем, активирован ли пользователь
        if not user.is_active:
            return Response(
                {'detail': 'Аккаунт не активирован. '
                           'Проверьте вашу почту для подтверждения.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Обновляем логин-статистику
        user.last_login_time = timezone.now()
        user.login_count += 1
        user.save()

        # Получаем или создаем токен для пользователя
        token, created = Token.objects.get_or_create(user=user)

        return Response({
            'token': token.key,
            'user_id': user.pk,
            'email': user.email
        }, status=status.HTTP_200_OK)




'''
class PartnerUpdate(APIView):
    """
    Класс для обновления прайса от поставщика
    """
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'Status': False, 'Error': 'Log in required'},
                status=403
            )

        if request.user.type != 'owner':
            return JsonResponse(
                {'Status': False, 'Error': 'Только для магазинов'},
                status=403
            )

        url = request.data.get('url')
        if not url:
            return JsonResponse(
                {'Status': False, 'Errors': 'Не указан URL'},
                status=400
            )

        validate_url = URLValidator()
        try:
            validate_url(url)
        except ValidationError as e:
            return JsonResponse({'Status': False,
                                 'Error': str(e)}, status=400)

        try:
            response = get(url)
            response.raise_for_status()  # Проверка на успешный статус ответа
            data = load_yaml(response.content, Loader=Loader)
        except Exception as e:
            return JsonResponse(
                {'Status': False,
                 'Error': f'Ошибка загрузки или парсинга данных: {e}'},
                status=400
            )

        # Получение или создание магазина
        shop_name = data.get('shop')
        if not shop_name:
            return JsonResponse(
                {'Status': False,
                 'Error': 'В файле отсутствует название магазина'},
                status=400
            )
        shop, _ = Shop.objects.get_or_create(name=shop_name,
                                             user_id=request.user.id)

        # Обработка категорий
        for category in data.get('categories', []):
            cat_id = category.get('id')
            cat_name = category.get('name')
            if not cat_id or not cat_name:
                continue  # Пропускаем некорректные категории
            category_object, _ = Category.objects.get_or_create(
                id=cat_id, name=cat_name
            )
            category_object.shops.add(shop)
            category_object.save()

        # Очистка старых товаров магазина
        ProductInfo.objects.filter(shop=shop).delete()

        # Обработка товаров
        for item in data.get('goods', []):
            name = item.get('name')
            category_id = item.get('category')
            full_name = item.get('full_name')
            external_id = item.get('id')
            parameters = item.get('parameters', {})

            if not all([name, category_id, full_name, external_id]):
                continue  # Пропускаем товары с неполными данными

            # Получение или создание продукта и категории
            product_category, _ = Category.objects.get_or_create(id=category_id)
            product, _ = Product.objects.get_or_create(
                name=name,
                category=product_category
            )

            # Создание ProductInfo
            product_info_data = {
                'external_id': external_id,
                'product': product,
                'shop': shop,
                'full_name': full_name,
                'quantity': item.get('quantity'),
                'retail_price': item.get('retail_price'),
                'wholesale_price': item.get('wholesale_price'),
                'sell_up_to': item.get('sell_up_to'),
            }

            product_info = ProductInfo.objects.create(**product_info_data)

            # Создание параметров товара
            for param_name, param_value in parameters.items():
                parameter_object, _ = Parameter.objects.get_or_create(
                    name=param_name)
                ProductParameter.objects.create(
                    product_info=product_info,
                    parameter=parameter_object,
                    value=param_value
                )

        return JsonResponse({'Status': True})
'''




class PartnerUpdate(APIView):
    """
    Класс для обновления прайса от поставщика

    Поддерживает:
    1. Загрузку по URL (http/https)
    2. Загрузку из локальной папки (file:// или путь)
    3. Прямую загрузку файла через multipart/form-data
    """
    permission_classes = [IsAuthenticated, IsShopOwner]

    def post(self, request, *args, **kwargs):
        """
        Обработка POST запроса для обновления прайса

        Параметры:
        - url: URL YAML файла (http/https или file://)
        - file_path: Путь к локальному файлу
        - file: Загруженный файл (multipart/form-data)
        """
        # Получаем данные из запроса
        url = request.data.get('url')
        file_path = request.data.get('file_path')
        uploaded_file = request.FILES.get('file')

        try:
            # Определяем источник данных и загружаем контент
            yaml_content = self._load_content(url, file_path, uploaded_file)

            # Парсим YAML
            data = YAMLProcessor.parse_yaml(yaml_content)

            # Валидируем через сериализатор
            serializer = YAMLImportSerializer(data=data)
            serializer.is_valid(raise_exception=True)

            # Обрабатываем данные
            result = YAMLProcessor.process_data(data, request.user)

            return JsonResponse({
                'Status': True,
                'Message': 'Данные успешно обновлены',
                'Details': result
            })

        except Exception as e:
            return self._handle_error(e)

    def _load_content(self, url, file_path, uploaded_file):
        """Загрузка контента из различных источников"""
        # Вариант 1: Загруженный файл
        if uploaded_file:
            if not uploaded_file.name.lower().endswith(('.yaml', '.yml')):
                raise ValidationError('Файл должен быть в формате YAML (.yaml или .yml)')
            return uploaded_file.read()

        # Вариант 2: URL (http/https)
        elif url and (url.startswith('http://') or url.startswith('https://')):
            return FileLoader.download_from_url(url)

        # Вариант 3: Локальный путь (file:// или абсолютный/относительный путь)
        elif url and url.startswith('file://'):
            actual_path = url[7:]  # Убираем 'file://'
            return FileLoader.read_local_file(actual_path)

        # Вариант 4: Прямой путь к файлу
        elif file_path:
            return FileLoader.read_local_file(file_path)

        # Вариант 5: URL без протокола (предполагаем локальный файл)
        elif url:
            return FileLoader.read_local_file(url)

        else:
            raise ValidationError(
                'Не указаны необходимые аргументы. '
                'Используйте один из параметров: url, file_path или загрузите файл'
            )

    def _handle_error(self, error):
        """Обработка ошибок"""
        error_messages = {
            ValidationError: lambda e: JsonResponse(
                {'Status': False, 'Error': f'Ошибка валидации: {str(e)}'},
                status=400
            ),
            FileNotFoundError: lambda e: JsonResponse(
                {'Status': False, 'Error': f'Файл не найден: {str(e)}'},
                status=404
            ),
            PermissionError: lambda e: JsonResponse(
                {'Status': False, 'Error': f'Ошибка доступа: {str(e)}'},
                status=403
            ),
            yaml.YAMLError: lambda e: JsonResponse(
                {'Status': False, 'Error': f'Ошибка парсинга YAML: {str(e)}'},
                status=400
            ),
            RequestException: lambda e: JsonResponse(
                {'Status': False, 'Error': f'Ошибка загрузки по URL: {str(e)}'},
                status=400
            ),
        }

        for error_type, handler in error_messages.items():
            if isinstance(error, error_type):
                return handler(error)

        # Общая ошибка
        return JsonResponse(
            {'Status': False, 'Error': f'Внутренняя ошибка: {str(error)}'},
            status=500
        )

