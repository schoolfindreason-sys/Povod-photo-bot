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
Создай премиальную рекламную фотографию на основе предоставленного
изображения товара для интернет-магазина цветов и подарков.

ГЛАВНЫЙ ПРИОРИТЕТ — ИСХОДНЫЙ ТОВАР.

Максимально точно сохрани реальный букет, композицию, корзину
или подарок с исходной фотографии.

Сохрани исходный состав товара.

Сохрани количество и разновидности видимых цветов, фруктов,
продуктов, упаковки и декоративных элементов.

Сохрани основные цвета, форму, пропорции, объём и характер композиции.

Товар на готовой фотографии должен максимально соответствовать
тому, что покупатель получит в реальности.

Если художественная красота изображения конфликтует
с точностью товара — всегда выбирай точность товара.


ВИЗУАЛЬНАЯ КОНЦЕПЦИЯ

Фотография должна выглядеть как рекламная съёмка дорогого
современного европейского flower & lifestyle бренда.

Эстетика:
luxury beauty campaign,
premium lifestyle editorial,
European fashion photography,
soft glamorous styling,
feminine luxury aesthetic,
high-end commercial photography.

Кадр светлый, воздушный, дорогой и современный.


МОДЕЛЬ — ОБЯЗАТЕЛЬНЫЙ ОБРАЗ

Добавь красивую женственную взрослую женщину-модель
примерно 25–35 лет.

Модель должна выглядеть как героиня современной
европейской luxury beauty campaign.

У неё:

длинные распущенные волосы;

объёмная профессиональная укладка;

крупные естественные мягкие волны;

ухоженные блестящие волосы;

мягкие женственные черты лица;

выразительные глаза;

ухоженная естественная кожа;

элегантный профессиональный beauty-макияж;

дорогой современный женственный образ.

Волосы обязательно распущенные и объёмные.

Образ модели должен напоминать премиальную журнальную
beauty/lifestyle фотосессию.


ОДЕЖДА — ОБЯЗАТЕЛЬНЫЙ ОБРАЗ

Модель одета в элегантный светлый кремовый жакет
или костюм оттенка warm ivory / cream / champagne.

Основной предпочтительный цвет одежды — CREAM / IVORY.

Ткань и крой выглядят дорого и современно.

Под жакетом светлый нейтральный топ.

Добавь небольшие элегантные золотые серьги.

Образ мягкий, женственный, светлый и премиальный.


ПОЗА

Модель естественно держит исходный товар двумя руками.

Поза расслабленная и эстетичная.

Положение рук естественное.

Пальцы и кисти анатомически корректные.

Товар расположен естественно относительно тела модели.

Сохрани реалистичный масштаб товара.

Модель взаимодействует именно с исходным товаром,
а не с его новой интерпретацией.


КОМПОЗИЦИЯ

Главный визуальный объект фотографии — ТОВАР.

Товар должен занимать значительную часть изображения
и сразу привлекать внимание.

Лицо и образ модели являются эстетическим дополнением,
но не конкурируют с товаром.

Руки модели не закрывают важные элементы композиции.

Сохрани вертикальный формат, подходящий для карточки товара
и социальных сетей.


ФОН

Используй светлый премиальный минималистичный фон.

Современный светло-серый, warm grey или мягкий neutral beige
студийный интерьер.

Фон спокойный и дорогой.

Минимум предметов в кадре.

Фон слегка размыт и не отвлекает внимание от товара и модели.


СВЕТ

Мягкий естественный дневной свет,
как от большого окна профессиональной фотостудии.

Мягкие реалистичные тени.

Красивый свет на лице модели.

Естественная текстура кожи.

Реалистичная фактура цветов, фруктов, упаковки и материалов.

Профессиональная коммерческая фотография высокого класса.


ФИНАЛЬНЫЙ ВИЗУАЛЬНЫЙ ОРИЕНТИР

Beautiful feminine European model,
long loose voluminous softly waved hair,
cream ivory tailored blazer,
minimal gold earrings,
natural luxury beauty makeup,
soft daylight,
premium European flower brand campaign,
luxury lifestyle editorial,
elegant feminine styling,
expensive sophisticated appearance,
photorealistic commercial photography.

Без текста, ценников, логотипов и водяных знаков.


PRESERVATION PRIORITY:

Product fidelity is more important than artistic creativity.

Preserve the original product as accurately as possible.
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
# STARTUP
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
        drop_pending_updates=False,
    )

    logger.info(
        "Telegram webhook configured: %s",
        WEBHOOK_URL,
    )


# ============================================================
# SHUTDOWN
# IMPORTANT:
# DO NOT DELETE THE TELEGRAM WEBHOOK HERE.
# Render Free may put the service to sleep.
# The webhook must remain registered so Telegram can wake it.
# ============================================================

@web.on_event("shutdown")
async def shutdown_event():

    logger.info(
        "Stopping Telegram application "
        "without deleting webhook"
    )

    await telegram_app.stop()
    await telegram_app.shutdown()
