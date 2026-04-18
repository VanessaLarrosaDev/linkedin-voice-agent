"""
telegram_bot.py — Gestión del bot de Telegram.

Envía mensajes a Vanessa y recibe sus respuestas.
Usa python-telegram-bot en modo polling.
"""

import asyncio
import os

from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Cola para pasar mensajes de Telegram al orquestador (main.py)
respuesta_queue: asyncio.Queue[str] = asyncio.Queue()

# Callback que main.py registra para procesar mensajes entrantes
_on_message_callback = None

# Foto pendiente de publicar (se establece cuando Vanessa adjunta una imagen)
_pending_photo: dict | None = None


def set_message_callback(callback) -> None:
    """Registra un callback que se ejecuta al recibir un mensaje de Vanessa."""
    global _on_message_callback
    _on_message_callback = callback


async def enviar_mensaje(texto: str) -> None:
    """Envía un mensaje a Vanessa por Telegram."""
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=texto)


async def enviar_y_esperar_respuesta(texto: str, timeout: int = 3600) -> str:
    """
    Envía un mensaje y espera la respuesta de Vanessa.
    Timeout por defecto: 1 hora.
    """
    # Limpiar la cola antes de enviar
    while not respuesta_queue.empty():
        respuesta_queue.get_nowait()

    await enviar_mensaje(texto)

    try:
        respuesta = await asyncio.wait_for(respuesta_queue.get(), timeout=timeout)
        return respuesta.strip()
    except asyncio.TimeoutError:
        return ""


def get_pending_photo() -> dict | None:
    """Devuelve y limpia la foto pendiente (file_id). Llamar justo antes de publicar."""
    global _pending_photo
    photo = _pending_photo
    _pending_photo = None
    return photo


async def _handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para mensajes con foto adjunta."""
    if not update.message or not update.message.photo:
        return

    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        return

    global _pending_photo
    _pending_photo = {"file_id": update.message.photo[-1].file_id}

    caption = (update.message.caption or "").strip()
    texto_cola = caption if caption else "PUBLICAR"
    await respuesta_queue.put(texto_cola)

    if _on_message_callback and caption:
        await _on_message_callback(caption)


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler interno para mensajes entrantes de Telegram."""
    if not update.message or not update.message.text:
        return

    # Solo procesar mensajes del chat autorizado
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        return

    texto = update.message.text.strip()

    # Poner en la cola para enviar_y_esperar_respuesta
    await respuesta_queue.put(texto)

    # Ejecutar callback si está registrado (para modo manual)
    if _on_message_callback:
        await _on_message_callback(texto)


async def _start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para el comando /start."""
    if update.message:
        await update.message.reply_text(
            "¡Hola Vanessa! Soy tu asistente de LinkedIn.\n\n"
            "Puedes enviarme un tema en cualquier momento y "
            "generaré un post para ti."
        )


def crear_app() -> Application:
    """Crea y configura la Application de Telegram."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", _start_command))
    app.add_handler(MessageHandler(filters.PHOTO, _handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
    return app


# ══════════════════════════════════════════════════════════════
# INSTRUCCIONES
# ══════════════════════════════════════════════════════════════
# Bot de Telegram para comunicarse con Vanessa.
#
# Cómo crear el bot:
# 1. Abre Telegram y busca @BotFather
# 2. Envía /newbot
# 3. Elige un nombre (ej: "LinkedIn Voice Agent")
# 4. Elige un username (ej: "vanessa_linkedin_bot")
# 5. BotFather te dará el token → ponlo en .env como TELEGRAM_BOT_TOKEN
# 6. Envía un mensaje a tu bot
# 7. Visita https://api.telegram.org/bot<TOKEN>/getUpdates
# 8. Copia el chat_id → ponlo en .env como TELEGRAM_CHAT_ID
#
# Uso desde main.py:
#   from telegram_bot import enviar_mensaje, enviar_y_esperar_respuesta
#
#   await enviar_mensaje("Hola Vanessa!")
#   respuesta = await enviar_y_esperar_respuesta("¿Tema 1, 2 o 3?")
# ══════════════════════════════════════════════════════════════
