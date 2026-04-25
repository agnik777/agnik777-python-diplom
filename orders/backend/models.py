# models.py
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_rest_passwordreset.tokens import get_token_generator

from .utils import ProductUtils


STATE_CHOICES = (
    ('basket', 'Статус корзины'),
    ('new', 'Новый'),
    ('confirmed', 'Подтвержден'),
    ('assembled', 'Собран'),
    ('sent', 'Отправлен'),
    ('delivered', 'Доставлен'),
    ('received', 'Получен'),
    ('canceled', 'Отменен'),
)

USER_TYPE_CHOICES = (
    ('owner', 'Владелец'),
    ('buyer', 'Покупатель'),
    ('admin', 'Администратор'),
)


class UserManager(BaseUserManager):
    """ Миксин для управления пользователями """
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given username, email, and password.
        """
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        # Устанавливаем is_active=False для новых пользователей
        extra_fields.setdefault('is_active', False)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        # Суперпользователь должен быть активным сразу
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('type', 'admin')
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return  self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Стандартная модель пользователей
    """
    REQUIRED_FIELDS = ['first_name', 'last_name']
    objects = UserManager()
    USERNAME_FIELD = 'email'
    email = models.EmailField(_('email address'), unique=True)
    company = models.CharField(verbose_name='Компания', max_length=40,
                               blank=True)
    username_validator = UnicodeUsernameValidator()
    username = models.CharField(
        _('username'), max_length=150,
        help_text=_('Required. 150 characters or fewer. '
                    'Letters, digits and @/./+/-/_ only.'),
        validators=[username_validator],
        error_messages={'unique': _("A user with that username already "
                                    "exists.")},
    )
    is_active = models.BooleanField(
        _('active'), default=False,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )
    type = models.CharField(verbose_name='Тип пользователя',
                           choices=USER_TYPE_CHOICES, max_length=5,
                           default='buyer')

    last_login_time = models.DateTimeField(
        verbose_name='Время последнего входа',
        null=True,
        blank=True
    )
    login_count = models.IntegerField(
        verbose_name='Количество входов',
        default=0
    )

    # Поля с уникальными related_name
    groups = models.ManyToManyField(
        Group,
        related_name='custom_user_set',
        blank=True,
        help_text=_('The groups this user belongs to.'),
        verbose_name=_('groups')
    )

    user_permissions = models.ManyToManyField(
        Permission,
        related_name='custom_user_set',
        blank=True,
        help_text=_('Specific permissions for this user.'),
        verbose_name=_('user permissions')
    )

    def __str__(self):
        return f'{self.first_name} {self.last_name}'

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Список пользователей'
        ordering = ('email',)


class Shop(models.Model):
    name = models.CharField(max_length=40, verbose_name='Название')
    url = models.URLField(verbose_name='Ссылка', blank=True)
    owner = models.ForeignKey(User, verbose_name='Владелец', null=True,
                               related_name='shops', on_delete=models.CASCADE)
    permissions_order = models.BooleanField(verbose_name='Заказ разрешен',
                                            default=True)

    class Meta:
        verbose_name = 'Магазин'
        verbose_name_plural = 'Список магазинов'
        ordering = ('name',)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=40, verbose_name='Название')
    shops = models.ManyToManyField(Shop, verbose_name='Магазины',
                                   related_name='categories')

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Список категорий'
        ordering = ('name',)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=40, verbose_name='Название')
    category = models.ForeignKey(Category, verbose_name='Категория',
                                    related_name='products',
                                    on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Продукт'
        verbose_name_plural = 'Список продуктов'
        ordering = ('name',)

    def __str__(self):
        return self.name


class ProductInfo(models.Model):
    product = models.ForeignKey(Product, verbose_name='Продукт',
                                   related_name='product_infos',
                                   on_delete=models.CASCADE)
    external_id = models.PositiveIntegerField(verbose_name='Внешний ИД',
                                              default=0, null=False)
    full_name = models.CharField(max_length=60, verbose_name='Полное название')
    shop = models.ForeignKey(Shop, verbose_name='Магазин',
                                related_name='product_infos',
                                on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(verbose_name='Количество')
    retail_price = models.PositiveIntegerField(verbose_name='Розничная цена')
    wholesale_price = models.PositiveIntegerField(verbose_name='Оптовая цена')
    sell_up_to = models.CharField(max_length=10, verbose_name='Продать до',
                                  default='')

    class Meta:
        verbose_name = 'Информация о продукте'
        verbose_name_plural = 'Информационный список о продуктах'
        constraints = [
            models.UniqueConstraint(fields=['product', 'external_id', 'shop'],
                                    name='unique_product_info'),
        ]

    def is_available(self):
        """Проверяет доступность товара"""
        # Проверка магазина
        if not self.shop.permissions_order:
            return False

        # Проверка наличия
        if self.quantity <= 0:
            return False

        # Проверка срока годности
        if ProductUtils.is_product_expired(self):
            return False

        return True

    def get_available_quantity(self):
        """Возвращает доступное количество товара"""
        if not self.is_available():
            return 0
        return self.quantity

    def get_sell_date(self):
        """Возвращает дату продажи как объект date или None"""
        return ProductUtils.parse_date(self.sell_up_to)

    def days_until_expiry(self):
        """Возвращает количество дней до истечения срока годности"""
        sell_date = self.get_sell_date()
        if not sell_date:
            return None

        today = timezone.now().date()
        delta = sell_date - today
        return delta.days


class Parameter(models.Model):
    name = models.CharField(max_length=40, verbose_name='Название')

    class Meta:
        verbose_name = 'Название параметра'
        verbose_name_plural = 'Список названий параметров'
        ordering = ('name',)

    def __str__(self):
        return self.name


class ProductParameter(models.Model):
    product_info = models.ForeignKey(ProductInfo,
                                     verbose_name='Информация о продукте',
                                     related_name='product_parameters',
                                     on_delete=models.CASCADE)
    parameter = models.ForeignKey(Parameter, verbose_name='Параметр',
                                  related_name='product_parameters',
                                  on_delete=models.CASCADE)
    value = models.CharField(max_length=60, verbose_name='Значение')

    class Meta:
        verbose_name = 'Параметр'
        verbose_name_plural = 'Список параметров'
        constraints = [
            models.UniqueConstraint(fields=['product_info', 'parameter'],
                                    name='unique_product_parameter'),
        ]


class Contact(models.Model):
    user = models.ForeignKey(User, verbose_name='Пользователь',
                             related_name='contacts',
                             blank=True, on_delete=models.CASCADE)
    city = models.CharField(max_length=40, verbose_name='Город')
    street = models.CharField(max_length=80, verbose_name='Улица')
    house = models.CharField(max_length=10, verbose_name='Дом', blank=True)
    structure = models.CharField(max_length=10, verbose_name='Корпус',
                                 blank=True)
    apartment = models.CharField(max_length=10, verbose_name='Квартира',
                                 blank=True)

    class Meta:
        verbose_name = 'Контакты пользователя'
        verbose_name_plural = 'Список контактов пользователей'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'city', 'street', 'house'],
                name='unique_user_address'
            )
        ]

    def __str__(self):
        return f'{self.city}, {self.street}, {self.house}'

    def clean(self):
        """Проверяем, что у пользователя не более 5 контактов"""
        if self.user and not self.pk:  # Только при создании нового
            if self.user.contacts.count() >= 5:
                # Разрешаем создание только для дефолтных контактов
                if self.city == 'Не указан' and self.street == 'Не указана':
                    return
                raise ValidationError(
                    'У пользователя может быть не более 5 контактов')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Phone(models.Model):
    user = models.OneToOneField(User, verbose_name='Пользователь',
                                related_name='phones',
                                on_delete=models.CASCADE)
    phone = models.CharField(max_length=20, verbose_name='Телефон',
                             unique=True)

    class Meta:
        verbose_name = 'Телефон'
        verbose_name_plural = 'Список телефонов'
        ordering = ('phone',)

    def __str__(self):
        return str(self.phone)


class Order(models.Model):
    contact = models.ForeignKey(Contact, verbose_name='Контакт',
                                related_name='orders',
                                on_delete=models.CASCADE)
    dt = models.DateTimeField(auto_now_add=True)
    status = models.CharField(choices=STATE_CHOICES, max_length=15,
                             verbose_name='Статус')

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Список заказов'
        ordering = ('-dt',)

    def __str__(self):
        return str(self.dt)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, verbose_name='Заказ',
                              related_name='order_items',
                              on_delete=models.CASCADE)
    product = models.ForeignKey(ProductInfo, verbose_name='Товар',
                                related_name='order_items',
                                on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(verbose_name='Количество')

    class Meta:
        verbose_name = 'Заказанный товар'
        verbose_name_plural = 'Список заказанных товаров'
        constraints = [
            models.UniqueConstraint(fields=['order', 'product'],
                                    name='unique_order_item'),
        ]


class ConfirmEmailToken(models.Model):
    class Meta:
        verbose_name = 'Токен подтверждения Email'
        verbose_name_plural = 'Токены подтверждения Email'

    @staticmethod
    def generate_key():
        """ generates a pseudo random code using os.urandom and
        binascii.hexlify"""
        return get_token_generator().generate_token()

    user = models.ForeignKey(
        User, related_name='confirm_email_tokens',
        on_delete=models.CASCADE,
        verbose_name=_("The User which is associated to this token")
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("When was this token generated")
    )

    # Key field, though it is not the primary key of the model
    key = models.CharField(_("Key"), max_length=64, db_index=True, unique=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super(ConfirmEmailToken, self).save(*args, **kwargs)

    def __str__(self):
        return "Reset token for user {user}".format(user=self.user)
