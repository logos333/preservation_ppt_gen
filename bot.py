"""
Telegram Bot — обработчики команд и сообщений.
Роутер для приёма фотографий и управления генерацией презентаций.
"""

import os
import shutil
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from aiogram import Router, Bot, F, BaseMiddleware
from aiogram.types import Message, FSInputFile, TelegramObject
from aiogram.filters import Command

from llm_ocr import rename_photo_with_llm, LLM_MODEL
from ppt_gen import generate_presentation

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================

logger = logging.getLogger(__name__)

PHOTOS_BASE_DIR: str = "photos"
IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg")
ALLOWED_CHAT_IDS: set[int] = {
    328556498,  # Temur Kh
    7080816340, # Temur Khoshimov
    6340353400  # Vitaliy Chernikov
}

HELP_TEXT: str = (
    "📋 <b>Доступные команды:</b>\n\n"
    "/time — Текущая дата и время\n"
    "/checkphotos — Показать список фото в текущей папке\n"
    "/makeppt — Обработать фото через LLM и сгенерировать презентацию\n"
    "/cleardata — Удалить все фото из папки photos\n"
    "/getppt — Скачать текущий шаблон презентации (template_{user_id}.pptx)\n"
    "/get_llm_model — Показать текущую LLM-модель\n"
    "/help — Список команд\n\n"
    "💡 <i>Чтобы загрузить новый шаблон, просто отправьте файл с именем <code>template_{user_id}.pptx</code>.\n"
    "Чтобы удалить сохранённое фото, ответьте на него словом <code>delete</code>.</i>"
)


# ==========================================
# MIDDLEWARE
# ==========================================

class ChatIdWhitelistMiddleware(BaseMiddleware):
    """Пропускает только сообщения из разрешённых чатов."""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        if isinstance(event, Message) and event.chat.id not in ALLOWED_CHAT_IDS:
            logger.warning(f"Заблокирован доступ для chat_id={event.chat.id}")
            return
        return await handler(event, data)


router = Router()
router.message.middleware(ChatIdWhitelistMiddleware())


# ==========================================
# УТИЛИТЫ
# ==========================================

def _get_today_folder() -> Path:
    """Возвращает путь к папке photos/{сегодняшняя дата}, создаёт если нет."""
    today = datetime.now().strftime("%d-%B-%Y")
    folder = Path(PHOTOS_BASE_DIR) / today
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _get_photos_in_folder(folder: Path) -> list[Path]:
    """Возвращает список фото в папке."""
    if not folder.exists():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


# ==========================================
# ОБРАБОТЧИК ФОТОГРАФИЙ
# ==========================================

@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot) -> None:
    """Сохраняет присланное фото в photos/{date}/. Если есть caption — использует как имя."""
    today_folder = _get_today_folder()

    # Берём фото максимального размера
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)

    # Определяем имя файла
    if message.caption:
        # Если есть подпись — используем как имя файла
        caption = message.caption.strip()
        if not any(caption.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
            caption += ".jpg"
        filename = caption
    else:
        # Без подписи — временное имя с message_id для обратной связи при /makeppt
        filename = f"temp_{message.message_id}.jpg"

    save_path = today_folder / filename

    await bot.download_file(file.file_path, destination=str(save_path))

    if message.caption:
        await message.reply(
            f"✅ Фото сохранено как <code>{filename}</code>\n"
            f"📁 Папка: <code>{today_folder}</code>"
        )
    else:
        await message.reply(
            f"✅ Фото сохранено (будет обработано LLM при /makeppt)\n"
            f"📁 Папка: <code>{today_folder}</code>"
        )


# ==========================================
# ОБРАБОТЧИК УДАЛЕНИЯ ФОТО (REPLY "delete")
# ==========================================

@router.message(F.text.lower() == "delete")
async def handle_delete_reply(message: Message) -> None:
    """Удаляет фото из файловой системы, если пользователь ответил 'delete' на сообщение с фото."""
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("⚠️ Чтобы удалить фото, ответьте на само сообщение с фотографией словом 'delete'.")
        return

    today_folder = _get_today_folder()
    replied_msg = message.reply_to_message

    # Восстанавливаем имя файла так же, как при сохранении
    if replied_msg.caption:
        caption = replied_msg.caption.strip()
        if not any(caption.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
            caption += ".jpg"
        filename = caption
    else:
        filename = f"temp_{replied_msg.message_id}.jpg"

    file_path = today_folder / filename

    if file_path.exists():
        file_path.unlink()
        await message.reply(f"🗑️ Фото <code>{filename}</code> успешно удалено с сервера.")
        # Пытаемся удалить само сообщение с фото из чата
        try:
            await replied_msg.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение {replied_msg.message_id} в Telegram: {e}")
    else:
        await message.reply(f"⚠️ Фото <code>{filename}</code> не найдено на сервере (возможно, уже удалено или находится в папке за другой день).")


# ==========================================
# ОБРАБОТЧИК ШАБЛОНА (TEMPLATE.PPTX)
# ==========================================

@router.message(F.document & F.document.file_name.endswith(".pptx"))
async def handle_template_upload(message: Message, bot: Bot) -> None:
    """Обновляет файл template.pptx."""
    doc = message.document
    if doc.file_name.lower() == f"template_{message.from_user.id}.pptx":
        try:
            file = await bot.get_file(doc.file_id)
            await bot.download_file(file.file_path, destination=f"template_{message.from_user.id}.pptx")
            await message.reply(f"✅ Шаблон <code>template_{message.from_user.id}.pptx</code> успешно обновлён!")
        except Exception as e:
            logger.error(f"Ошибка загрузки шаблона: {e}")
            await message.reply(f"❌ Произошла ошибка при загрузке файла: {type(e).__name__}\nПодробнее: {e}")
    else:
        await message.reply(
            f"⚠️ Пожалуйста, переименуйте ваш файл в <code>template_{message.from_user.id}.pptx</code> перед отправкой, "
            "если хотите обновить шаблон."
        )


# ==========================================
# КОМАНДЫ
# ==========================================

@router.message(Command("time"))
async def cmd_time(message: Message) -> None:
    """Выводит текущую дату и время."""
    now = datetime.now().strftime("%d-%B-%Y %H:%M:%S")
    await message.reply(f"🕐 Текущая дата и время: <code>{now}</code>")


@router.message(Command("makeppt"))
async def cmd_makeppt(message: Message) -> None:
    """Обрабатывает все фото через LLM, затем генерирует презентацию."""
    today_folder = _get_today_folder()
    photos = _get_photos_in_folder(today_folder)

    if not photos:
        await message.reply("❌ Нет фото для обработки. Отправьте фотографии сначала.")
        return

    # Шаг 1: LLM-обработка фото без подписей (у них имена temp_{message_id})
    temp_photos = [p for p in photos if p.name.startswith("temp_")]
    if temp_photos:
        status_msg = await message.reply(
            f"🔄 Обработка {len(temp_photos)} фото через LLM..."
        )
        for i, photo_path in enumerate(temp_photos, start=1):
            # Извлекаем message_id из имени файла для ответа на оригинальное сообщение
            orig_msg_id = int(photo_path.stem.split("_", 1)[1]) if "_" in photo_path.stem else None
            try:
                new_path = await asyncio.to_thread(
                    rename_photo_with_llm, str(photo_path)
                )
                new_name = Path(new_path).name
                logger.info(f"LLM OCR [{i}/{len(temp_photos)}]: {photo_path.name} → {new_name}")
                # Отвечаем на оригинальное фото с результатом
                if orig_msg_id:
                    await message.bot.send_message(
                        chat_id=message.chat.id,
                        text=f"🏷 Распознано: <code>{new_name}</code>",
                        reply_to_message_id=orig_msg_id,
                    )
            except Exception as e:
                logger.error(f"Ошибка LLM OCR для {photo_path.name}: {e}")
                await message.reply(f"⚠️ Ошибка при обработке {photo_path.name}: {e}")

        await status_msg.edit_text(
            f"✅ LLM-обработка завершена ({len(temp_photos)} фото)"
        )

    # Шаг 2: Генерация презентации
    await message.reply("📊 Генерация презентации...")
    try:
        output_path, report = await asyncio.to_thread(
            generate_presentation, str(today_folder), f"template_{message.from_user.id}.pptx"
        )
        
        # Отправляем файл в чат
        doc = FSInputFile(output_path, filename=Path(output_path).name)
        await message.reply_document(doc, caption="✅ Презентация готова!")
        logger.info(f"Презентация отправлена: {output_path}")

        # Формируем и отправляем отчет о расстановке фото
        report_lines = ["📋 <b>Отчет о генерации:</b>\n"]
        
        if report.get("used"):
            report_lines.append("✅ <b>Размещено на слайдах:</b>")
            for slide_title, photos in report["used"].items():
                report_lines.append(f"  • {slide_title}:")
                for p in photos:
                    report_lines.append(f"      - <code>{p}</code>")
            report_lines.append("")
            
        if report.get("unused"):
            report_lines.append("⚠️ <b>Не найдено соответствий (пропущено):</b>")
            for p in report["unused"]:
                report_lines.append(f"  - <code>{p}</code>")
                
        if len(report_lines) == 1:
            report_lines.append("<i>Слайды не были изменены (теги не совпали)</i>")

        # Отправляем длинный отчет частями, если нужно
        report_text = "\n".join(report_lines)
        for i in range(0, len(report_text), 4000):
            await message.reply(report_text[i:i+4000])

    except Exception as e:
        logger.error(f"Ошибка генерации презентации: {e}")
        await message.reply(f"❌ Ошибка генерации: {e}")


@router.message(Command("checkphotos"))
async def cmd_checkphotos(message: Message) -> None:
    """Выводит список имен файлов в папке за сегодняшний день."""
    today_folder = _get_today_folder()
    photos = _get_photos_in_folder(today_folder)
    
    if not photos:
        await message.reply("📂 Папка пуста.")
        return
        
    lines = [f"📂 <b>Фото на сегодня ({len(photos)}):</b>"]
    for p in photos:
        lines.append(f"• <code>{p.name}</code>")
        
    # Разбиваем на чанки, если список очень длинный
    text = "\n".join(lines)
    for i in range(0, len(text), 4000):
        await message.reply(text[i:i+4000])


@router.message(Command("cleardata"))
async def cmd_cleardata(message: Message) -> None:
    """Удаляет всё содержимое папки photos."""
    photos_dir = Path(PHOTOS_BASE_DIR)
    if photos_dir.exists():
        for item in photos_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        await message.reply("🗑️ Все данные из папки photos удалены.")
    else:
        await message.reply("📁 Папка photos и так пуста.")


@router.message(Command("get_llm_model"))
async def cmd_get_llm_model(message: Message) -> None:
    """Показывает текущую LLM-модель из конфигурации."""
    await message.reply(f"🤖 Текущая LLM-модель: <code>{LLM_MODEL}</code>")


@router.message(Command("getppt"))
async def cmd_getppt(message: Message) -> None:
    """Отправляет текущий шаблон template.pptx."""
    template_path = Path(f"template_{message.from_user.id}.pptx")
    if template_path.exists():
        doc = FSInputFile(template_path, filename=f"template_{message.from_user.id}.pptx")
        await message.reply_document(doc, caption="📁 Текущий шаблон презентации.")
    else:
        await message.reply(f"❌ Шаблон <code>template_{message.from_user.id}.pptx</code> не найден на сервере.")


@router.message(Command("help", "start"))
async def cmd_help(message: Message) -> None:
    """Выводит справку по командам."""
    await message.reply(HELP_TEXT)
