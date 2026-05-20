# backend/views.py
import yaml
import logging
from datetime import timedelta

from django.http import JsonResponse, Http404
from django.utils import timezone
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_view, extend_schema, \
    OpenApiParameter, OpenApiExample, inline_serializer, OpenApiResponse

from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework import generics, status, permissions, viewsets, parsers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, \
    IsAuthenticatedOrReadOnly
from rest_framework.authtoken.models import Token
from requests.exceptions import RequestException

from .models import (
    Shop, ConfirmEmailToken, ProductInfo, Order, Contact, OrderItem,
    Phone, ProductImage
)
from .serializers import (
    YAMLImportSerializer, UserRegistrationSerializer, UserLoginSerializer,
    ShopSerializer, ShopCategorySerializer, ProductInfoSerializer,
    ProductSearchSerializer, OrderSerializer, AddToCartSerializer,
    OrderItemSerializer, UpdateCartItemSerializer, ContactSerializer,
    PhoneSerializer, OrderCreateSerializer, OrderDetailSerializer,
    OrderConfirmSerializer, OrderListSerializer, ShopPermissionSerializer,
    ShopOrderListSerializer, AvatarSerializer, ProductImageUploadSerializer,
    ProductImageUpdateSerializer, ProductImageBulkUploadSerializer,
    ProductImageListSerializer
)
from .utils import ProductUtils
from .yaml_processor import YAMLProcessor
from .file_loader import FileLoader
from .permissions import IsShopOwner
from .throttles import (
    RegisterThrottle, LoginThrottle,
    ConfirmEmailThrottle, PartnerUpdateThrottle,
)
from .tasks import (
    send_confirmation_email_task, send_order_created_email_task,
    send_all_shop_owner_emails_task, send_order_confirmed_email_task,
    send_order_status_changed_email_task
)
from .image_tasks import generate_product_thumbnails, bulk_generate_thumbnails


logger = logging.getLogger(__name__)


@extend_schema(
    summary="Завершение авторизации через Яндекс",
    description="Возвращает токен и данные пользователя после успешной "
                "социальной авторизации.",
    responses={
        200: OpenApiResponse(
            response=inline_serializer(
                name="SocialAuthSuccess",
                fields={
                    "token": OpenApiTypes.STR,
                    "user_id": OpenApiTypes.INT,
                    "email": OpenApiTypes.STR,
                    "detail": OpenApiTypes.STR,
                },
            ),
        ),
        400: OpenApiResponse(description="Авторизация не завершена"),
    },
)
class SocialAuthCompleteView(APIView):
    """
    View, которая возвращает токен после успешной авторизации через соцсеть.
    URL: /api/social-auth/complete/
    Метод: GET
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # 1️⃣ Проверяем, авторизован ли пользователь
        if not request.user.is_authenticated:
            return Response(
                {"error": "Пользователь не авторизован"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2️⃣ Получаем или создаем токен
        token, created = Token.objects.get_or_create(user=request.user)

        # 3️⃣ Возвращаем токен и данные пользователя
        return Response({
            "token": token.key,
            "user_id": request.user.pk,
            "email": request.user.email,
            "detail": "Авторизация через Яндекс успешна."
        }, status=status.HTTP_200_OK)


@extend_schema(
    summary="Ошибка авторизации через соцсеть",
    description="Возвращает описание ошибки, произошедшей при авторизации "
                "через соцсеть.",
    parameters=[
        OpenApiParameter(
            name='error',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Описание ошибки, возвращаемое провайдером',
        ),
    ],
    responses={
        400: OpenApiResponse(
            response=inline_serializer(
                name="SocialAuthError",
                fields={
                    "error": OpenApiTypes.STR,
                },
            ),
            description="Ошибка авторизации"
        ),
    },
    tags=["Auth"],
)
class SocialAuthErrorView(APIView):
    """
    View для отображения ошибки авторизации.
    URL: /api/social-auth/error/
    """
    permission_classes = [AllowAny]

    def get(self, request):
        error = request.GET.get('error', 'Неизвестная ошибка')
        logger.warning(f"Social auth error: {error}")

        return Response(
            {
                "error": error,
                "detail": "Попробуйте авторизоваться снова. "
                          "Если ошибка повторяется, обратитесь в поддержку."
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class BaseUserDataView(generics.GenericAPIView):
    """
    Базовый класс для API, работающих с личными данными пользователя
    (телефон, контакты). Проверяет права доступа.
    """
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """Проверяем, что пользователь - покупатель"""
        if self.request.user.is_authenticated and hasattr(self.request.user,
                                                          'type'):
            if self.request.user.type != 'buyer':
                self.permission_denied(
                    self.request,
                    message="Только покупатели могут работать с данными"
                )
        return super().get_permissions()


@extend_schema(
    summary="Регистрация нового пользователя",
    description="Создаёт нового пользователя и отправляет токен подтверждения "
                "на email.",
    request=UserRegistrationSerializer,
    responses={
        201: OpenApiResponse(description="Пользователь создан, "
                                         "письмо отправлено"),
        400: OpenApiResponse(description="Невалидные данные"),
    },
    tags=["Auth"],
)
class UserRegistrationView(generics.CreateAPIView):
    """Регистрация нового пользователя"""
    serializer_class = UserRegistrationSerializer
    throttle_classes = [RegisterThrottle]

    def perform_create(self, serializer):
        user = serializer.save()
        token = ConfirmEmailToken.objects.create(user=user)

        # используем Celery задачу
        send_confirmation_email_task.delay(user.id, token.key)


@extend_schema(
    summary="Подтверждение email по токену",
    description="Активирует аккаунт пользователя по одноразовому токену "
                "(24 часа действителен).",
    parameters=[
        OpenApiParameter(
            name='token_key',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
            description='Токен подтверждения, отправленный на email',
            required=True,
        ),
    ],
    responses={
        200: OpenApiResponse(description="Email подтверждён"),
        400: OpenApiResponse(description="Токен устарел или неверен"),
    },
    tags=["Auth"],
)
class ConfirmEmailView(APIView):
    """Подтверждение email по токену"""
    throttle_classes = [ConfirmEmailThrottle]

    def get(self, request, token_key):
        try:
            token = ConfirmEmailToken.objects.get(key=token_key)
            if timezone.now() - token.created_at > timedelta(hours=24):
                token.delete()
                return Response(
                    {'detail': 'Токен устарел.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user = token.user
            user.is_active = True
            user.save(using=user._state.db)  # Явно указываем базу
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


@extend_schema(
    summary="Вход в систему",
    description="Аутентификация пользователя по email и паролю. "
                "Возвращает токен.",
    request=UserLoginSerializer,
    responses={
        200: OpenApiResponse(
            response=inline_serializer(
                name="LoginSuccess",
                fields={
                    "token": OpenApiTypes.STR,
                    "user_id": OpenApiTypes.INT,
                    "email": OpenApiTypes.STR,
                },
            ),
            description="Успешный вход",
        ),
        403: OpenApiResponse(description="Аккаунт не активирован"),
        400: OpenApiResponse(description="Неверные учётные данные"),
    },
    tags=["Auth"],
)
class UserLoginView(generics.GenericAPIView):
    """Вход пользователя в систему"""
    serializer_class = UserLoginSerializer
    throttle_classes = [LoginThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        if not user.is_active:
            return Response(
                {'detail': 'Аккаунт не активирован. '
                           'Проверьте вашу почту для подтверждения.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Обновляем логин-статистику
        user.last_login_time = timezone.now()
        user.login_count += 1
        user.save(update_fields=['last_login_time', 'login_count'])

        # Получаем или создаем токен для пользователя
        token, created = Token.objects.get_or_create(user=user)

        return Response({
            'token': token.key,
            'user_id': user.pk,
            'email': user.email
        }, status=status.HTTP_200_OK)


@extend_schema(
    summary="Выход из системы",
    description="Удаляет токен аутентификации пользователя, "
                "делая его недействительным.",
    responses={
        200: OpenApiResponse(description="Успешный выход"),
        500: OpenApiResponse(description="Ошибка при выходе"),
    },
    tags=["Auth"],
)
class LogoutView(APIView):
    """
    API для выхода пользователя из системы (удаление токена).
    URL: /api/logout/
    Метод: POST
    """
    # Доступ только для аутентифицированных пользователей
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Обрабатывает запрос на выход.
        Удаляет токен аутентификации пользователя, делая его недействительным.
        """
        try:
            # Получаем и удаляем токен пользователя
            request.user.auth_token.delete()
            return Response(
                {"detail": "Вы успешно вышли из системы."},
                status=status.HTTP_200_OK
            )
        except (AttributeError, Token.DoesNotExist):
            # Если что-то пошло не так (например, у пользователя нет токена)
            return Response(
                {"detail": "Ошибка при выходе из системы."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema_view(
    post=extend_schema(
        summary="Обновление прайса магазина через YAML",
        description="""
        Загружает прайс-лист в формате YAML от поставщика. Поддерживает:
        - Загрузку по URL (http/https)
        - Загрузку локального файла (file:// или абсолютный путь)
        - Загрузку через multipart/form-data (файл)
        """,
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'url': {'type': 'string',
                            'description': 'URL YAML-файла'},
                    'file_path': {'type': 'string',
                                  'description': 'Путь к локальному файлу'},
                    'file': {'type': 'string', 'format': 'binary',
                             'description': 'Загружаемый YAML-файл'},
                },
                'required': ['url', 'file_path', 'file'],
                'example': {
                    'url': 'https://example.com/prices.yaml',
                    'file_path': '/data/prices.yaml',
                    'file': 'file: prices.yaml'
                }
            }
        },
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="PartnerUpdateSuccess",
                    fields={
                        'Status': OpenApiTypes.BOOL,
                        'Message': OpenApiTypes.STR,
                        'Details': OpenApiTypes.OBJECT,
                    },
                ),
                description="Успешное обновление",
            ),
            400: OpenApiResponse(description="Ошибка валидации или формата"),
            403: OpenApiResponse(description="Нет прав доступа"),
            404: OpenApiResponse(description="Файл не найден"),
            500: OpenApiResponse(description="Внутренняя ошибка сервера"),
        },
        tags=["Partner"],
        examples=[
            OpenApiExample(
                "Пример запроса с файлом",
                summary="Загрузка через файл",
                value={
                    "file": "file: prices.yaml"
                },
                request_only=True,
            ),
            OpenApiExample(
                "Пример ответа успеха",
                summary="Успешный ответ",
                value={
                    "Status": True,
                    "Message": "Данные успешно обновлены",
                    "Details": {
                        "categories_created": 2,
                        "products_created": 15,
                        "products_updated": 3
                    }
                },
                response_only=True,
            ),
        ],
    )
)
class PartnerUpdate(APIView):
    """Класс для обновления прайса от поставщика"""
    permission_classes = [IsAuthenticated, IsShopOwner]
    throttle_classes = [PartnerUpdateThrottle]

    def post(self, request, *args, **kwargs):
        """Обработка POST запроса для обновления прайса"""
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
                raise ValidationError('Файл должен быть в формате YAML '
                                      '(.yaml или .yml)')
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
                'Используйте один из параметров: '
                'url, file_path или загрузите файл'
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
                {'Status': False,
                 'Error': f'Ошибка парсинга YAML: {str(e)}'},
                status=400
            ),
            RequestException: lambda e: JsonResponse(
                {'Status': False,
                 'Error': f'Ошибка загрузки по URL: {str(e)}'},
                status=400
            ),
        }

        for error_type, handler in error_messages.items():
            if isinstance(error, error_type):
                return handler(error)

        # Общая ошибка
        return JsonResponse(
            {'Status': False,
             'Error': f'Внутренняя ошибка: {str(error)}'},
            status=500
        )


@extend_schema_view(
    get=extend_schema(
        summary="Список магазинов",
        description="Возвращает список активных магазинов.",
        responses={200: ShopSerializer(many=True)},
        tags=['Магазины'],
    )
)
class ShopListView(generics.ListAPIView):
    """
    API для получения списка активных магазинов
    GET /api/shops/
    """
    queryset = Shop.objects.filter(permissions_order=True).order_by('name')
    serializer_class = ShopSerializer
    permission_classes = [permissions.AllowAny]


@extend_schema_view(
    get=extend_schema(
        summary="Магазины с категориями",
        description="Возвращает магазины со списком их категорий.",
        parameters=[
            OpenApiParameter(
                name='category_id',
                type=int,
                location=OpenApiParameter.QUERY,
                description='Фильтр по ID категории',
                required=False,
            ),
            OpenApiParameter(
                name='shop_name',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Фильтр по названию магазина (частичное совпадение)',
                required=False,
            ),
        ],
        responses={200: ShopCategorySerializer(many=True)},
        tags=['Магазины'],
    )
)
class ShopCategoriesView(generics.ListAPIView):
    """
    API для получения магазинов с их категориями
    GET /api/shops/categories/
    Ответ: сначала магазины, внутри каждого - список категорий
    """
    serializer_class = ShopCategorySerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        """Получаем магазины с разрешенными заказами и их категории"""
        queryset = Shop.objects.filter(
            permissions_order=True
        ).prefetch_related('categories').order_by('name')

        # Фильтрация по категории (опционально)
        category_id = self.request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(categories__id=category_id)

        # Фильтрация по названию магазина (опционально)
        shop_name = self.request.query_params.get('shop_name')
        if shop_name:
            queryset = queryset.filter(name__icontains=shop_name)

        # Явное кэширование для параметризованных запросов
        # cacheops автоматически инвалидирует кэш при изменении данных
        return queryset.distinct().cache()

    def list(self, request, *args, **kwargs):
        """Добавляем заголовки кэширования в ответ"""
        response = super().list(request, *args, **kwargs)
        response['X-Cache-Enabled'] = 'true'
        response['X-Cache-TTL'] = '1800'  # 30 минут
        return response


@extend_schema_view(
    get=extend_schema(
        summary="Поиск товаров",
        description="Поиск товаров с фильтрацией по магазину, категории, "
                    "названию, цене и наличию.",
        parameters=[
            OpenApiParameter(name='shop_name', type=str,
                             location=OpenApiParameter.QUERY,
                             description='Название магазина '
                                         '(частичное совпадение)',
                             required=False),
            OpenApiParameter(name='category_name', type=str,
                             location=OpenApiParameter.QUERY,
                             description='Название категории '
                                         '(частичное совпадение)',
                             required=False),
            OpenApiParameter(name='product_name', type=str,
                             location=OpenApiParameter.QUERY,
                             description='Название товара '
                                         '(частичное совпадение)',
                             required=False),
            OpenApiParameter(name='min_price', type=float,
                             location=OpenApiParameter.QUERY,
                             description='Минимальная розничная цена',
                             required=False),
            OpenApiParameter(name='max_price', type=float,
                             location=OpenApiParameter.QUERY,
                             description='Максимальная розничная цена',
                             required=False),
            OpenApiParameter(name='in_stock_only', type=bool,
                             location=OpenApiParameter.QUERY,
                             description='Только товары в наличии',
                             required=False),
            OpenApiParameter(name='page', type=int,
                             location=OpenApiParameter.QUERY,
                             description='Номер страницы (пагинация)',
                             required=False),
        ],
        responses={200: ProductInfoSerializer(many=True)},
        tags=['products'],
    )
)
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
    permission_classes = [permissions.AllowAny]

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
        queryset = ProductUtils.exclude_expired_products(queryset)

        # Фильтр по наличию
        if data.get('in_stock_only'):
            queryset = queryset.filter(quantity__gt=0)

        # Если есть параметры фильтрации — кэшируем с ключом по параметрам
        # cacheops сам сгенерирует ключ на основе SQL и параметров
        if any([
            data.get('shop_name'),
            data.get('category_name'),
            data.get('product_name'),
            data.get('min_price') is not None,
            data.get('max_price') is not None,
            data.get('in_stock_only'),
        ]):
            queryset = queryset.cache()

        return queryset.order_by('-id')

    def apply_filters(self, queryset, filters_data):
        """Применение фильтров к queryset"""
        shop_name = filters_data.get('shop_name')
        if shop_name:
            queryset = queryset.filter(shop__name__icontains=shop_name)

        category_name = filters_data.get('category_name')
        if category_name:
            queryset = queryset.filter(
                product__category__name__icontains=category_name)

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

    def list(self, request, *args, **kwargs):
        """Переопределяем для добавления метаданных и заголовков кэширования"""
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
        else:
            serializer = self.get_serializer(queryset, many=True)
            response = Response(serializer.data)

        # Добавляем заголовки кэширования
        response['X-Cache-Enabled'] = 'true'
        response['X-Cache-TTL'] = '600'  # 10 минут
        return response


@extend_schema_view(
    get=extend_schema(
        summary="Детальная информация о товаре",
        description="Возвращает полную информацию о товаре по ID.",
        responses={200: ProductInfoSerializer,
                   404: {'description': 'Товар не найден'}},
        tags=['products'],
    )
)
class ProductDetailView(generics.RetrieveAPIView):
    """
    API для получения детальной информации о товаре
    GET /api/products/{id}/
    """
    serializer_class = ProductInfoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        """Используем утилиту для получения доступных товаров с оптимизацией."""
        return ProductUtils.get_available_products_queryset()


@extend_schema_view(
    get=extend_schema(
        summary='Просмотр корзины',
        description='Возвращает содержимое корзины текущего пользователя.',
        responses={200: OrderSerializer},
        tags=['Cart'],
    ),
    post=extend_schema(
        summary='Добавление товара в корзину',
        description='Добавляет указанный товар в корзину пользователя.',
        request=AddToCartSerializer,
        responses={
            200: OpenApiExample(
                'Success',
                value={
                    'message': 'Товар добавлен в корзину',
                    'item': {'id': 1, 'product': 42, 'quantity': 1}
                }
            ),
            400: OpenApiExample(
                'Error',
                value={'error': 'Товар недоступен для заказа'}
            ),
            404: OpenApiExample(
                'Not Found',
                value={'error': 'Товар не найден'}
            ),
        },
        tags=['Cart'],
    ),
)
class CartView(BaseUserDataView):
    """
    API для работы с корзиной
    GET: Просмотр содержимого корзины
    POST: Добавление товара в корзину
    """
    def get_basket_order(self, user):
        """Получает или создает корзину пользователя"""
        # Ищем активную корзину
        basket = Order.objects.filter(
            contact__user=user,
            status='basket'
        ).first()

        # Если корзины нет, создаем новую
        if not basket:
            # Получаем последний контакт пользователя
            contact = user.contacts.last()

            if not contact:
                # Если контактов нет — создаем дефолтный
                contact = Contact.objects.create(
                    user=user,
                    city='Не указан',
                    street='Не указана',
                    house='',
                    structure='',
                    apartment=''
                )

            basket = Order.objects.create(
                contact=contact,
                status='basket'
            )

        return basket

    def get(self, request):
        """Просмотр содержимого корзины"""
        basket = self.get_basket_order(request.user)
        serializer = OrderSerializer(basket)
        return Response(serializer.data)

    def post(self, request):
        """Добавление товара в корзину"""
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_id = serializer.validated_data['product_id']

        try:
            product = ProductInfo.objects.get(id=product_id)
        except ProductInfo.DoesNotExist:
            return Response(
                {'error': 'Товар не найден'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Проверка доступности товара
        if not product.is_available():
            return Response(
                {'error': 'Товар недоступен для заказа'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Получаем корзину
        basket = self.get_basket_order(request.user)

        # Проверяем, есть ли уже такой товар в корзине
        order_item = OrderItem.objects.filter(
            order=basket,
            product=product
        ).first()

        if order_item:
            # Увеличиваем количество на 1
            if order_item.quantity < product.get_available_quantity():
                order_item.quantity += 1
                order_item.save()
                message = 'Количество товара увеличено'
            else:
                return Response(
                    {'error': f'Доступно только {product.quantity} '
                              f'единиц товара'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # Добавляем новый товар
            if product.quantity >= 1:
                order_item = OrderItem.objects.create(
                    order=basket,
                    product=product,
                    quantity=1
                )
                message = 'Товар добавлен в корзину'
            else:
                return Response(
                    {'error': 'Товар отсутствует в наличии'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response({
            'message': message,
            'item': OrderItemSerializer(order_item).data
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    put=extend_schema(
        summary='Изменение количества товара в корзине',
        description='Обновляет количество указанного товара в корзине.',
        request=UpdateCartItemSerializer,
        parameters=[
            OpenApiParameter(
                name='item_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='ID позиции в корзине',
            ),
        ],
        responses={
            200: OpenApiExample(
                'Success',
                value={
                    'message': 'Количество товара обновлено',
                    'item': {'id': 1, 'product': 42, 'quantity': 3}
                }
            ),
            400: OpenApiExample(
                'Error',
                value={'error': 'Доступно только 5 единиц товара'}
            ),
        },
        tags=['Cart'],
    ),
    delete=extend_schema(
        summary='Удаление товара из корзины',
        description='Удаляет указанный товар из корзины пользователя.',
        parameters=[
            OpenApiParameter(
                name='item_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='ID позиции в корзине',
            ),
        ],
        responses={
            200: OpenApiExample(
                'Success',
                value={'message': 'Товар удален из корзины'}
            ),
        },
        tags=['Cart'],
    ),
)
class CartItemDetailView(BaseUserDataView):
    """
    API для работы с конкретным товаром в корзине
    PUT: Изменение количества товара
    DELETE: Удаление товара из корзины
    """

    def get_object(self, item_id):
        """Получает товар из корзины пользователя"""
        try:
            return OrderItem.objects.get(
                id=item_id,
                order__contact__user=self.request.user,
                order__status='basket'
            )
        except OrderItem.DoesNotExist:
            raise Http404

    def put(self, request, item_id):
        """Изменение количества товара в корзине"""
        order_item = self.get_object(item_id)

        serializer = UpdateCartItemSerializer(
            order_item,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)

        # Проверка доступного количества
        max_available = order_item.product.get_available_quantity()
        new_quantity = serializer.validated_data.get(
            'quantity', order_item.quantity)

        if new_quantity > max_available:
            return Response(
                {'error': f'Доступно только {max_available} '
                          f'единиц товара'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer.save()

        return Response({
            'message': 'Количество товара обновлено',
            'item': OrderItemSerializer(order_item).data
        })

    def delete(self, request, item_id):
        """Удаление товара из корзины"""
        order_item = self.get_object(item_id)
        order_item.delete()

        return Response(
            {'message': 'Товар удален из корзины'},
            status=status.HTTP_200_OK
        )


@extend_schema_view(
    post=extend_schema(
        summary='Создание заказа из корзины',
        description=(
            'Переводит корзину в статус "new" и создаёт заказ. '
            'Отправляются уведомления на email.'
        ),
        request=OrderCreateSerializer,
        responses={
            201: OpenApiExample(
                'Order Created',
                value={
                    'detail': 'Заказ успешно создан',
                    'order_id': 1,
                    'status': 'new',
                    'order': {
                        'id': 1,
                        'status': 'new',
                        'contact': 1,
                        'items': [],
                        'total': 1500.00
                    }
                }
            ),
            500: OpenApiExample(
                'Error',
                value={'detail': 'Ошибка при создании заказа: ...'}
            ),
        },
        tags=['Orders'],
    ),
)
class OrderCreateView(generics.GenericAPIView):
    """Создание заказа из корзины"""
    permission_classes = [IsAuthenticated]
    serializer_class = OrderCreateSerializer

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        basket = serializer.validated_data['basket']
        contact_id = serializer.validated_data['contact_id']
        phone = serializer.validated_data['phone']

        try:
            contact = Contact.objects.get(id=contact_id, user=request.user)

            # Преобразуем корзину в заказ
            basket.status = 'new'
            basket.contact = contact
            basket.save()

            # Отправляем письмо покупателю
            send_order_created_email_task.delay(request.user.id, basket.id)

            # Отправляем письма владельцам магазинов
            send_all_shop_owner_emails_task.delay(basket.id)

            return Response({
                'detail': 'Заказ успешно создан',
                'order_id': basket.id,
                'status': basket.status,
                'order': OrderDetailSerializer(basket).data
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {'detail': f'Ошибка при создании заказа: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema_view(
    post=extend_schema(
        summary='Подтверждение заказа',
        description=(
            'Переводит заказ в статус "confirmed". '
            'Отправляются уведомления.'
        ),
        request=OrderConfirmSerializer,
        responses={
            200: OpenApiExample(
                'Order Confirmed',
                value={
                    'detail': 'Заказ успешно подтвержден',
                    'order_id': 1,
                    'status': 'confirmed',
                    'order': {
                        'id': 1,
                        'status': 'confirmed',
                        'contact': 1,
                        'items': [],
                        'total': 1500.00
                    }
                }
            ),
            404: OpenApiExample(
                'Not Found',
                value={'detail': 'Заказ не найден'}
            ),
        },
        tags=['Orders'],
    ),
)
class OrderConfirmView(generics.GenericAPIView):
    """Подтверждение заказа"""
    permission_classes = [IsAuthenticated]
    serializer_class = OrderConfirmSerializer

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        order_id = serializer.validated_data['order_id']

        try:
            order = Order.objects.get(id=order_id, contact__user=request.user)

            previous_status = order.status
            order.status = 'confirmed'
            order.save()

            # Отправляем письмо о подтверждении
            send_order_confirmed_email_task.delay(request.user.id, order.id)

            # Отправляем письмо об изменении статуса
            send_order_status_changed_email_task.delay(
                request.user.id, order.id, previous_status
            )

            # Отправляем письма владельцам магазинов
            send_all_shop_owner_emails_task.delay(order.id)

            return Response({
                'detail': 'Заказ успешно подтвержден',
                'order_id': order.id,
                'status': order.status,
                'order': OrderDetailSerializer(order).data
            }, status=status.HTTP_200_OK)
        except Order.DoesNotExist:
            return Response(
                {'detail': 'Заказ не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'detail': f'Ошибка при подтверждении заказа: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema_view(
    get=extend_schema(
        summary='Список заказов пользователя',
        description='Возвращает все заказы текущего пользователя, '
                    'исключая корзину (статус basket). '
                    'Сортировка по дате (сначала новые).',
        responses={
            200: OrderListSerializer(many=True),
            401: OpenApiResponse(description='Не авторизован'),
        },
        tags=['Заказы'],
    )
)
class OrderListView(generics.ListAPIView):
    """Список заказов пользователя"""
    permission_classes = [IsAuthenticated]
    serializer_class = OrderListSerializer

    def get_queryset(self):
        return Order.objects.filter(
            contact__user=self.request.user
        ).exclude(status='basket').order_by('-dt')


@extend_schema_view(
    get=extend_schema(
        summary='Детальная информация о заказе',
        description='Возвращает полную информацию о заказе, '
                    'включая список товаров, контакт и статус.',
        parameters=[
            OpenApiParameter(
                name='pk',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='ID заказа',
            ),
        ],
        responses={
            200: OrderDetailSerializer,
            401: OpenApiResponse(description='Не авторизован'),
            404: OpenApiResponse(description='Заказ не найден'),
        },
        tags=['Заказы'],
    )
)
class OrderDetailView(generics.RetrieveAPIView):
    """Детальная информация о заказе"""
    permission_classes = [IsAuthenticated]
    serializer_class = OrderDetailSerializer

    def get_queryset(self):
        return Order.objects.filter(
            contact__user=self.request.user
        ).exclude(status='basket')


@extend_schema(
    summary="Получить или обновить телефон пользователя",
    description="GET: возвращает текущий телефон. "
                "POST: создаёт или обновляет телефон.",
    request=PhoneSerializer,
    responses={
        200: inline_serializer(
            name='PhoneResponse',
            fields={
                'detail': OpenApiTypes.STR,
                'phone': PhoneSerializer()
            }
        ),
        404: inline_serializer(
            name='PhoneNotFound',
            fields={'detail': OpenApiTypes.STR}
        )
    },
    methods=['GET', 'POST'],
    tags=['User Profile']
)
class PhoneView(generics.GenericAPIView):
    """
    API для работы с телефоном пользователя
    GET: Получение текущего телефона
    POST: Создание/обновление телефона
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PhoneSerializer

    def get(self, request):
        """Получение телефона пользователя"""
        try:
            phone = Phone.objects.get(user=request.user)
            serializer = self.get_serializer(phone)
            return Response(serializer.data)
        except Phone.DoesNotExist:
            return Response(
                {'detail': 'Телефон не указан'},
                status=status.HTTP_404_NOT_FOUND
            )

    def post(self, request):
        """Создание или обновление телефона"""
        try:
            phone = Phone.objects.get(user=request.user)
            serializer = self.get_serializer(phone, data=request.data)
        except Phone.DoesNotExist:
            serializer = self.get_serializer(data=request.data)

        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {'detail': 'Телефон успешно сохранен',
             'phone': serializer.data},
            status=status.HTTP_200_OK
        )


@extend_schema_view(
    get=extend_schema(
        summary='Список контактов',
        description='Возвращает все контакты текущего пользователя.',
        responses={
            200: ContactSerializer(many=True),
            401: OpenApiResponse(description='Не авторизован'),
        },
        tags=['Контакты'],
    ),
    post=extend_schema(
        summary='Создать контакт',
        description='Создаёт новый контакт для текущего пользователя.',
        request=ContactSerializer,
        responses={
            201: ContactSerializer,
            400: OpenApiResponse(description='Ошибка валидации'),
            401: OpenApiResponse(description='Не авторизован'),
        },
        tags=['Контакты'],
    ),
)
class ContactViewSet(generics.ListCreateAPIView):
    """Представление для работы с контактами"""

    serializer_class = ContactSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Возвращаем только контакты текущего пользователя"""
        return Contact.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        """Сохраняем контакт с текущим пользователем"""
        serializer.save(user=self.request.user)


@extend_schema_view(
    get=extend_schema(
        summary="Получить контакт",
        responses={200: ContactSerializer},
        tags=['Contacts']
    ),
    put=extend_schema(
        summary="Обновить контакт (полное)",
        request=ContactSerializer,
        responses={200: ContactSerializer},
        tags=['Contacts']
    ),
    patch=extend_schema(
        summary="Частично обновить контакт",
        request=ContactSerializer,
        responses={200: ContactSerializer},
        tags=['Contacts']
    ),
    delete=extend_schema(
        summary="Удалить контакт",
        responses={
            200: inline_serializer(
                name='ContactDeleted',
                fields={'detail': OpenApiTypes.STR}
            ),
            400: inline_serializer(
                name='ContactInUse',
                fields={'detail': OpenApiTypes.STR}
            )
        },
        tags=['Contacts']
    )
)
class ContactDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для работы с конкретным контактом
    GET: Получение контакта
    PUT/PATCH: Обновление контакта
    DELETE: Удаление контакта
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ContactSerializer

    def get_queryset(self):
        """Возвращает контакты текущего пользователя"""
        return Contact.objects.filter(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """Удаление контакта с проверкой на использование в заказах"""
        instance = self.get_object()

        # Проверяем, используется ли контакт в заказах
        if Order.objects.filter(contact=instance).exists():
            return Response(
                {'detail': 'Невозможно удалить контакт, '
                           'так как он используется в заказах'},
                status=status.HTTP_400_BAD_REQUEST
            )

        self.perform_destroy(instance)
        return Response(
            {'detail': 'Контакт успешно удален'},
            status=status.HTTP_200_OK
        )


@extend_schema_view(
    patch=extend_schema(
        summary='Изменить права доступа магазина',
        description='Владелец магазина может изменить '
                    'параметр permissions_order для своего магазина.',
        parameters=[
            OpenApiParameter('pk', OpenApiTypes.INT,
                             OpenApiParameter.PATH,
                             description='ID магазина'),
        ],
        request=ShopPermissionSerializer,
        responses={
            200: ShopPermissionSerializer,
            400: OpenApiResponse(description='Ошибка валидации'),
            401: OpenApiResponse(description='Не авторизован'),
            403: OpenApiResponse(description='Недостаточно прав'),
            404: OpenApiResponse(description='Магазин не найден'),
        },
        tags=['Магазины'],
    ),
)
class ShopPermissionUpdateView(APIView):
    """API для владельца магазина:
    изменение доступа к заказам (permissions_order)."""

    permission_classes = [IsAuthenticated, IsShopOwner]

    def patch(self, request, pk):
        try:
            shop = Shop.objects.get(pk=pk)
            self.check_object_permissions(request, shop)  # Явная проверка

            serializer = ShopPermissionSerializer(shop, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST)
        except Shop.DoesNotExist:
            return Response({'detail': 'Магазин не найден.'},
                            status=status.HTTP_404_NOT_FOUND)


@extend_schema_view(
    get=extend_schema(
        summary='Заказы магазинов владельца',
        description='Возвращает заказы, содержащие товары '
                    'из магазинов, принадлежащих текущему пользователю.',
        responses={
            200: ShopOrderListSerializer(many=True),
            401: OpenApiResponse(description='Не авторизован'),
            404: OpenApiResponse(
                description='У вас нет магазинов',
                examples=[
                    OpenApiExample(
                        'Пример',
                        value={'detail': 'У вас нет магазинов.'},
                    )
                ],
            ),
        },
        tags=['Магазины'],
    ),
)
class ShopOrderListView(APIView):
    """API для владельца магазина:
    получение списка заказов с товарами из его магазинов."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_shops = Shop.objects.filter(owner=request.user)

        if not user_shops.exists():
            return Response({'detail': 'У вас нет магазинов.'},
                            status=status.HTTP_404_NOT_FOUND)

        user_shop_ids = list(user_shops.values_list('id', flat=True))

        # Получаем заказы, где есть товары из магазинов пользователя
        orders = Order.objects.filter(
            order_items__product__shop__in=user_shops
        ).distinct().order_by('-dt')

        # Передаём ID магазинов владельца в контекст сериализатора
        serializer = ShopOrderListSerializer(
            orders, many=True, context={'user_shop_ids': user_shop_ids})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    retrieve=extend_schema(
        summary="Получить аватар пользователя",
        responses={200: AvatarSerializer},
        tags=['User Profile']
    ),
    upload=extend_schema(
        summary="Загрузить аватар",
        description="Загружает изображение аватара (JPEG, PNG, WebP, до 5 МБ).",
        request=inline_serializer(
            name='AvatarUpload',
            fields={
                'avatar': OpenApiTypes.BINARY
            }
        ),
        responses={
            200: inline_serializer(
                name='AvatarUploadResponse',
                fields={
                    'status': OpenApiTypes.STR,
                    'message': OpenApiTypes.STR,
                    'data': AvatarSerializer()
                }
            )
        },
        methods=['POST'],
        examples=[
            OpenApiExample(
                'Valid Upload',
                summary='Загрузка аватара',
                value={
                    "avatar": "file://avatar.png"
                },
                request_only=True,
                response_only=False
            )
        ],
        tags=['User Profile']
    ),
    delete_avatar=extend_schema(
        summary="Удалить аватар",
        responses={
            200: inline_serializer(
                name='AvatarDeleted',
                fields={
                    'status': OpenApiTypes.STR,
                    'message': OpenApiTypes.STR
                }
            ),
            404: inline_serializer(
                name='AvatarNotFound',
                fields={
                    'status': OpenApiTypes.STR,
                    'message': OpenApiTypes.STR
                }
            )
        },
        methods=['DELETE'],
        tags=['User Profile']
    )
)
class AvatarViewSet(viewsets.ViewSet):
    """
    API для управления аватаром пользователя.

    * Требуется аутентификация.
    * Пользователь может управлять только СВОИМ аватаром.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser,
                      parsers.JSONParser]

    def get_serializer_class(self):
        return AvatarSerializer

    def retrieve(self, request):
        """
        GET /api/avatar/ — просмотр текущего аватара.
        """
        serializer = AvatarSerializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='upload')
    def upload(self, request):
        """
        POST /api/avatar/upload/ — загрузить/обновить аватар.

        Тело запроса (multipart/form-data):
        - avatar: файл изображения (JPEG, PNG, WebP, макс. 5 МБ)
        """
        serializer = AvatarSerializer(
            request.user,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    'status': 'success',
                    'message': 'Аватар успешно обновлён',
                    'data': serializer.data
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['delete'], url_path='delete')
    def delete_avatar(self, request):
        """
        DELETE /api/avatar/delete/ — удалить аватар.
        """
        user = request.user
        if user.avatar:
            # Удаляем файл
            storage = user.avatar.storage
            if user.avatar:
                storage.delete(user.avatar.name)
            # Очищаем поле
            user.avatar = None
            user.save(update_fields=['avatar'])
            return Response(
                {'status': 'success', 'message': 'Аватар удалён'},
                status=status.HTTP_200_OK
            )
        return Response(
            {'status': 'error', 'message': 'Аватар не установлен'},
            status=status.HTTP_404_NOT_FOUND
        )


@extend_schema_view(
    list=extend_schema(
        summary="Список изображений товаров",
        responses={200: ProductImageListSerializer(many=True)},
        tags=['Product Images']
    ),
    retrieve=extend_schema(
        summary="Получить изображение товара",
        responses={200: ProductImageListSerializer},
        tags=['Product Images']
    ),
    create=extend_schema(
        summary="Загрузить изображение товара",
        request=ProductImageUploadSerializer,
        responses={201: ProductImageListSerializer},
        tags=['Product Images']
    ),
    update=extend_schema(
        summary="Обновить изображение товара",
        request=ProductImageUpdateSerializer,
        responses={200: ProductImageListSerializer},
        tags=['Product Images']
    ),
    partial_update=extend_schema(
        summary="Частично обновить изображение товара",
        request=ProductImageUpdateSerializer,
        responses={200: ProductImageListSerializer},
        tags=['Product Images']
    ),
    destroy=extend_schema(
        summary="Удалить изображение товара",
        responses={204: None},
        tags=['Product Images']
    ),
    by_product=extend_schema(
        summary="Получить все изображения товара",
        description="Возвращает все изображения для указанного ProductInfo.",
        responses={
            200: inline_serializer(
                name='ProductImagesResponse',
                fields={
                    'product_info_id': OpenApiTypes.INT,
                    'product_name': OpenApiTypes.STR,
                    'count': OpenApiTypes.INT,
                    'results': ProductImageListSerializer(many=True)
                }
            )
        },
        parameters=[
            OpenApiParameter(
                name='product_info_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID ProductInfo"
            )
        ],
        tags=['Product Images']
    ),
    bulk_upload=extend_schema(
        summary="Массовая загрузка изображений товара",
        description="Загружает несколько изображений для одного товара. "
                    "Поддерживает multipart/form-data.",
        request=ProductImageBulkUploadSerializer,
        responses={
            201: inline_serializer(
                name='BulkUploadSuccess',
                fields={
                    'status': OpenApiTypes.STR,
                    'product_info_id': OpenApiTypes.INT,
                    'total_uploaded': OpenApiTypes.INT,
                    'created': OpenApiTypes.INT,
                    'errors': OpenApiTypes.INT,
                    'image_ids': list,
                    'error_details': OpenApiTypes.OBJECT
                }
            ),
            207: inline_serializer(
                name='BulkUploadPartial',
                fields={
                    'status': OpenApiTypes.STR,
                    'product_info_id': OpenApiTypes.INT,
                    'total_uploaded': OpenApiTypes.INT,
                    'created': OpenApiTypes.INT,
                    'errors': OpenApiTypes.INT,
                    'image_ids': list,
                    'error_details': OpenApiTypes.OBJECT
                }
            )
        },
        methods=['POST'],
        examples=[
            OpenApiExample(
                'Bulk Upload Example',
                summary='Пример массовой загрузки',
                value={
                    "product_info": 123,
                    "images": [
                        "file://img1.jpg",
                        "file://img2.png"
                    ],
                    "alt_text": "Описание изображений"
                },
                request_only=True
            )
        ],
        tags=['Product Images']
    ),
    set_main=extend_schema(
        summary="Установить изображение как главное",
        responses={
            200: inline_serializer(
                name='SetMainSuccess',
                fields={
                    'status': OpenApiTypes.STR,
                    'message': OpenApiTypes.STR
                }
            )
        },
        methods=['POST'],
        tags=['Product Images']
    ),
    regenerate=extend_schema(
        summary="Перегенерировать миниатюры изображения",
        responses={
            200: inline_serializer(
                name='RegenerateSuccess',
                fields={
                    'status': OpenApiTypes.STR,
                    'message': OpenApiTypes.STR
                }
            )
        },
        methods=['POST'],
        tags=['Product Images']
    )
)
class ProductImageViewSet(viewsets.ModelViewSet):
    """
    API для управления изображениями товаров.

    list        → GET    /api/product-images/
    retrieve    → GET    /api/product-images/{id}/
    create      → POST   /api/product-images/          (загрузить одно)
    update      → PUT    /api/product-images/{id}/
    partial_update → PATCH /api/product-images/{id}/
    destroy     → DELETE /api/product-images/{id}/

    Дополнительные endpoints:
    - GET  /api/product-images/by-product/{product_info_id}/
    - POST /api/product-images/bulk-upload/
    - POST /api/product-images/{id}/set-main/
    - POST /api/product-images/{id}/regenerate/
    """
    queryset = ProductImage.objects.all()
    permission_classes = [IsAuthenticatedOrReadOnly]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser,
                      parsers.JSONParser]

    def get_serializer_class(self):
        if self.action == 'create':
            return ProductImageUploadSerializer
        elif self.action in ('update', 'partial_update'):
            return ProductImageUpdateSerializer
        elif self.action == 'bulk_upload':
            return ProductImageBulkUploadSerializer
        return ProductImageListSerializer

    def perform_create(self, serializer):
        """
        После создания ЗАПУСКАЕМ Celery-задачу.
        Модель не запускает задачу сама — это ответственность ViewSet.
        """
        instance = serializer.save()
        # Асинхронно генерируем миниатюры — НЕ блокируем ответ
        generate_product_thumbnails.delay(instance.id)

    def perform_destroy(self, instance):
        """При удалении вызываем штатный delete модели (удаляет и файлы)."""
        instance.delete()

    # ──── Дополнительные endpoints ────

    @action(detail=False, methods=['get'],
            url_path='by-product/(?P<product_info_id>[^/.]+)')
    def by_product(self, request, product_info_id=None):
        """
        GET /api/product-images/by-product/{product_info_id}/
        Возвращает ВСЕ изображения указанного товара.
        """
        product_info = get_object_or_404(ProductInfo, id=product_info_id)
        images = ProductImage.objects.filter(product_info=product_info)
        serializer = ProductImageListSerializer(images, many=True,
                                                context={'request': request})
        return Response({
            'product_info_id': product_info.id,
            'product_name': product_info.full_name,
            'count': images.count(),
            'results': serializer.data
        })

    @action(detail=False, methods=['post'], url_path='bulk-upload',
            parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def bulk_upload(self, request):
        """
        POST /api/product-images/bulk-upload/
        Множественная загрузка изображений для одного товара.

        Загружает все файлы, затем запускает ОДНУ Celery-задачу на всю пачку.
        """
        serializer = ProductImageBulkUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_info = serializer.validated_data['product_info']
        images = serializer.validated_data['images']
        alt_text = serializer.validated_data.get('alt_text', '')

        created_ids = []
        errors = []

        for idx, image_file in enumerate(images):
            try:
                img_instance = ProductImage.objects.create(
                    product_info=product_info,
                    original=image_file,
                    alt_text=alt_text or f'Изображение {idx + 1} товара '
                                         f'{product_info.full_name}',
                    sort_order=idx,
                    is_main=(idx == 0 and not ProductImage.objects.filter(
                        product_info=product_info, is_main=True
                    ).exists())
                )
                created_ids.append(img_instance.id)

            except Exception as exc:
                errors.append({
                    'file': getattr(image_file, 'name', f'image_{idx}'),
                    'error': str(exc)
                })

        # Запускаем ОДНУ задачу на все изображения (а не N отдельных)
        if created_ids:
            bulk_generate_thumbnails.delay(created_ids)

        return Response({
            'status': 'success' if not errors else 'partial',
            'product_info_id': product_info.id,
            'total_uploaded': len(images),
            'created': len(created_ids),
            'errors': len(errors),
            'image_ids': created_ids,
            'error_details': errors if errors else None,
        },
            status=(status.HTTP_201_CREATED if not errors else
                    status.HTTP_207_MULTI_STATUS)
        )

    @action(detail=True, methods=['post'], url_path='set-main')
    def set_main(self, request, pk=None):
        """
        POST /api/product-images/{id}/set-main/
        Устанавливает данное изображение как главное для товара.
        """
        image = self.get_object()
        ProductImage.objects.filter(
            product_info=image.product_info,
            is_main=True
        ).exclude(id=image.id).update(is_main=False)

        image.is_main = True
        image.save(update_fields=['is_main'])

        return Response({
            'status': 'success',
            'message': f'Изображение {image.id} теперь главное для товара '
                       f'"{image.product_info.full_name}"'
        })

    @action(detail=True, methods=['post'], url_path='regenerate')
    def regenerate(self, request, pk=None):
        """
        POST /api/product-images/{id}/regenerate/
        Принудительно перегенерировать миниатюры для изображения.
        """
        image = self.get_object()
        # Сбрасываем старые миниатюры, чтобы задача заново их создала
        image.preview = None
        image.full_view = None
        image.save(update_fields=['preview', 'full_view'])

        generate_product_thumbnails.delay(image.id)

        return Response({
            'status': 'success',
            'message': f'Запущена регенерация миниатюр для изображения {image.id}'
        })
