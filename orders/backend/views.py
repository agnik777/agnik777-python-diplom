# views.py
import yaml
from datetime import timedelta, datetime

from django.http import JsonResponse
from django.utils import timezone
from rest_framework.pagination import PageNumberPagination

from rest_framework.views import APIView
from .models import Shop, ConfirmEmailToken, ProductInfo
from requests.exceptions import RequestException
from rest_framework import generics, status, filters
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .permissions import IsShopOwner
from .serializers import YAMLImportSerializer, UserRegistrationSerializer, UserLoginSerializer, ShopSerializer, \
    ShopCategorySerializer, ProductInfoSerializer, ProductSearchSerializer
from .yaml_processor import YAMLProcessor
from .file_loader import FileLoader
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models import Q


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



class PartnerUpdate(APIView):
    """
    Класс для обновления прайса от поставщика
    """
    permission_classes = [IsAuthenticated, IsShopOwner]

    def post(self, request, *args, **kwargs):
        """
        Обработка POST запроса для обновления прайса
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

            # Валидируем структуру YAML (без проверки существования в БД)
            serializer = YAMLImportSerializer(data=data)
            serializer.is_valid(raise_exception=True)

            # Обрабатываем данные (создаем категории и товары)
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


class ShopListView(generics.ListAPIView):
    """
    API для получения списка активных магазинов
    GET /api/shops/
    """
    queryset = Shop.objects.filter(permissions_order=True).order_by('name')
    serializer_class = ShopSerializer


class ShopCategoriesView(generics.ListAPIView):
    """
    API для получения магазинов с их категориями
    GET /api/shops/categories/
    Ответ: сначала магазины, внутри каждого - список категорий
    """
    serializer_class = ShopCategorySerializer

    def get_queryset(self):
        """Получаем магазины с разрешенными заказами и их категории"""
        queryset = Shop.objects.filter(
            permissions_order=True
        ).prefetch_related(
            'categories'
        ).order_by('name')

        # Фильтрация по категории (опционально)
        category_id = self.request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(categories__id=category_id)

        # Фильтрация по названию магазина (опционально)
        shop_name = self.request.query_params.get('shop_name')
        if shop_name:
            queryset = queryset.filter(name__icontains=shop_name)

        return queryset.distinct()


class ProductSearchView(generics.ListAPIView):
    """
    API для поиска товаров по параметрам
    GET /api/products/search/

    Параметры запроса:
    - shop_name: название магазина (частичное совпадение)
    - category_name: название категории (частичное совпадение)
    - product_name: название товара (частичное совпадение)
    - min_price: минимальная розничная цена
    - max_price: максимальная розничная цена
    - in_stock_only: только товары в наличии (quantity > 0)
    - page: номер страницы (пагинация)
    """
    serializer_class = ProductInfoSerializer
    pagination_class = PageNumberPagination

    def get_queryset(self):
        """
        Возвращает отфильтрованный queryset товаров.
        """
        # Получаем и валидируем параметры запроса
        serializer = ProductSearchSerializer(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Базовый запрос с оптимизацией (select_related и prefetch_related)
        queryset = ProductInfo.objects.select_related(
            'shop', 'product', 'product__category'
        ).prefetch_related('product_parameters__parameter').filter(
            shop__permissions_order=True
        )

        # Применяем фильтры
        queryset = self.apply_filters(queryset, data)

        # Фильтруем просроченные товары
        queryset = self.exclude_expired_products(queryset)

        # Фильтр по наличию
        if data.get('in_stock_only'):
            queryset = queryset.filter(quantity__gt=0)

        return queryset.order_by('-id')

    def apply_filters(self, queryset, filters_data):
        """Применение фильтров к queryset"""
        shop_name = filters_data.get('shop_name')
        if shop_name:
            queryset = queryset.filter(shop__name__icontains=shop_name)

        category_name = filters_data.get('category_name')
        if category_name:
            queryset = queryset.filter(product__category__name__icontains=category_name)

        product_name = filters_data.get('product_name')
        if product_name:
            queryset = queryset.filter(
                Q(full_name__icontains=product_name) |
                Q(product__name__icontains=product_name)
            )

        min_price = filters_data.get('min_price')
        max_price = filters_data.get('max_price')

        if min_price is not None:
            queryset = queryset.filter(retail_price__gte=min_price)

        if max_price is not None:
            queryset = queryset.filter(retail_price__lte=max_price)

        return queryset

    def exclude_expired_products(self, queryset):
        """
        Исключает просроченные товары.
        Обрабатывает поле sell_up_to в формате YYYY-mm-dd или dd.mm.YYYY
        """
        today = timezone.now().date()

        # Создаем список для условий исключения
        exclude_conditions = Q()

        # Обрабатываем каждый товар
        for product_info in queryset:
            sell_up_to = product_info.sell_up_to

            # Пропускаем пустые значения
            if not sell_up_to or sell_up_to.strip() == '':
                continue

            try:
                # Пробуем разные форматы даты
                date_obj = None

                # Формат YYYY-mm-dd
                if '-' in sell_up_to and len(sell_up_to.split('-')[0]) == 4:
                    try:
                        date_obj = datetime.strptime(sell_up_to, '%Y-%m-%d').date()
                    except ValueError:
                        pass

                # Формат dd.mm.YYYY
                if not date_obj and '.' in sell_up_to:
                    try:
                        date_obj = datetime.strptime(sell_up_to, '%d.%m.%Y').date()
                    except ValueError:
                        pass

                # Если дата определена и просрочена, добавляем в условия исключения
                if date_obj and date_obj < today:
                    exclude_conditions |= Q(id=product_info.id)

            except (ValueError, AttributeError):
                # Если формат даты некорректный, пропускаем этот товар
                continue

        # Исключаем просроченные товары
        return queryset.exclude(exclude_conditions)

    def list(self, request, *args, **kwargs):
        """Переопределяем для добавления метаданных"""
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

