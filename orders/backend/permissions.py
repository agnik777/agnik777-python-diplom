# permissions.py
from rest_framework import permissions


class IsShopOwner(permissions.BasePermission):
    """
    Разрешение только для владельцев магазинов
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.type == 'owner'
