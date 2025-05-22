import os
import whisper
import tempfile
import warnings
from contextlib import asynccontextmanager
from http import HTTPStatus
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters

import httpx
from functools import wraps

# Suppress CPU fp16 warnings and force INT8 compute for performance
warnings.filterwarnings(
    "ignore",
    message="FP16 is not supported on CPU; using FP32 instead"
)
# Load Whisper model for transcription on CPU
whisper_model = whisper.load_model("base", device="cpu")

# Whitelist configuration
ALLOWED_USER_ID = 5900777801
ALLOWED_CHAT_ID = -1002557754749

def requires_permission(func):
    @wraps(func)
    async def wrapper(update, context):
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        if user_id != ALLOWED_USER_ID and chat_id != ALLOWED_CHAT_ID:
            await update.message.reply_text("No tienes permiso")
            return
        return await func(update, context)
    return wrapper

# Moderation: delete messages containing forbidden word "idiota"
async def moderation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    if "idiota" in text.lower():
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
        user_mention = update.effective_user.first_name or update.effective_user.username
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"<a href=\"tg://user?id={update.effective_user.id}\">{user_mention}</a>, oye cabrón, no mames, no puedes decir groserías en este grupo, pendejo.",
            parse_mode="HTML"
        )
        return

load_dotenv()
TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_DOMAIN: str = os.getenv('RAILWAY_PUBLIC_DOMAIN')
print(TELEGRAM_BOT_TOKEN)
print(WEBHOOK_DOMAIN)

# Build the Telegram Bot application
bot_builder = (
    Application.builder()
    .token(TELEGRAM_BOT_TOKEN)
    .updater(None)
    .build()
)

bot_builder.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, moderation), group=0)

import io
import tempfile

@requires_permission
async def transcribe_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Transcribe voice messages up to 1 minute using local Whisper model."""
    voice = update.message.voice
    if not voice:
        return
    if voice.duration > 60:
        await update.message.reply_text("El audio supera el límite de 1 minuto.")
        return
    file = await context.bot.get_file(voice.file_id)
    data = await file.download_as_bytearray()
    bio = io.BytesIO(data)
    # Write to a temporary file for Whisper
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp.write(bio.read())
        tmp_path = tmp.name
    result = whisper_model.transcribe(tmp_path)
    text = result.get("text", "").strip()
    os.remove(tmp_path)
    await update.message.reply_text(f"🎙️ Transcripción:\n{text}")

# Register transcription handler at group 1
bot_builder.add_handler(MessageHandler(filters.VOICE, transcribe_voice), group=1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """ Sets the webhook for the Telegram Bot and manages its lifecycle (start/stop). """
    await bot_builder.bot.setWebhook(url=WEBHOOK_DOMAIN)
    async with bot_builder:
        await bot_builder.start()
        yield
        await bot_builder.stop()


app = FastAPI(lifespan=lifespan)


@app.post("/")
async def process_update(request: Request):
    """ Handles incoming Telegram updates and processes them with the bot. """
    message = await request.json()
    update = Update.de_json(data=message, bot=bot_builder.bot)
    await bot_builder.process_update(update)
    return Response(status_code=HTTPStatus.OK)


@requires_permission
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """ Handles the /start command by sending a "Hello world!" message in response. """
    await update.message.reply_text(f"Hola {update.message.from_user.first_name}!\nBienvenido al bot de prueba de Telegram.\n\n"
                                    "Este bot está alojado en Railway y utiliza FastAPI como framework web.\n\n"
                                    "¡Espero que lo disfrutes!")


@requires_permission
async def echo(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    await update.message.reply_text(update.message.text )


@requires_permission
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Replies with a list of available commands."""
    help_text = (
        "Aquí van los comandos disponibles:\n"
        "/start - Inicia el bot y muestra un saludo\n"
        "/ayuda - Muestra esta ayuda\n"
        "/seikened <username> - Obtiene info de GitHub del usuario indicado"
    )
    await update.message.reply_text(help_text)

@requires_permission
async def seikened_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Obtiene info de GitHub del usuario seikened."""
    args = context.args
    if not args:
        await update.message.reply_text("Uso: /seikened <username>")
        return
    username = args[0]
    url = f"https://api.github.com/users/{username}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        data = resp.json()
    if resp.status_code != 200:
        await update.message.reply_text(f"Usuario {username} no encontrado")
        return
    name = data.get("name") or data.get("login")
    avatar_url = data.get("avatar_url")
    await update.message.reply_photo(photo=avatar_url, caption=name)

bot_builder.add_handler(CommandHandler(command="ayuda", callback=help_command))
bot_builder.add_handler(CommandHandler(command="start", callback=start))
bot_builder.add_handler(CommandHandler(command="seikened", callback=seikened_command))
bot_builder.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND, callback=echo))
