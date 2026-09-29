import asyncio
import base64
import logging
import os
import tempfile
from io import BytesIO

import httpx
from fastapi import FastAPI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("povod-photo-bot")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PROXYAPI_KEY = os.environ["PROXYAPI_KEY"]
PROXYAPI_URL = "https://api.proxyapi.ru/v1/images/edits"
MODEL = os.getenv("IMAGE_MODEL", "openai/gpt-image-1")
IMAGE_QUALITY = os.getenv("IMAGE_QUALITY", "medium")
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "1024x1536")

PROMPT = """Отредактируй предоставленную фотографию товара для премиального интернет-магазина цветов и подарков.

КРИТИЧЕСКИ ВАЖНО: исходный товар является главным объектом изображения. Максимально точно сохрани сам букет, композицию, корзину или подарок из исходной фотографии.

Не меняй состав букета. Не добавляй и не удаляй цветы, растения, упаковку, ленты, декоративные элементы или товары. Не меняй количество видимых цветов, их разновидности и основные цвета. Сохрани форму, пропорции, размер и характер исходной композиции. Товар должен оставаться узнаваемым и максимально соответствовать тому, что реально получит покупатель.

Замени исходный фон на премиальный минималистичный студийный интерьер в светло-серой нейтральной гамме. Фон спокойный, современный, дорогой, без лишних предметов, надписей и логотипов.

Создай естественное направленное освещение, похожее на мягкий дневной свет из большого окна. Добавь реалистичные мягкие тени от модели и букета. Изображение должно выглядеть как настоящая профессиональная fashion/lifestyle фотосъёмка, а не как AI-генерация.

Добавь стильную взрослую женщину-модель 25–35 лет с современной европейской внешностью и естественным макияжем. Ухоженная, элегантная, премиальный образ без чрезмерной гламурности.

Одежда модели: современный минимализм — чёрный, графитовый, молочный или бежевый жакет, костюм или платье без логотипов и крупных принтов.

Модель естественно держит исходный товар в руках. Поза расслабленная и эстетичная. Руки анатомически корректные. Букет располагается естественно относительно тела и имеет реалистичный масштаб.

Главный визуальный акцент — товар, а не модель. Букет или композиция должны занимать значительную часть кадра и хорошо читаться. Не закрывай руками основные цветы и декоративные элементы.

Не добавляй текст, логотипы, водяные знаки, ценники или брендинг.

Стиль результата: premium editorial photography, contemporary luxury flower brand, clean European aesthetic, realistic commercial photography, natural skin texture, realistic flowers, high-end studio lighting.

Сохрани вертикальную композицию исходного изображения, если она подходит для товара. Результат должен быть пригоден для карточки товара интернет-магазина, социальных сетей и рекламных материалов.

PRESERVATION PRIORITY: product fidelity is more important than artistic creativity. If there is a conflict, preserve the original product."""

web = FastAPI(title="Povod Photo Bot")

@web.get("/")
async def health():
    return {"status": "ok", "service": "Povod Photo Bot"}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришлите фотографию букета или товара. Я сохраню товар максимально близко к оригиналу, "
        "заменю фон и добавлю модель."
    )

async def edit_image(image_bytes: bytes, filename: str = "photo.jpg") -> bytes:
    headers = {"Authorization": f"Bearer {PROXYAPI_KEY}"}
    data = {
        "model": MODEL,
        "prompt": PROMPT,
        "size": IMAGE_SIZE,
        "quality": IMAGE_QUALITY,
        "n": "1",
    }
    files = {"image": (filename, image_bytes, "image/jpeg")}

    timeout = httpx.Timeout(300.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(PROXYAPI_URL, headers=headers, data=data, files=files)
        response.raise_for_status()
        payload = response.json()

    return base64.b64decode(payload["data"][0]["b64_json"])

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    status = await msg.reply_text("Фото получила. Обрабатываю — это может занять несколько минут.")

    try:
        if msg.photo:
            tg_file = await msg.photo[-1].get_file()
            filename = "photo.jpg"
        elif msg.document and (msg.document.mime_type or "").startswith("image/"):
            tg_file = await msg.document.get_file()
            filename = msg.document.file_name or "photo.jpg"
        else:
            await status.edit_text("Пришлите фотографию как фото или файл.")
            return

        buf = BytesIO()
        await tg_file.download_to_memory(out=buf)
        result = await edit_image(buf.getvalue(), filename)

        await msg.reply_document(
            document=BytesIO(result),
            filename="povod_edited.png",
            caption="Готово. Отправляю файлом, чтобы Telegram не ухудшал качество."
        )
        await status.delete()

    except httpx.HTTPStatusError as exc:
        logger.exception("ProxyAPI HTTP error")
        body = exc.response.text[:800] if exc.response is not None else ""
        await status.edit_text(f"ProxyAPI вернул ошибку. Код: {exc.response.status_code}. {body}")
    except Exception:
        logger.exception("Image processing failed")
        await status.edit_text("Не получилось обработать фото. Попробуйте ещё раз чуть позже.")

async def run_telegram():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo))
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot started")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

@web.on_event("startup")
async def startup_event():
    asyncio.create_task(run_telegram())
