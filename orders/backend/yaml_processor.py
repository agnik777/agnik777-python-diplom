# yaml_processor.py
import yaml
from django.core.exceptions import ValidationError
from yaml import Loader

from .models import (Shop, Category, Product, ProductInfo, Parameter,
                     ProductParameter)


class YAMLProcessor:
    """
    Класс для обработки YAML файлов с данными магазина
    """

    @staticmethod
    def validate_structure(data):
        """
        Валидация структуры YAML данных

        Args:
            data: Распарсенные данные YAML

        Raises:
            ValidationError: Если структура невалидна
        """
        required_keys = ['shop', 'categories', 'goods']

        for key in required_keys:
            if key not in data:
                raise ValidationError(f'Отсутствует обязательный ключ: {key}')

        # Проверка категорий
        if not isinstance(data['categories'], list):
            raise ValidationError('"categories" должен быть списком')

        for i, category in enumerate(data['categories']):
            if 'id' not in category:
                raise ValidationError(f'Категория #{i}: отсутствует "id"')
            if 'name' not in category:
                raise ValidationError(f'Категория #{i}: отсутствует "name"')

        # Проверка товаров
        if not isinstance(data['goods'], list):
            raise ValidationError('"goods" должен быть списком')

        required_item_keys = ['id', 'name', 'category', 'quantity',
                              'retail_price']

        for i, item in enumerate(data['goods']):
            for key in required_item_keys:
                if key not in item:
                    raise ValidationError(f'Товар #{i}: отсутствует "{key}"')

            # Проверка параметров (опционально)
            if 'parameters' in item and not isinstance(
                    item['parameters'], dict):
                raise ValidationError(f'Товар #{i}: "parameters" '
                                      f'должен быть словарем')

    @staticmethod
    def parse_yaml(content):
        """
        Парсинг YAML контента

        Args:
            content: Содержимое YAML файла (bytes или str)

        Returns:
            dict: Распарсенные данные

        Raises:
            yaml.YAMLError: Если ошибка парсинга
        """
        if isinstance(content, bytes):
            content = content.decode('utf-8')

        return yaml.load(content, Loader=Loader)

    @staticmethod
    def process_data(data, user):
        """
        Обработка данных из YAML файла

        Args:
            data: Распарсенные данные YAML
            user: Текущий пользователь (владелец магазина)

        Returns:
            dict: Результат обработки
        """
        # Валидация структуры
        YAMLProcessor.validate_structure(data)

        # Создание или получение магазина
        shop, created = Shop.objects.get_or_create(
            name=data['shop'],
            owner=user,
            defaults={'url': data.get('url', '')}
        )

        # Обработка категорий
        categories_processed = 0
        category_map = {}  # Словарь для быстрого доступа к категориям

        for category in data['categories']:
            category_object, _ = Category.objects.get_or_create(
                id=category['id'],
                name=category['name']
            )
            # Добавляем магазин в категорию через ManyToMany
            category_object.shops.add(shop)
            categories_processed += 1
            category_map[category['id']] = category_object

        # Удаление старых товаров магазина
        deleted_count = ProductInfo.objects.filter(shop=shop).delete()[0]

        # Обработка товаров
        products_processed = 0
        parameters_processed = 0

        for item in data['goods']:
            # Получаем категорию из словаря
            category_id = item['category']
            if category_id not in category_map:
                raise ValidationError(f"Категория с id={category_id} "
                                      f"не найдена в загружаемых данных")

            category = category_map[category_id]

            # Создаем или получаем продукт
            product, _ = Product.objects.get_or_create(
                name=item['name'],
                category=category
            )

            # Создаем информацию о продукте
            product_info = ProductInfo.objects.create(
                product=product,
                external_id=item['id'],
                full_name=item.get('full_name', item['name']),
                shop=shop,
                quantity=item['quantity'],
                retail_price=item['retail_price'],
                wholesale_price=item.get('wholesale_price',
                                         item['retail_price'])
            )

            # Обработка параметров товара
            for name, value in item.get('parameters', {}).items():
                parameter_object, _ = Parameter.objects.get_or_create(name=name)
                ProductParameter.objects.create(
                    product_info=product_info,
                    parameter=parameter_object,
                    value=str(value)
                )
                parameters_processed += 1

            products_processed += 1

        return {
            'shop': {
                'id': shop.id,
                'name': shop.name,
                'owner': user.email,
                'created': created
            },
            'statistics': {
                'categories_processed': categories_processed,
                'products_processed': products_processed,
                'parameters_processed': parameters_processed,
                'old_products_deleted': deleted_count
            }
        }
