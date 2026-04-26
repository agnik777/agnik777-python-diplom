# permissions.py
from rest_framework import permissions

from .models import Shop, Order


class IsShopOwner(permissions.BasePermission):
    """
    Разрешение только для владельцев магазинов
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.type == 'owner'

    def has_object_permission(self, request, view, obj):
        # Если объект - магазин, проверяем напрямую
        if isinstance(obj, Shop):
            return obj.owner == request.user

        if isinstance(obj, Order):
            # Получаем все магазины пользователя
            user_shops = Shop.objects.filter(owner=request.user)
            # Проверяем, есть ли в заказе товары из этих магазинов
            return obj.order_items.filter(product__shop__in=user_shops).exists()

        return False
