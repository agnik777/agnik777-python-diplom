# backend/models.py
import os
import uuid
import logging
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from django_rest_passwordreset.tokens import get_token_generator
from imagekit.models import ImageSpecField, ProcessedImageField
from imagekit.processors import ResizeToFill, ResizeToFit, SmartResize, Transpose
from imagekit.cachefiles import ImageCacheFile

from .utils import ProductUtils


logger = logging.getLogger(__name__)

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


def user_avatar_path(instance, filename):
    """
    Генерирует путь для сохранения аватара пользователя.
    Формат: avatars/user_{id}/avatar_{filename}
    """
    import uuid
    ext = filename.split('.')[-1] if '.' in filename else 'jpg'
    unique_name = f'{uuid.uuid4().hex}.{ext}'
    return f'avatars/user_{instance.id}/{unique_name}'


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
        unique=False,
        blank=True,
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
    avatar = models.ImageField(
        verbose_name='Аватар',
        upload_to=user_avatar_path,
        blank=True,
        null=True,
        help_text=_('Изображение аватара пользователя. '
                    'Рекомендуемый размер: 200x200 пикселей.'),
    )
    avatar_url = models.URLField(
        verbose_name='URL аватара',
        max_length=500,
        blank=True,
        null=True,
        help_text=_('Ссылка на аватар из социальной сети'),
    )
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
        return f'{self.first_name} {self.last_name}'.strip() or self.email

    @property
    def avatar_display_url(self):
        """
        Возвращает URL для отображения аватара.
        Приоритет: загруженный файл > URL из соцсети > заглушка.
        """
        if self.avatar:
            return self.avatar.url
        if self.avatar_url:
            return self.avatar_url
        return None

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


def product_image_path(instance, filename):
    """
    Генерирует путь для сохранения изображения товара.
    Формат: products/product_{id}/images/{uuid}.{ext}
    """
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
    unique_name = f'{uuid.uuid4().hex}.{ext}'
    return f'products/product_{instance.product_info_id}/images/{unique_name}'

def validate_image_size(file):
    """Валидатор: максимальный размер файла 10 МБ"""
    max_size = 10 * 1024 * 1024  # 10 MB
    if file.size > max_size:
        raise ValidationError(
            f'Размер файла не должен превышать 10 МБ. '
            f'Текущий размер: {file.size / 1024 / 1024:.1f} МБ'
        )


class ProductImage(models.Model):
    """
    Модель для дополнительных изображений товара.
    Один товар → много фото.
    """
    product_info = models.ForeignKey(
        ProductInfo,
        verbose_name='Товар',
        on_delete=models.CASCADE,
        related_name='images'
    )

    # Оригинал изображения (загруженный файл)
    original = ProcessedImageField(
        verbose_name='Оригинал',
        upload_to=product_image_path,
        processors=[ResizeToFit(1920, 1920)],
        format='WEBP',
        options={'quality': 90},
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp']),
            validate_image_size
        ],
        help_text='Оригинальное изображение (макс. 1920x1920px)'
    )

    # Миниатюры (ImageSpecField — ленивая генерация)
    thumbnail_small = ImageSpecField(
        source='original',
        processors=[ResizeToFill(100, 100)],
        format='WEBP',
        options={'quality': 70}
    )
    thumbnail_medium = ImageSpecField(
        source='original',
        processors=[SmartResize(300, 300)],
        format='WEBP',
        options={'quality': 80}
    )
    thumbnail_large = ImageSpecField(
        source='original',
        processors=[ResizeToFit(800, 800)],
        format='WEBP',
        options={'quality': 85}
    )

    # preview, full_view — ProcessedImageField без source
    # Заполняются через Celery-задачу
    preview = ProcessedImageField(
        verbose_name='Превью',
        upload_to=product_image_path,
        processors=[ResizeToFit(400, 400)],
        format='WEBP',
        options={'quality': 80},
        null=True,
        blank=True,
        help_text='Предварительный просмотр 400x400'
    )
    full_view = ProcessedImageField(
        verbose_name='Полный просмотр',
        upload_to=product_image_path,
        processors=[ResizeToFit(1200, 1200)],
        format='WEBP',
        options={'quality': 85},
        null=True,
        blank=True,
        help_text='Фото товара 1200x1200px'
    )

    is_main = models.BooleanField(
        verbose_name='Основное фото',
        default=False,
        help_text='Отметьте, если это главное фото товара'
    )
    alt_text = models.CharField(
        verbose_name='Alt-текст',
        max_length=255,
        blank=True,
        help_text='Текст для SEO и accessibility'
    )
    sort_order = models.PositiveIntegerField(
        verbose_name='Порядок сортировки',
        default=0,
        help_text='Чем меньше число, тем выше позиция'
    )
    uploaded_at = models.DateTimeField(
        verbose_name='Дата загрузки',
        auto_now_add=True
    )

    class Meta:
        verbose_name = 'Изображение товара'
        verbose_name_plural = 'Изображения товаров'
        ordering = ('sort_order', 'uploaded_at')

    def __str__(self):
        return f'Фото {self.id} для "{self.product_info.full_name}"'

    def save(self, *args, **kwargs):
        """
        Переопределяем save:
        1. Автоматически устанавливаем is_main для первого изображения
        2. НЕ запускаем Celery здесь — это делает ViewSet!
        """
        is_new = self.pk is None

        # Первое изображение → основное
        if is_new and not self.product_info.images.exists():
            self.is_main = True

        super().save(*args, **kwargs)

    @property
    def all_thumbnails(self):
        """Возвращает словарь со всеми размерами миниатюр"""
        return {
            'small': self.thumbnail_small.url if self.thumbnail_small else None,
            'medium': self.thumbnail_medium.url if self.thumbnail_medium else None,
            'large': self.thumbnail_large.url if self.thumbnail_large else None,
            'preview': self.preview.url if self.preview else None,
            'full': self.full_view.url if self.full_view else None,
            'original': self.original.url if self.original else None,
        }

    def delete(self, *args, **kwargs):
        """При удалении записи удаляем и файлы с диска"""
        storage = self.original.storage

        # Удаляем все файлы
        for field_name in ['original', 'preview', 'full_view']:
            field = getattr(self, field_name, None)
            if field and field.name:
                try:
                    storage.delete(field.name)
                except Exception:
                    pass

        # Удаляем кеш imagekit
        for spec_name in ['thumbnail_small', 'thumbnail_medium',
                          'thumbnail_large']:
            try:
                spec = getattr(self.__class__, spec_name, None)
                if spec:
                    cache_file = ImageCacheFile(spec, self)
                    if cache_file and cache_file.name:
                        storage.delete(cache_file.name)
            except Exception:
                pass

        super().delete(*args, **kwargs)


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
