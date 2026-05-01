# serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.utils.translation import gettext_lazy as _
from .models import (Shop, Category, Product, ProductInfo, Parameter,
                     ProductParameter, OrderItem, Order, Phone, Contact)


User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
    """Сериализатор для регистрации пользователя"""
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password']

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        return user


class UserLoginSerializer(serializers.Serializer):
    """Сериализатор для логирования"""
    email = serializers.EmailField()
    password = serializers.CharField(
        trim_whitespace=False,
        style={'input_type': 'password'}
    )

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            # Используем authenticate с email как username
            user = authenticate(
                request=self.context.get('request'),
                username=email,
                password=password
            )
            if not user:
                msg = _('Неверный email или пароль.')
                raise serializers.ValidationError(msg, code='authorization')
            # Проверка is_active встроена в authenticate
            # при использовании TokenAuthentication
        else:
            msg = _('Должны быть указаны email и пароль.')
            raise serializers.ValidationError(msg, code='authorization')

        attrs['user'] = user
        return attrs


class CategoryListSerializer(serializers.ModelSerializer):
    """Сериализатор списка категорий"""
    class Meta:
        model = Category
        fields = ['id', 'name']
        read_only_fields = ['id']


class ShopCategorySerializer(serializers.ModelSerializer):
    """Сериализатор для магазинов с категориями"""
    categories = CategoryListSerializer(many=True, read_only=True)
    owner_email = serializers.EmailField(source='owner.email', read_only=True)

    class Meta:
        model = Shop
        fields = ['id', 'name', 'url', 'owner', 'owner_email',
                  'permissions_order', 'categories']
        read_only_fields = ['id', 'owner', 'owner_email']


class ShopSerializer(serializers.ModelSerializer):
    """Сериализатор для магазина"""
    owner_email = serializers.EmailField(source='owner.email', read_only=True)

    class Meta:
        model = Shop
        fields = ['id', 'name', 'url', 'owner', 'owner_email']
        read_only_fields = ['owner']


class CategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категории"""
    shops_count = serializers.IntegerField(source='shops.count',
                                           read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'shops', 'shops_count']
        read_only_fields = ['shops']


class ProductSerializer(serializers.ModelSerializer):
    """Сериализатор для продукта"""
    category_name = serializers.CharField(source='category.name',
                                          read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'name', 'category', 'category_name']


class ParameterSerializer(serializers.ModelSerializer):
    """Сериализатор для параметра"""

    class Meta:
        model = Parameter
        fields = ['id', 'name']
        read_only_fields = ['id']


class ProductParameterSerializer(serializers.ModelSerializer):
    """Сериализатор для параметра продукта"""
    parameter_name = serializers.CharField(source='parameter.name',
                                           read_only=True)

    class Meta:
        model = ProductParameter
        fields = ['id', 'product_info', 'parameter', 'parameter_name', 'value']


class ProductInfoSerializer(serializers.ModelSerializer):
    """Сериализатор для информации о продукте"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)

    parameters_dict = serializers.SerializerMethodField()

    def get_parameters_dict(self, obj):
        """Возвращает параметры в виде словаря {название: значение}"""
        parameters = {}
        for param in obj.product_parameters.all():
            parameters[param.parameter.name] = param.value
        return parameters

    class Meta:
        model = ProductInfo
        fields = [
            'id', 'product', 'product_name', 'external_id',
            'full_name', 'shop', 'shop_name', 'quantity',
            'retail_price', 'wholesale_price', 'sell_up_to',
            'parameters_dict'
        ]


class ProductSearchSerializer(serializers.Serializer):
    """Сериализатор для поиска товаров"""
    shop_name = serializers.CharField(required=False, allow_blank=True)
    category_name = serializers.CharField(required=False, allow_blank=True)
    product_name = serializers.CharField(required=False, allow_blank=True)
    min_price = serializers.IntegerField(required=False, min_value=0)
    max_price = serializers.IntegerField(required=False, min_value=0)
    in_stock_only = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        """Валидация ценового диапазона"""
        min_price = data.get('min_price')
        max_price = data.get('max_price')

        if min_price and max_price and min_price > max_price:
            raise serializers.ValidationError({
                'min_price': 'Минимальная цена не может быть '
                             'больше максимальной'
            })

        return data


class ContactSerializer(serializers.ModelSerializer):
    """Сериализатор для контактов пользователя"""

    class Meta:
        model = Contact
        fields = ['id', 'city', 'street', 'house', 'structure', 'apartment']
        read_only_fields = ['id']

    def create(self, validated_data):
        """Создание контакта"""
        # user будет добавлен из представления
        return Contact.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """Обновление контакта"""
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ContactListSerializer(serializers.ModelSerializer):
    """Сериализатор для списка контактов"""

    class Meta:
        model = Contact
        fields = ['id', 'city', 'street', 'house', 'structure', 'apartment']


class OrderItemSerializer(serializers.ModelSerializer):
    """Сериализатор для товара в корзине"""
    product_name = serializers.CharField(source='product.product.name',
                                         read_only=True)
    full_name = serializers.CharField(source='product.full_name',
                                      read_only=True)
    shop_name = serializers.CharField(source='product.shop.name',
                                      read_only=True)
    retail_price = serializers.IntegerField(source='product.retail_price',
                                            read_only=True)
    item_total = serializers.SerializerMethodField()
    external_id = serializers.IntegerField(source='product.external_id',
                                           read_only=True)
    max_available = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'product_name', 'full_name', 'shop_name',
            'external_id', 'retail_price', 'quantity', 'item_total',
            'max_available'
        ]

    def get_item_total(self, obj):
        """Рассчитывает стоимость товара в корзине"""
        return obj.quantity * obj.product.retail_price

    def get_max_available(self, obj):
        """Возвращает максимально доступное количество товара"""
        return obj.product.get_available_quantity()


class OrderSerializer(serializers.ModelSerializer):
    """Сериализатор для заказа (корзины)"""
    order_items = OrderItemSerializer(many=True, read_only=True)
    contact_info = serializers.SerializerMethodField()
    shop_totals = serializers.SerializerMethodField()
    basket_total = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'status', 'dt', 'contact', 'contact_info',
            'order_items', 'shop_totals', 'basket_total'
        ]
        read_only_fields = ['id', 'status', 'dt']

    def get_contact_info(self, obj):
        """Возвращает информацию о контакте"""
        if obj.contact:
            return {
                'city': obj.contact.city,
                'street': obj.contact.street,
                'house': obj.contact.house,
                'apartment': obj.contact.apartment
            }
        return None

    def get_shop_totals(self, obj):
        """Рассчитывает стоимость товаров по магазинам"""
        shop_totals = {}
        for item in obj.order_items.all():
            shop_name = item.product.shop.name
            item_total = item.quantity * item.product.retail_price
            if shop_name not in shop_totals:
                shop_totals[shop_name] = 0
            shop_totals[shop_name] += item_total
        return shop_totals

    def get_basket_total(self, obj):
        """Рассчитывает общую стоимость корзины"""
        total = 0
        for item in obj.order_items.all():
            total += item.quantity * item.product.retail_price
        return total


class AddToCartSerializer(serializers.Serializer):
    """Сериализатор для добавления товара в корзину"""
    product_id = serializers.IntegerField()

    def validate_product_id(self, value):
        """Проверяет существование товара"""
        try:
            product = ProductInfo.objects.get(id=value)

            # Проверка доступности товара
            if not product.is_available():
                raise serializers.ValidationError("Товар недоступен для заказа")

            return value
        except ProductInfo.DoesNotExist:
            raise serializers.ValidationError("Товар не найден")


class UpdateCartItemSerializer(serializers.ModelSerializer):
    """Сериализатор для обновления количества товара в корзине"""

    class Meta:
        model = OrderItem
        fields = ['quantity']

    def validate_quantity(self, value):
        """Проверяет количество товара"""
        if value <= 0:
            raise serializers.ValidationError("Количество должно быть больше 0")

        # Проверка доступного количества
        if hasattr(self, 'instance'):
            max_available = self.instance.product.get_available_quantity()
            if value > max_available:
                raise serializers.ValidationError(
                    f"Доступно только {max_available} единиц товара"
                )

        return value


class OrderCreateSerializer(serializers.Serializer):
    """Сериализатор для создания заказа из корзины"""
    contact_id = serializers.IntegerField(required=True)

    def validate_contact_id(self, value):
        """Проверяет, что контакт принадлежит пользователю"""
        user = self.context['request'].user
        try:
            contact = Contact.objects.get(id=value, user=user)
            return value
        except Contact.DoesNotExist:
            raise serializers.ValidationError("Контакт не найден или "
                                              "не принадлежит вам")

    def validate(self, data):
        """Проверяет, что в корзине есть товары"""
        user = self.context['request'].user

        # Ищем корзину пользователя
        basket = Order.objects.filter(
            contact__user=user,
            status='basket'
        ).first()

        if not basket or not basket.order_items.exists():
            raise serializers.ValidationError(
                {'detail': 'Корзина пуста. Добавьте товары перед '
                           'оформлением заказа.'}
            )

        # Проверяем, что у пользователя есть телефон
        try:
            phone = Phone.objects.get(user=user)
        except Phone.DoesNotExist:
            raise serializers.ValidationError(
                {'detail': 'Для оформления заказа необходимо указать '
                           'номер телефона.'}
            )

        data['basket'] = basket
        data['phone'] = phone
        return data


class OrderConfirmSerializer(serializers.Serializer):
    """Сериализатор для подтверждения заказа"""
    order_id = serializers.IntegerField(required=True)

    def validate_order_id(self, value):
        """Проверяет, что заказ принадлежит пользователю и имеет статус 'new'"""
        user = self.context['request'].user
        try:
            order = Order.objects.get(id=value, contact__user=user)
            if order.status != 'new':
                raise serializers.ValidationError(
                    f"Заказ имеет статус '{order.status}' "
                    f"и не может быть подтвержден"
                )
            return value
        except Order.DoesNotExist:
            raise serializers.ValidationError("Заказ не найден или "
                                              "не принадлежит вам")


class OrderDetailSerializer(serializers.ModelSerializer):
    """Сериализатор для детальной информации о заказе"""
    order_items = OrderItemSerializer(many=True, read_only=True)
    contact_info = ContactSerializer(source='contact', read_only=True)
    phone = serializers.SerializerMethodField()
    shop_totals = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'status', 'dt', 'contact', 'contact_info',
            'order_items', 'shop_totals', 'total_amount', 'phone'
        ]
        read_only_fields = ['id', 'status', 'dt']

    def get_phone(self, obj):
        """Возвращает телефон пользователя"""
        try:
            phone = Phone.objects.get(user=obj.contact.user)
            return phone.phone
        except Phone.DoesNotExist:
            return None

    def get_shop_totals(self, obj):
        """Рассчитывает стоимость товаров по магазинам"""
        shop_totals = {}
        for item in obj.order_items.all():
            shop_name = item.product.shop.name
            item_total = item.quantity * item.product.retail_price
            if shop_name not in shop_totals:
                shop_totals[shop_name] = {
                    'shop_name': shop_name,
                    'total': 0,
                    'items': []
                }
            shop_totals[shop_name]['total'] += item_total
            shop_totals[shop_name]['items'].append({
                'product_name': item.product.full_name,
                'quantity': item.quantity,
                'price': item.product.retail_price,
                'item_total': item_total
            })
        return list(shop_totals.values())

    def get_total_amount(self, obj):
        """Рассчитывает общую стоимость заказа"""
        total = 0
        for item in obj.order_items.all():
            total += item.quantity * item.product.retail_price
        return total


class OrderListSerializer(serializers.ModelSerializer):
    """Сериализатор для списка заказов"""
    total_amount = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['id', 'status', 'dt', 'total_amount', 'items_count']
        read_only_fields = ['id', 'status', 'dt']

    def get_total_amount(self, obj):
        """Рассчитывает общую стоимость заказа"""
        total = 0
        for item in obj.order_items.all():
            total += item.quantity * item.product.retail_price
        return total

    def get_items_count(self, obj):
        """Возвращает количество товаров в заказе"""
        return obj.order_items.count()


class PhoneSerializer(serializers.ModelSerializer):
    """Сериализатор для телефона пользователя"""

    class Meta:
        model = Phone
        fields = ['id', 'phone']
        read_only_fields = ['id']

    def validate_phone(self, value):
        """Валидация номера телефона"""
        # Убираем все нецифровые символы
        cleaned_phone = ''.join(filter(str.isdigit, value))

        # Проверяем длину (минимум 10 цифр для международного формата)
        if len(cleaned_phone) < 10:
            raise serializers.ValidationError("Номер телефона слишком короткий")

        # Проверяем уникальность
        if Phone.objects.filter(phone=cleaned_phone).exists():
            raise serializers.ValidationError(
                "Этот номер телефона уже используется")

        return cleaned_phone

    def create(self, validated_data):
        """Создание телефона для пользователя"""
        user = self.context['request'].user

        # Удаляем старый телефон, если он есть
        Phone.objects.filter(user=user).delete()

        # Создаем новый телефон
        return Phone.objects.create(user=user, **validated_data)

    def update(self, instance, validated_data):
        """Обновление телефона"""
        instance.phone = validated_data.get('phone', instance.phone)
        instance.save()
        return instance


class ShopPermissionSerializer(serializers.ModelSerializer):
    """Сериализатор для изменения разрешения на заказы (permissions_order)"""
    class Meta:
        model = Shop
        fields = ['permissions_order']
        extra_kwargs = {
            'permissions_order': {'required': True}
        }


class ShopOrderItemSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров в заказе"""
    product_name = serializers.CharField(source='product.full_name',
                                         read_only=True)
    shop_name = serializers.CharField(source='product.shop.name',
                                      read_only=True)
    retail_price = serializers.IntegerField(source='product.retail_price',
                                            read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['product_name', 'shop_name', 'quantity', 'retail_price',
                  'total_price']

    def get_total_price(self, obj):
        return obj.quantity * obj.product.retail_price

class ShopOrderListSerializer(serializers.ModelSerializer):
    """Сериализатор для списка заказов с товарами
    только из магазинов владельца"""
    order_items = serializers.SerializerMethodField()
    total_sum = serializers.SerializerMethodField()
    contact_info = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['id', 'dt', 'status', 'order_items', 'total_sum',
                  'contact_info']
        read_only_fields = fields

    def get_order_items(self, obj):
        # Получаем список ID магазинов владельца из контекста
        user_shop_ids = self.context.get('user_shop_ids', [])
        # Фильтруем товары заказа только по магазинам владельца
        filtered_items = obj.order_items.filter(product__shop__in=user_shop_ids)
        serializer = ShopOrderItemSerializer(filtered_items, many=True,
                                             context=self.context)
        return serializer.data

    def get_total_sum(self, obj):
        user_shop_ids = self.context.get('user_shop_ids', [])
        return sum(
            item.quantity * item.product.retail_price
            for item in obj.order_items.filter(product__shop__in=user_shop_ids)
        )

    def get_contact_info(self, obj):
        contact = obj.contact
        return {
            'city': contact.city,
            'street': contact.street,
            'house': contact.house,
            'structure': contact.structure,
            'apartment': contact.apartment,
            'user_name': f"{contact.user.first_name} {contact.user.last_name}",
            'user_email': contact.user.email,
        }


# Сериализаторы для YAML импорта
class YAMLCategorySerializer(serializers.Serializer):
    """Сериализатор для категории из YAML"""
    id = serializers.IntegerField()
    name = serializers.CharField()


class YAMLParameterSerializer(serializers.Serializer):
    """Сериализатор для параметров из YAML"""

    def to_representation(self, instance):
        return instance

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Параметры должны быть словарем")
        return data


class YAMLProductSerializer(serializers.Serializer):
    """Сериализатор для товара из YAML"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    category = serializers.IntegerField()
    full_name = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=0)
    retail_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    wholesale_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False
    )
    parameters = YAMLParameterSerializer(required=False)

    def validate(self, data):
        """Дополнительная валидация"""
        # Если wholesale_price не указан, используем retail_price
        if 'wholesale_price' not in data:
            data['wholesale_price'] = data['retail_price']

        # Если full_name не указан, используем name
        if 'full_name' not in data or not data['full_name']:
            data['full_name'] = data['name']

        return data


class YAMLImportSerializer(serializers.Serializer):
    """Сериализатор для всего YAML файла"""
    shop = serializers.CharField()
    url = serializers.URLField(required=False, allow_blank=True)
    categories = YAMLCategorySerializer(many=True)
    goods = YAMLProductSerializer(many=True)

    def validate(self, data):
        """Валидация всей структуры"""
        # Проверяем уникальность ID категорий
        category_ids = [cat['id'] for cat in data['categories']]
        if len(category_ids) != len(set(category_ids)):
            raise serializers.ValidationError(
                "ID категорий должны быть уникальными")

        # Проверяем уникальность ID товаров
        product_ids = [product['id'] for product in data['goods']]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError(
                "ID товаров должны быть уникальными")

        # Проверяем, что все категории товаров есть в списке категорий
        category_ids_set = set(category_ids)
        for i, product in enumerate(data['goods']):
            if product['category'] not in category_ids_set:
                raise serializers.ValidationError(
                    f"Товар #{i}: категория с id={product['category']} "
                    f"не найдена в списке категорий"
                )

        return data
