# backend/image_tasks.py
import os
from io import BytesIO

from celery import shared_task
from django.core.files.base import ContentFile
from PIL import Image

from .models import ProductImage


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def generate_product_thumbnails(self, image_id):
    """
    Генерирует preview (400x400), full_view (1200x1200)
    из оригинального изображения ПОЛНОСТЬЮ АСИНХРОННО.

    Используем потоки BytesIO вместо работы с файловой системой —
    это позволяет Celery работать с in-memory данными.
    """
    try:
        image = ProductImage.objects.select_related('product_info').get(
            id=image_id)
    except ProductImage.DoesNotExist:
        return f'Изображение {image_id} не найдено'

    # Если всё уже сгенерировано — пропускаем
    if image.preview and image.full_view:
        return f'Изображение {image_id} уже полностью обработано'

    try:
        # Открываем оригинал через файловый поток (не блокируем I/O)
        original_path = image.original.path
        with Image.open(original_path) as img:
            # Конвертируем в RGB если нужно (для JPEG-совместимости)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            # === Генерация preview (400x400) ===
            if not image.preview:
                preview_buffer = BytesIO()
                preview_img = img.copy()
                preview_img.thumbnail((400, 400), Image.LANCZOS)
                preview_img.save(preview_buffer, format='WEBP', quality=80)
                preview_buffer.seek(0)
                image.preview.save(
                    f'preview_{image.id}.webp',
                    ContentFile(preview_buffer.read()),
                    save=False
                )
                preview_buffer.close()

            # === Генерация full_view (1200x1200) ===
            if not image.full_view:
                full_buffer = BytesIO()
                full_img = img.copy()
                full_img.thumbnail((1200, 1200), Image.LANCZOS)
                full_img.save(full_buffer, format='WEBP', quality=85)
                full_buffer.seek(0)
                image.full_view.save(
                    f'full_{image.id}.webp',
                    ContentFile(full_buffer.read()),
                    save=False
                )
                full_buffer.close()

                # Сохраняем модель (только обновлённые поля)
        image.save(update_fields=['preview', 'full_view'])

        return (
            f'Изображение {image_id} обработано: '
            f'preview={bool(image.preview)}, '
            f'full_view={bool(image.full_view)}'
        )

    except Exception as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3)
def bulk_generate_thumbnails(self, image_ids):
    """
    Массовая генерация миниатюр для нескольких изображений.
    Запускается одной задачей.
    """
    results = []
    for image_id in image_ids:
        try:
            result = generate_product_thumbnails(image_id)
            results.append(
                {'id': image_id, 'status': 'success', 'result': result})
        except Exception as exc:
            results.append(
                {'id': image_id, 'status': 'error', 'error': str(exc)})

    return {
        'total': len(image_ids),
        'success': sum(1 for r in results if r['status'] == 'success'),
        'errors': sum(1 for r in results if r['status'] == 'error'),
        'details': results
    }
