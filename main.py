import base64
import logging
import os
from io import BytesIO

import httpx
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("povod-photo-bot")


# ============================================================
# SETTINGS
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PROXYAPI_KEY = os.environ["PROXYAPI_KEY"]

PROXYAPI_URL = "https://api.proxyapi.ru/v1/images/edits"

MODEL = os.getenv("IMAGE_MODEL", "openai/gpt-image-1")
IMAGE_QUALITY = os.getenv("IMAGE_QUALITY", "medium")
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "1024x1536")

# Render automatically provides this variable.
RENDER_EXTERNAL_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    "https://povod-photo-bot.onrender.com",
)

WEBHOOK_PATH = "/telegram"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL.rstrip('/')}{WEBHOOK_PATH}"


# ============================================================
# IMAGE PROMPT
# ============================================================

PROMPT = """
Отредактируй предоставленную фотографию товара для премиального
интернет-магазина цветов и подарков.

КРИТИЧЕСКИ ВАЖНО:
исходный товар является главным объектом изображения.

Максимально точно сохрани сам букет, композицию, корзину
или подарок из исходной фотографии.

Не меняй состав букета.
Не добавляй и не удаляй цветы, растения, упаковку, ленты,
декоративные элементы или товары.

Не меняй количество видимых цветов, их разновидности
и основные цвета.

Сохрани форму, пропорции, размер и характер исходной композиции.

Товар должен оставаться узнаваемым и максимально соответствовать
тому, что реально получит покупатель.


ФОН И ОСВЕЩЕНИЕ

Замени исходный фон на премиальный минималистичный студийный
или современный интерьер в светло-серой нейтральной гамме.

Фон спокойный, современный, дорогой, эстетичный,
без лишних предметов, надписей и логотипов.

Создай естественное направленное освещение,
похожее на мягкий дневной свет из большого окна.

Добавь реалистичные мягкие тени от модели и букета.

Изображение должно выглядеть как настоящая профессиональная
fashion / beauty / lifestyle фотосъёмка премиального бренда,
а не как AI-генерация.


МОДЕЛЬ

Добавь красивую стильную взрослую женщину-модель 25–35 лет
с эффектной современной европейской внешностью.

Мягкие женственные черты лица.
Выразительные глаза.
Ухоженная естественная кожа.
Профессиональный естественный beauty-макияж.

Длинные объёмные ухоженные волосы.
Естественная дорогая укладка с мягкими волнами.

Образ женственный, стильный, современный и дорогой,
как в рекламной съёмке премиального европейского
flower / beauty / lifestyle бренда.

Модель НЕ должна выглядеть как строгая офисная сотрудница,
секретарь или женщина в корпоративной фотосессии.

Избегай сухого делового и чрезмерно официального образа.


ОДЕЖДА МОДЕЛИ

Используй только светлую премиальную гамму:

молочный,
ivory,
cream,
champagne,
светло-бежевый.

Предпочтительно:
элегантный кремовый или молочный жакет,
светлый современный костюм,
или лаконичное светлое платье.

НЕ использовать:
чёрную одежду,
графитовую одежду,
тёмно-серую одежду,
траурный образ,
строгий чёрный деловой костюм.

Одежда без логотипов и крупных принтов.

Допустимы минималистичные элегантные золотые серьги.


ПОЗА И ТОВАР

Модель естественно держит исходный товар в руках.

Поза расслабленная, женственная и эстетичная.

Руки анатомически корректные.

Букет располагается естественно относительно тела
и имеет реалистичный масштаб.

Главный визуальный акцент — ТОВАР, а не модель.

Букет или композиция должны занимать значительную часть кадра
и хорошо читаться.

Не закрывай руками основные цветы,
упаковку и декоративные элементы.


СТИЛЬ

Premium editorial photography.
Luxury beauty campaign.
Contemporary European flower brand.
High-end lifestyle photography.
Soft glamorous styling.
Elegant and expensive appearance.
Natural skin texture.
Realistic flowers.
High-end studio lighting.
Clean European aesthetic.

Не добавляй текст, логотипы, водяные знаки,
ценники или дополнительный брендинг.

Сохрани вертикальную композицию исходного изображения,
если она подходит для товара.

Результат должен быть пригоден для карточки товара
интернет-магазина, социальных сетей и рекламных материалов.


PRESERVATION PRIORITY:

Product fidelity is more important than artistic creativity.

If there is any conflict between creating a beautiful image
and accurately preserving the original product,
preserve the original product.
"""


# ============================================================
# FASTAPI
# ============================================================

web = FastAPI(title="Povod Photo Bot")


@web.get("/")
async def health():
    return {
        "status": "ok",
        "service": "Povod Photo Bot",
        "telegram_mode": "webhook",
    }


# ============================================================
# TELEGRAM BOT
# ============================================================

telegram_app = (
    Application.builder()
    .token(TELEGRAM_BOT_TOKEN)
    .updater(None)
    .build()
)


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Пришлите фотографию букета или товара. "
        "Я сохраню товар максимально близко к оригиналу, "
        "заменю фон и добавлю модель."
    )


# ============================================================
# IMAGE EDITING
# ============================================================

async def edit_image(
    image_bytes: bytes,
    filename: str = "photo.jpg",
) -> bytes:

    headers = {
        "Authorization": f"Bearer {PROXYAPI_KEY}"
    }

    data = {
        "model": MODEL,
        "prompt": PROMPT,
        "size": IMAGE_SIZE,
        "quality": IMAGE_QUALITY,
        "n": "1",
    }

    files = {
        "image": (
            filename,
            image_bytes,
            "image/jpeg",
        )
    }

    timeout = httpx.Timeout(
        300.0,
        connect=30.0,
    )

    async with httpx.AsyncClient(
        timeout=timeout
    ) as client:

        response = await client.post(
            PROXYAPI_URL,
            headers=headers,
            data=data,
            files=files,
        )

        response.raise_for_status()

        payload = response.json()

    return base64.b64decode(
        payload["data"][0]["b64_json"]
    )


# ============================================================
# PHOTO HANDLER
# ============================================================

async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    msg = update.message

    if msg is None:
        return

    status = await msg.reply_text(
        "Фото получила. Обрабатываю — "
        "это может занять несколько минут."
    )

    try:

        if msg.photo:

            tg_file = await msg.photo[-1].get_file()
            filename = "photo.jpg"

        elif (
            msg.document
            and (msg.document.mime_type or "").startswith("image/")
        ):

            tg_file = await msg.document.get_file()
            filename = (
                msg.document.file_name
                or "photo.jpg"
            )

        else:

            await status.edit_text(
                "Пришлите фотографию как фото или файл."
            )
            return

        buf = BytesIO()

        await tg_file.download_to_memory(
            out=buf
        )

        result = await edit_image(
            buf.getvalue(),
            filename,
        )

        await msg.reply_document(
            document=BytesIO(result),
            filename="povod_edited.png",
            caption=(
                "Готово. Отправляю файлом, "
                "чтобы Telegram не ухудшал качество."
            ),
        )

        await status.delete()

    except httpx.HTTPStatusError as exc:

        logger.exception(
            "ProxyAPI HTTP error"
        )

        body = (
            exc.response.text[:800]
            if exc.response is not None
            else ""
        )

        code = (
            exc.response.status_code
            if exc.response is not None
            else "unknown"
        )

        await status.edit_text(
            f"ProxyAPI вернул ошибку. "
            f"Код: {code}. {body}"
        )

    except Exception:

        logger.exception(
            "Image processing failed"
        )

        await status.edit_text(
            "Не получилось обработать фото. "
            "Попробуйте ещё раз чуть позже."
        )


telegram_app.add_handler(
    CommandHandler(
        "start",
        start,
    )
)

telegram_app.add_handler(
    MessageHandler(
        filters.PHOTO | filters.Document.IMAGE,
        handle_photo,
    )
)


# ============================================================
# TELEGRAM WEBHOOK
# ============================================================

@web.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
):

    try:

        data = await request.json()

        update = Update.de_json(
            data,
            telegram_app.bot,
        )

        await telegram_app.process_update(
            update
        )

        return Response(
            status_code=200
        )

    except Exception:

        logger.exception(
            "Webhook processing failed"
        )

        return Response(
            status_code=200
        )


# ============================================================
# STARTUP / SHUTDOWN
# ============================================================

@web.on_event("startup")
async def startup_event():

    logger.info(
        "Starting Telegram application"
    )

    await telegram_app.initialize()
    await telegram_app.start()

    await telegram_app.bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True,
    )

    logger.info(
        "Telegram webhook configured: %s",
        WEBHOOK_URL,
    )


@web.on_event("shutdown")
async def shutdown_event():

    logger.info(
        "Stopping Telegram application"
    )

    try:
        await telegram_app.bot.delete_webhook()
    except Exception:
        logger.exception(
            "Could not delete Telegram webhook"
        )

    await telegram_app.stop()
    await telegram_app.shutdown()
