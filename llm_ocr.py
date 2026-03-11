"""
LLM OCR Module — извлечение текста из фотографий через LLM и переименование файлов.
Использует LiteLLM для единого интерфейса ко всем провайдерам (OpenAI, Gemini, Claude и др.).
"""

import os
import re
import sys
import base64
import mimetypes
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import litellm

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================

load_dotenv()

# Модель в формате LiteLLM: "gpt-4o", "gemini/gemini-2.0-flash", "anthropic/claude-sonnet-4-20250514"
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash")

# Список известных тегов для few-shot подсказки
KNOWN_TAGS: list[str] = [
    "D903B-1", "D903B-2", "D903B-3",
    "201EP458-1", "201EP458-2",
    "D303SP-1", "D303SP-2",
    "D304-1", "D304-2", "D304-3",
    "D303LP-1", "D303LP-2",
    "D202-1", "D202-2", "D202-3", "D202-4", "D202-5",
    "201-A204B", "201-A204A",
]

# Промпт для извлечения тега с жёлтой бирки на манометре
EXTRACTION_PROMPT: str = (
    "This image shows a monometer (pressure gauge) with a yellow tag attached to it. "
    "Read the text written on the yellow tag and return it exactly as written. "
    "The tag typically contains an equipment ID like the examples below.\n\n"
    "Known tag examples:\n"
    + "\n".join(f"- {tag}" for tag in KNOWN_TAGS)
    + "\n\n"
    "Return ONLY the tag text that best matches what you see on the yellow tag. "
    "Do NOT add any explanation, quotes, or extra characters — just the tag value."
)

# Отключаем лишние логи LiteLLM
litellm.suppress_debug_info = True


# ==========================================
# УТИЛИТЫ
# ==========================================

def _encode_image_base64(image_path: str) -> str:
    """Кодирует изображение в base64-строку."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_mime_type(image_path: str) -> str:
    """Определяет MIME-тип файла по расширению."""
    mime, _ = mimetypes.guess_type(image_path)
    return mime or "image/jpeg"


def _normalize_dashes(text: str) -> str:
    """Заменяет все Unicode-варианты дефиса/тире на стандартный ASCII дефис '-'."""
    dash_chars = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D"
    return re.sub(f'[{dash_chars}]', '-', text)


def _sanitize_filename(name: str) -> str:
    """Нормализует дефисы и очищает строку от символов, запрещённых в именах файлов."""
    name = _normalize_dashes(name)
    sanitized = re.sub(r'201EP458', '201-EP458', name)
    sanitized = re.sub(r'[^\w\s\-]', '', sanitized)
    sanitized = re.sub(r'\s+', '', sanitized)
    return sanitized[:80] if sanitized else "unnamed"


# ==========================================
# ОСНОВНАЯ ЛОГИКА
# ==========================================

def extract_text_from_image(image_path: str, model: Optional[str] = None) -> str:
    """Отправляет изображение в LLM через LiteLLM и возвращает извлечённый текст."""
    b64_image = _encode_image_base64(image_path)
    mime_type = _get_mime_type(image_path)

    response = litellm.completion(
        model=model or LLM_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_image}"
                        },
                    },
                ],
            }
        ],
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


def rename_photo_with_llm(photo_path: str, model: Optional[str] = None) -> str:
    """
    Отправляет фото в LLM, получает описательный текст,
    переименовывает файл (сохраняя расширение). Возвращает новый путь.
    """
    photo = Path(photo_path)
    if not photo.exists():
        raise FileNotFoundError(f"Файл не найден: {photo_path}")

    print(f"Обработка: {photo.name} → отправка в LLM ({model or LLM_MODEL})...")
    raw_name = extract_text_from_image(str(photo), model)
    clean_name = _sanitize_filename(raw_name)

    new_filename = f"{clean_name}{photo.suffix}"
    new_path = photo.parent / new_filename

    # Если файл с таким именем уже существует — добавляем суффикс
    counter = 1
    while new_path.exists() and new_path != photo:
        new_filename = f"{clean_name}-{counter}{photo.suffix}"
        new_path = photo.parent / new_filename
        counter += 1

    photo.rename(new_path)
    print(f"Переименовано: {photo.name} → {new_filename}")
    return str(new_path)


# ==========================================
# ТОЧКА ВХОДА (для тестирования)
# ==========================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python llm_ocr.py <путь_к_фото> [путь_к_фото ...]")
        sys.exit(1)

    for path in sys.argv[1:]:
        try:
            new_path = rename_photo_with_llm(path)
            print(f"  Результат: {new_path}")
        except Exception as e:
            print(f"  Ошибка для '{path}': {e}")
