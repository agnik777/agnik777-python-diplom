from django.shortcuts import render

# Create your views here.
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from requests import get
from rest_framework.views import APIView
from yaml import load as load_yaml, Loader
from .models import (Shop, Category, Product, ProductInfo, Parameter,
                     ProductParameter)


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
            return JsonResponse(
                {'Status': False, 'Error': str(e)}, status=400
            )

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
            category_object, _ = Category.objects.get_or_create(id=cat_id,
                                                                name=cat_name)
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
                name=name, category=product_category
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
