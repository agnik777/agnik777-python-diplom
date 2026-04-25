# views.py
import yaml
from datetime import timedelta, datetime

from django.http import JsonResponse, Http404
from django.utils import timezone
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from .models import (Shop, ConfirmEmailToken, ProductInfo, Order, Contact,
                     OrderItem, Phone)
from requests.exceptions import RequestException
from rest_framework import generics, status, filters, permissions
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .permissions import IsShopOwner
from .serializers import (
    YAMLImportSerializer, UserRegistrationSerializer, UserLoginSerializer,
    ShopSerializer, ShopCategorySerializer, ProductInfoSerializer,
    ProductSearchSerializer, OrderSerializer, AddToCartSerializer,
    OrderItemSerializer, UpdateCartItemSerializer, ContactSerializer,
    ContactListSerializer, PhoneSerializer, OrderCreateSerializer,
    OrderDetailSerializer, OrderConfirmSerializer, OrderListSerializer
)
from .utils import ProductUtils, OrderUtils
from .yaml_processor import YAMLProcessor
from .file_loader import FileLoader
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models import Q


class UserRegistrationView(generics.CreateAPIView):
    """Регистрация нового пользователя"""
    serializer_class = UserRegistrationSerializer

    def perform_create(self, serializer):
        user = serializer.save()
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
    """Подтверждение email по токену"""
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
    """Вход пользователя в систему"""
    serializer_class = UserLoginSerializer

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
        user.save()

        # Получаем или создаем токен для пользователя
        token, created = Token.objects.get_or_create(user=user)

        return Response({
            'token': token.key,
            'user_id': user.pk,
            'email': user.email
        }, status=status.HTTP_200_OK)


class PartnerUpdate(APIView):
    """Класс для обновления прайса от поставщика"""
    permission_classes = [IsAuthenticated, IsShopOwner]

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


class ShopListView(generics.ListAPIView):
    """
    API для получения списка активных магазинов
    GET /api/shops/
    """
    queryset = Shop.objects.filter(permissions_order=True).order_by('name')
    serializer_class = ShopSerializer
    permission_classes = [permissions.AllowAny]


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
                        date_obj = datetime.strptime(sell_up_to,
                                                     '%Y-%m-%d').date()
                    except ValueError:
                        pass

                # Формат dd.mm.YYYY
                if not date_obj and '.' in sell_up_to:
                    try:
                        date_obj = datetime.strptime(sell_up_to,
                                                     '%d.%m.%Y').date()
                    except ValueError:
                        pass

                # Если дата определена и просрочена,
                # добавляем в условия исключения
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


class CartView(generics.GenericAPIView):
    """
    API для работы с корзиной
    GET: Просмотр содержимого корзины
    POST: Добавление товара в корзину
    """
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """Проверяем, что пользователь - покупатель"""
        if self.request.method in ['GET', 'POST', 'PUT', 'DELETE']:
            if self.request.user.type != 'buyer':
                self.permission_denied(
                    self.request,
                    message="Только покупатели могут работать с корзиной"
                )
        return super().get_permissions()

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


class CartItemDetailView(generics.GenericAPIView):
    """
    API для работы с конкретным товаром в корзине
    PUT: Изменение количества товара
    DELETE: Удаление товара из корзины
    """
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """Проверяем, что пользователь - покупатель"""
        if self.request.user.type != 'buyer':
            self.permission_denied(
                self.request,
                message="Только покупатели могут работать с корзиной"
            )
        return super().get_permissions()

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


class ProductDetailView(generics.RetrieveAPIView):
    """
    API для получения детальной информации о товаре
    GET /api/products/{id}/
    """
    serializer_class = ProductInfoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        """Оптимизированный запрос с предзагрузкой связанных данных"""
        queryset = ProductUtils.get_available_products_queryset()

        # Оптимизация запросов
        queryset = queryset.select_related(
            'product',
            'shop',
            'product__category'
        ).prefetch_related(
            'product_parameters__parameter'
        )

        return queryset

    def get_queryset(self):
        """Используем утилиту для получения доступных товаров"""
        return ProductUtils.get_available_products_queryset()
    
    def get_object(self):
        """Получаем товар с проверкой доступности"""
        queryset = self.get_queryset()
        obj = super().get_object()

        # Дополнительная проверка (на всякий случай)
        if not obj.is_available():
            raise Http404("Товар недоступен")

        return obj


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

            # Отправляем уведомления
            OrderUtils.send_order_notifications(request.user, basket,
                                                contact, phone)

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

            # Отправляем уведомления
            OrderUtils.send_order_confirmed_notifications(
                request.user, order, previous_status
            )

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


class OrderListView(generics.ListAPIView):
    """Список заказов пользователя"""
    permission_classes = [IsAuthenticated]
    serializer_class = OrderListSerializer

    def get_queryset(self):
        return Order.objects.filter(
            contact__user=self.request.user
        ).exclude(status='basket').order_by('-dt')


class OrderDetailView(generics.RetrieveAPIView):
    """Детальная информация о заказе"""
    permission_classes = [IsAuthenticated]
    serializer_class = OrderDetailSerializer

    def get_queryset(self):
        return Order.objects.filter(
            contact__user=self.request.user
        ).exclude(status='basket')


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
