# serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.utils.translation import gettext_lazy as _
from .models import ConfirmEmailToken
from .models import (Shop, Category, Product, ProductInfo, Parameter,
                     ProductParameter)


User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
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


class ShopSerializer(serializers.ModelSerializer):
    """Сериализатор для магазина"""
    owner_email = serializers.EmailField(source='owner.email', read_only=True)

    class Meta:
        model = Shop
        fields = ['id', 'name', 'url', 'owner', 'owner_email']
        read_only_fields = ['owner']


class CategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категории"""
    shops_count = serializers.IntegerField(source='shops.count', read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'shops', 'shops_count']
        read_only_fields = ['shops']


class ProductSerializer(serializers.ModelSerializer):
    """Сериализатор для продукта"""
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'name', 'category', 'category_name']


class ParameterSerializer(serializers.ModelSerializer):
    """Сериализатор для параметра"""

    class Meta:
        model = Parameter
        fields = ['id', 'name']


class ProductParameterSerializer(serializers.ModelSerializer):
    """Сериализатор для параметра продукта"""
    parameter_name = serializers.CharField(source='parameter.name', read_only=True)

    class Meta:
        model = ProductParameter
        fields = ['id', 'product_info', 'parameter', 'parameter_name', 'value']


class ProductInfoSerializer(serializers.ModelSerializer):
    """Сериализатор для информации о продукте"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    parameters = ProductParameterSerializer(many=True, read_only=True)

    class Meta:
        model = ProductInfo
        fields = [
            'id', 'product', 'product_name', 'external_id',
            'full_name', 'shop', 'shop_name', 'quantity',
            'retail_price', 'wholesale_price', 'parameters'
        ]


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

    def validate_category(self, value):
        """Проверка существования категории"""
        if not Category.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Категория с id={value} не найдена")
        return value

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
            raise serializers.ValidationError("ID категорий должны быть уникальными")

        # Проверяем уникальность ID товаров
        product_ids = [product['id'] for product in data['goods']]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("ID товаров должны быть уникальными")

        return data
