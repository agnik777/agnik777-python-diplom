# admin.py
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    User,
    Shop,
    Category,
    Product,
    ProductInfo,
    Parameter,
    ProductParameter,
    Contact,
    Phone,
    Order,
    OrderItem,
    ConfirmEmailToken,
)


class ProductParameterInline(admin.TabularInline):
    """Параметры товара внутри карточки ProductInfo"""
    model = ProductParameter
    extra = 1
    verbose_name = 'Параметр'
    verbose_name_plural = 'Характеристики товара'


class ContactInline(admin.TabularInline):
    """Контакты внутри пользователя"""
    model = Contact
    extra = 0
    verbose_name = 'Контакт'
    verbose_name_plural = 'Адреса доставки'


class PhoneInline(admin.TabularInline):
    """Телефоны внутри пользователя"""
    model = Phone
    extra = 0
    verbose_name = 'Телефон'
    verbose_name_plural = 'Телефоны'


class OrderItemInline(admin.TabularInline):
    """Товары внутри заказа"""
    model = OrderItem
    extra = 1
    readonly_fields = ('product', 'quantity')
    verbose_name = 'Позиция заказа'
    verbose_name_plural = 'Товары в заказе'


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        'email', 'first_name', 'last_name', 'type', 'company',
        'is_active', 'is_staff', 'login_count', 'last_login_time'
    )
    list_filter = ('type', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('email', 'first_name', 'last_name', 'company')
    ordering = ('email',)
    readonly_fields = ('login_count', 'last_login_time', 'avatar_display')
    inlines = [ContactInline, PhoneInline]
    fieldsets = (
        (None, {
            'fields': ('email', 'password')
        }),
        ('Персональная информация', {
            'fields': (
                'first_name', 'last_name', 'company', 'type',
                'avatar', 'avatar_display', 'avatar_url'
            )
        }),
        ('Разрешения', {
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'groups', 'user_permissions'
            )
        }),
        ('Статистика', {
            'fields': ('login_count', 'last_login_time')
        }),
    )

    def avatar_display(self, obj):
        url = obj.avatar_display_url
        if url:
            return format_html(
                '<img src="{}" style="max-height: 100px; border-radius: 8px;" />',
                url
            )
        return '—'
    avatar_display.short_description = 'Аватар (просмотр)'


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'owner', 'permissions_order')
    list_filter = ('permissions_order',)
    search_fields = ('name', 'owner__email')
    ordering = ('name',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'shops_list')
    search_fields = ('name',)
    ordering = ('name',)

    def shops_list(self, obj):
        return ', '.join([shop.name for shop in obj.shops.all()])
    shops_list.short_description = 'Магазины'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    list_filter = ('category',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    list_display = (
        'product', 'full_name', 'shop', 'external_id',
        'quantity', 'retail_price', 'wholesale_price',
        'sell_up_to', 'is_available'
    )
    list_filter = ('shop', 'product__category')
    search_fields = ('full_name', 'product__name')
    ordering = ('product',)
    inlines = [ProductParameterInline]

    def is_available(self, obj):
        return obj.is_available()
    is_available.boolean = True
    is_available.short_description = 'Доступен'


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(ProductParameter)
class ProductParameterAdmin(admin.ModelAdmin):
    list_display = ('product_info', 'parameter', 'value')
    list_filter = ('parameter',)
    search_fields = ('product_info__full_name', 'parameter__name', 'value')


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'street', 'house', 'structure', 'apartment')
    list_filter = ('city',)
    search_fields = ('user__email', 'city', 'street')
    ordering = ('user',)


@admin.register(Phone)
class PhoneAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone')
    search_fields = ('phone', 'user__email')
    ordering = ('phone',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'contact', 'dt', 'status')
    list_filter = ('status',)
    search_fields = ('contact__user__email',)
    ordering = ('-dt',)
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity')
    search_fields = ('order__id', 'product__full_name')


@admin.register(ConfirmEmailToken)
class ConfirmEmailTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'key', 'created_at')
    search_fields = ('user__email', 'key')
    readonly_fields = ('key', 'created_at')
    ordering = ('-created_at',)
