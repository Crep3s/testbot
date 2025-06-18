import json
import os
import zipfile
import io
from telegram import InputFile
import config

def load_json(filename, default=None):
    if default is None:
        default = {}
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return default
    return default

def save_json(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def create_backup_zip():
    """Создает ZIP-архив с данными в памяти и возвращает его как BytesIO объект."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for fname in os.listdir(config.DATA_DIR):
            if fname.endswith(".json"):
                zipf.write(os.path.join(config.DATA_DIR, fname), arcname=fname)
    buffer.seek(0)
    return buffer

async def restore_from_zip(file):
    """Распаковывает ZIP-архив с данными."""
    zip_path = os.path.join(config.DATA_DIR, "restore_temp.zip")
    await file.download_to_drive(zip_path)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(config.DATA_DIR)
        return True, "✅ Бекап відновлено успішно."
    except zipfile.BadZipFile:
        return False, "❌ Помилка: файл не є дійсним ZIP."
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)