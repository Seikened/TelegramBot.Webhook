import os
from contextlib import asynccontextmanager
from http import HTTPStatus
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import MessageEntityType

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_DOMAIN: str = os.getenv('RAILWAY_PUBLIC_DOMAIN')

# Build the Telegram Bot application
bot_builder = (
    Application.builder()
    .token(TELEGRAM_BOT_TOKEN)
    .updater(None)
    .build()
)

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

async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """ Handles the /start command by sending a "Hello world!" message in response. """
    await update.message.reply_text("Hello! 🍡 Send me a message and I'll echo it back to you")

async def echo(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    await update.message.reply_text(update.message.text)

async def group_mention_or_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde cuando es mencionado o dicen 'ayuda' en grupos."""
    message = update.message
    if not message:
        return

    # Solo responder en grupos o supergrupos
    if message.chat.type not in ["group", "supergroup"]:
        return

    bot_username = (await context.bot.get_me()).username

    # Detecta si el bot fue mencionado
    mentioned = False
    if message.entities:
        for entity in message.entities:
            if (
                entity.type == MessageEntityType.MENTION and
                bot_username and
                message.text[entity.offset:entity.offset + entity.length] == f"@{bot_username}"
            ):
                mentioned = True
                break

    # Detecta si se dice "ayuda"
    ayuda = "ayuda" in message.text.lower()

    # Responde si alguna condición se cumple
    if mentioned:
        await message.reply_text("¡Me has mencionado! ¿En qué puedo ayudarte?")
    elif ayuda:
        await message.reply_text("¿Necesitas ayuda? Aquí estoy para asistirte.")

bot_builder.add_handler(CommandHandler(command="start", callback=start))
bot_builder.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND, callback=group_mention_or_help))
bot_builder.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND, callback=echo))
