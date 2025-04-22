import asyncio
import logging
import json
import os
from binance.client import Client
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, JobQueue, Job
from datetime import datetime

# ============ CONFIGURACIÓN ============
BINANCE_API_KEY = 'TU_API_KEY'
BINANCE_API_SECRET = 'TU_API_SECRET'
TELEGRAM_BOT_TOKEN = 'TU_BOT_TOKEN'
TELEGRAM_CHAT_ID = 'TU_CHAT_ID'  # Tu chat ID para alertas automáticas
PORTFOLIO_FILE = 'portfolio.json'

# Criptos a monitorear
symbols_to_track = ['BTCUSDT', 'ETHUSDT',
                    'BNBUSDT', 'SOLUSDT', 'ADAUSDT', 'EURUSDT']

# Cliente de Binance
db_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

# ====== CONFIGURAR LOGGING ======
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== FUNCIONES DE PORTAFOLIO ======


def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_portfolio():
    with open(PORTFOLIO_FILE, 'w') as f:
        json.dump(portfolio, f, indent=4)


# Cargar cartera al inicio
portfolio = load_portfolio()

# ====== FUNCIONES DE ANÁLISIS ======


def get_price(symbol: str) -> float:
    return float(db_client.get_symbol_ticker(symbol=symbol)['price'])


def get_7day_average(symbol: str) -> float:
    klines = db_client.get_klines(
        symbol=symbol, interval=Client.KLINE_INTERVAL_1DAY, limit=7)
    closes = [float(k[4]) for k in klines]
    return sum(closes) / len(closes)


def analyze_market_text() -> str:
    msg_lines = []
    for symbol in symbols_to_track:
        try:
            price = get_price(symbol)
            avg7 = get_7day_average(symbol)
            text = f"📊 {symbol}: ${price:,.2f} | Prom7D: ${avg7:,.2f}"
            if price < avg7 * 0.85:
                text += f"\n🟢 OPORTUNIDAD de COMPRA."
            elif symbol in portfolio:
                for trans in portfolio[symbol]:
                    if price >= trans['precio'] * 1.25:
                        text += f"\n🔴 VENTA sugerida (+25%) desde compra a ${trans['precio']:,.2f}."
            msg_lines.append(text)
        except Exception as e:
            logger.error("Error analizando %s: %s", symbol, e)
            msg_lines.append(f"⚠️ Error en {symbol}: {e}")
    return "\n\n".join(msg_lines)

# ====== HANDLERS ASÍNCRONOS ======


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 ¡Hola! Soy tu TradingBot. Usa /analizar para revisar el mercado o espera alertas automáticas."
    )


async def analizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Analizando mercado...")
    result = analyze_market_text()
    await update.message.reply_text(result)


async def cartera(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not portfolio:
        await update.message.reply_text("📂 Cartera vacía.")
    else:
        lines = []
        for symbol, transacciones in portfolio.items():
            current_price = get_price(symbol)
            for t in transacciones:
                profit = ((current_price - t['precio']) / t['precio']) * 100
                lines.append(
                    f"{symbol} | ${t['monto']:,.2f} comprados a ${t['precio']:,.2f} | Valor actual: ${current_price:,.2f} | {'📈' if profit >= 0 else '📉'} {profit:.2f}%")
        await update.message.reply_text("📂 Cartera actual:\n" + "\n".join(lines))


async def compra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        monto = float(context.args[0].replace('$', ''))
        symbol = context.args[1].upper()
        price = get_price(symbol)
        if symbol not in portfolio:
            portfolio[symbol] = []
        portfolio[symbol].append({'monto': monto, 'precio': price})
        save_portfolio()
        await update.message.reply_text(f"✅ Compra registrada: ${monto} de {symbol} a ${price:,.2f}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error al registrar compra: {e}")


async def venta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        symbol = context.args[0].upper()
        monto = float(context.args[1].replace('$', ''))
        if symbol in portfolio:
            portfolio[symbol] = [
                t for t in portfolio[symbol] if t['monto'] != monto]
            if not portfolio[symbol]:
                del portfolio[symbol]
            save_portfolio()
            await update.message.reply_text(f"✅ Venta registrada: ${monto} de {symbol} eliminados de cartera")
        else:
            await update.message.reply_text(f"⚠️ No se encontró {symbol} en tu cartera")
    except Exception as e:
        await update.message.reply_text(f"❌ Error al registrar venta: {e}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmds = [
        "/start - Iniciar el bot",
        "/analizar - Analizar mercado ahora",
        "/cartera - Ver simulaciones de compra",
        "/compra [monto] [cripto] - Simular compra",
        "/venta  [monto] [cripto] - Simular venta",
        "/help o /ayuda - Mostrar comandos",
    ]
    await update.message.reply_text("Comandos:\n" + "\n".join(cmds))


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmds = [
        "/start - Iniciar el bot",
        "/analizar - Analizar mercado ahora",
        "/cartera - Ver simulaciones de compra",
        "/compra [monto] [cripto] - Simular compra",
        "/venta  [monto] [cripto] - Simular venta",
        "/help o /ayuda - Mostrar comandos",
    ]
    await update.message.reply_text(
        "⚠️ No te entendí. Prueba con uno de estos comandos:\n" +
        "\n".join(cmds)
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Error manejando actualización %s: %s", update, context.error)

# ====== TAREA PROGRAMADA PARA ALERTAS AUTOMÁTICAS ======


async def automatic_alert(context: ContextTypes.DEFAULT_TYPE):
    alert_text = analyze_market_text()
    await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=alert_text)

# ====== CONFIGURAR Y EJECUTAR APP ======

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('analizar', analizar))
    app.add_handler(CommandHandler('cartera', cartera))
    app.add_handler(CommandHandler('compra', compra))
    app.add_handler(CommandHandler('venta', venta))
    app.add_handler(CommandHandler(['help', 'ayuda'], help_command))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    app.add_error_handler(error_handler)

    job_queue: JobQueue = app.job_queue
job_queue.run_repeating(automatic_alert, interval=3600, first=10)

logger.info(
    "🚀 Bot iniciado. Esperando comandos y enviando alertas automáticas cada hora.")
app.run_polling()
