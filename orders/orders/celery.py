# orders/celery.py
import os
from celery import Celery


# Устанавливаем модуль настроек Django по умолчанию для Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'orders.settings')

app = Celery('orders')

# Загружаем конфигурацию из Django settings с префиксом CELERY
app.config_from_object('django.conf:settings', namespace='CELERY')

# Автоматически находим и регистрируем задачи из всех файлов tasks.py
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Отладочная задача для проверки работы Celery"""
    print(f'Request: {self.request!r}')
