# admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import (
    User, Shop, Category, Product, ProductInfo, Parameter,
    ProductParameter, Contact, Phone, Order, OrderItem, ConfirmEmailToken
)

# --- Inline-модели для вложенного редактирования ---

class ProductInfoInline(admin.TabularInline):
    model = ProductInfo
    extra = 1 # Количество пустых форм для добавления

class ProductParameterInline(admin.TabularInline):
    model = ProductParameter
    extra = 1

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1

# --- Кастомный UserAdmin ---

class UserAdmin(BaseUserAdmin):
    # Поля для формы создания пользователя (в админке)
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )

    # Поля для формы изменения пользователя
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'username',
                                         'company', 'type')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups',
                       'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )

    # Отображение в списке пользователей
    list_display = ('email', 'first_name', 'last_name', 'type', 'is_active',
                    'is_staff')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'type')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)

# --- Регистрация моделей ---

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    pass

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner')
    search_fields = ('name',)
    list_filter = ('owner',)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    filter_horizontal = ('shops',) # Удобный виджет для ManyToMany

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    search_fields = ('name',)
    list_filter = ('category',)

@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    list_display = ('product', 'shop', 'quantity', 'retail_price')
    search_fields = ('product__name', 'shop__name')
    list_filter = ('shop', 'product__category')
    inlines = [ProductParameterInline] # Вкладка с параметрами прямо здесь

@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(ProductParameter)
class ProductParameterAdmin(admin.ModelAdmin):
    list_display = ('product_info', 'parameter', 'value')

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'street')
    search_fields = ('user__email', 'city')

@admin.register(Phone)
class PhoneAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone')
    search_fields = ('phone', 'user__email')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('dt', 'contact', 'status')
    list_filter = ('status', 'dt')
    search_fields = ('contact__user__email',)
    inlines = [OrderItemInline] # Вкладка с товарами в заказе

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity')

@admin.register(ConfirmEmailToken)
class ConfirmEmailTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    readonly_fields = ('key',) # Ключ нельзя менять вручную
