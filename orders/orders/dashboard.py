# orders/dashboard.py
from jet.dashboard.dashboard import Dashboard
from jet.dashboard.modules import (
    AppList,
    RecentActions,
    Feed,
    LinkList,
    ModelList,
)


class CustomIndexDashboard(Dashboard):
    """Кастомная панель управления для Orders API"""

    columns = 3  # Количество колонок (по умолчанию 2)

    def init_with_context(self, context):
        # Колонка 1 — основные модели
        self.children.append(
            ModelList(
                title='Пользователи и магазины',
                models=[
                    'backend.User',
                    'backend.Shop',
                    'backend.Category',
                ],
                column=0,
                order=0,
            )
        )

        self.children.append(
            ModelList(
                title='Товары и заказы',
                models=[
                    'backend.Product',
                    'backend.ProductInfo',
                    'backend.Order',
                ],
                column=0,
                order=1,
            )
        )

        # Колонка 2 — статистика и действия
        self.children.append(
            RecentActions(
                title='Последние действия',
                items=10,  # Показывать 10 последних действий
                column=1,
                order=0,
            )
        )

        self.children.append(
            AppList(
                title='Приложения',
                column=1,
                order=1,
                exclude=('jet', 'jet.dashboard'),
            )
        )

        # Колонка 3 — полезные ссылки и RSS
        self.children.append(
            LinkList(
                title='Полезные ссылки',
                column=2,
                order=0,
                children=[
                    {
                        'title': 'Документация API (Swagger)',
                        'url': '/api/docs/',
                        'external': False,
                        'target': '_blank',
                    },
                    {
                        'title': 'Схема API (ReDoc)',
                        'url': '/api/redoc/',
                        'external': False,
                        'target': '_blank',
                    },
                    {
                        'title': 'Административная панель',
                        'url': '/admin/',
                        'external': False,
                        'target': '_blank',
                    },
                ],
            )
        )

        self.children.append(
            Feed(
                title='Новости Django',
                feed_url='https://www.djangoproject.com/rss/weblog/',
                limit=5,
                column=2,
                order=1,
            )
        )
