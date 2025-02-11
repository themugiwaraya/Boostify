import aiohttp
import os
import logging
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, ReplyKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

load_dotenv()

API_KEY = os.getenv("API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL")

async def calculate_price(service_id, quantity):
    """Вычисляет итоговую цену заказа"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(API_URL, data={"key": API_KEY, "action": "services"}) as response:
                data = await response.json()
                for service in data:
                    if str(service.get("service")) == str(service_id):
                        price = float(service.get("rate", 0))
                        total = (price * quantity) / 1000
                        return total, price
        except Exception as e:
            logging.error(f"Ошибка при расчете цены: {e}")
        return None, None

async def place_order(service_id, link, quantity):
    async with aiohttp.ClientSession() as session:
        try:
            payload = {
                "key": API_KEY,
                "action": "add",
                "service": service_id,
                "link": link,
                "quantity": quantity
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            
            async with session.post(API_URL, data=payload, headers=headers) as response:
                data = await response.json()
                logging.info(f"Ответ API: {data}")
                return data.get("order")  
        except Exception as e:
            logging.error("Ошибка при оформлении заказа: %s", str(e))
        return None

async def cancel_orders(order_ids: str) -> str:
    """
    Отменяет один или несколько заказов через API
    Аргументы:
        order_ids: Строка с номерами заказов через запятую
    Возвращает:
        Сообщение о статусе отмены
    """
    async with aiohttp.ClientSession() as session:
        try:
            payload = {
                "key": API_KEY,
                "action": "cancel",
                "orders": order_ids
            }
            
            async with session.post(API_URL, data=payload) as response:
                text_response = await response.text()
                
                logging.info(f"📜 Ответ API на отмену заказов:\n{text_response}")
                
                try:
                    data = json.loads(text_response)
                except json.JSONDecodeError:
                    return "❌ Ошибка: сервер вернул некорректный ответ."

                if "error" in data:
                    return f"❌ Ошибка: {data['error']}"
                
                return "✅ Заказы успешно отменены!"

        except aiohttp.ClientError as e:
            logging.error(f"Ошибка при отмене заказов: {e}")
            return "❌ Ошибка сети при отмене заказов."
        except Exception as e:
            logging.error(f"Неизвестная ошибка при отмене заказов: {e}")
            return "❌ Внутренняя ошибка при отмене заказов."

async def fetch_categories():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(API_URL, data={"key": API_KEY, "action": "services"}) as response:
                data = await response.json()
                return sorted({s.get("category", "Без категории") for s in data if "category" in s})
        except Exception as e:
            logging.error("Ошибка при получении категорий: %s", str(e))
        return []

async def fetch_services(category):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(API_URL, data={"key": API_KEY, "action": "services"}) as response:
                data = await response.json()
                if not isinstance(data, list):
                    logging.error("Ошибка: API вернул не список!")
                    return []

                services = []
                for s in data:
                    service_id = s.get("service") or s.get("id")
                    name = s.get("name", "Без названия")
                    price = s.get("rate", 0)
                    rotation = s.get("rate_per", "1000")

                    if s.get("category") != category:
                        continue

                    if service_id is None:
                        continue

                    try:
                        price = float(price)
                        price = f"{price:.2f} ₽ за {rotation}"
                    except (ValueError, TypeError):
                        price = "Не указано"

                    services.append((service_id, f"ID: {service_id}, Название: {name}, Цена: {price}"))
                
                return services
        except Exception as e:
            logging.error(f"Ошибка при получении услуг: {e}")
            return []

async def fetch_balance():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(API_URL, data={"key": API_KEY, "action": "balance"}) as response:
                data = await response.json()
                return data.get("balance", "❌ Ошибка при получении баланса")
        except Exception as e:
            logging.error("Ошибка при получении баланса: %s", str(e))
        return "❌ Ошибка при получении баланса"

async def fetch_order_status(order_id: str) -> str:
    async with aiohttp.ClientSession() as session:
        try:
            payload = {"key": API_KEY, "action": "status", "order": order_id}
            async with session.post(API_URL, data=payload) as response:
                text_response = await response.text()

                logging.info(f"\n📜 Полный ответ API:\n{text_response}\n")

                try:
                    data = json.loads(text_response)
                except json.JSONDecodeError:
                    logging.error("❌ Ошибка: API вернул не JSON. Возможно, HTML-страницу или ошибку.")
                    return "❌ Ошибка: сервер вернул некорректный ответ."

                logging.info(f"🔍 Разобранные данные: {json.dumps(data, indent=4, ensure_ascii=False)}\n")

                if "error" in data:
                    return f"❌ Ошибка: {data['error']}"
                
                status_message = (
                    f"📦 *Статус заказа {order_id}*\n"
                    f"💰 *Стоимость:* {data.get('charge', 'Нет данных')} руб.\n"
                    f"🛠 *Услуга:* {data.get('service', 'Нет данных')}\n"
                    f"📌 *Статус:* {data.get('status', 'Нет данных')}\n"
                    f"📉 *Осталось:* {data.get('remains', 'Нет данных')}\n"
                )

                return status_message

        except aiohttp.ClientError as http_error:
            logging.error(f"Ошибка HTTP-запроса: {http_error}")
            return "❌ Ошибка сети. Проверьте соединение."

        except Exception as e:
            logging.error(f"Неизвестная ошибка: {e}")
            return "❌ Внутренняя ошибка. Попробуйте позже."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["🛒 Оформить заказ", "💰 Баланс"],
        ["📦 Статус заказа", "❌ Отменить заказ"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Добро пожаловать! Выберите действие:",
        reply_markup=reply_markup
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("serv_"):
        service_id = query.data.split("_")[1]
        context.user_data["selected_service_id"] = service_id
        
        services = context.user_data.get("services", {})
        service_info = services.get(f"serv_{service_id}")
        if service_info:
            context.user_data["service_info"] = service_info[1]
        
        await query.message.reply_text(
            f"📋 Выбрана услуга:\n{context.user_data['service_info']}\n\n"
            "🔗 Введите ссылку на профиль или пост:"
        )
        context.user_data["awaiting_link"] = True
    
    elif query.data.startswith("cat_"):
        index = int(query.data.split("_")[1])
        category = context.user_data["categories"][index]
        services = await fetch_services(category)

        if not services:
            await query.message.reply_text("❌ В этой категории пока нет услуг.")
            return

        keyboard = [
            [InlineKeyboardButton(service[1], callback_data=f"serv_{service[0]}")]
            for service in services
        ]
        context.user_data["services"] = {f"serv_{service[0]}": service for service in services}

        await query.message.reply_text(
            f"✅ Выберите услугу в категории *{category}*: ",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif query.data == "confirm_order":
        order_details = context.user_data.get("order_details", {})
        order_id = await place_order(
            order_details["service_id"],
            order_details["link"],
            order_details["quantity"]
        )
        
        if order_id:
            total_price, rate = await calculate_price(
                order_details["service_id"],
                order_details["quantity"]
            )
            
            success_message = (
                "✅ Заказ успешно размещен!\n\n"
                f"📦 Номер заказа: {order_id}\n"
                f"🔗 Ссылка: {order_details['link']}\n"
                f"📊 Количество: {order_details['quantity']}\n"
                f"💰 Цена за 1000: {rate:.2f} ₽\n"
                f"💵 Итоговая стоимость: {total_price:.2f} ₽"
            )
            await query.message.reply_text(success_message)
        else:
            await query.message.reply_text("❌ Ошибка при создании заказа. Пожалуйста, попробуйте снова.")
        
        context.user_data.clear()
    
    elif query.data == "cancel_order":
        await query.message.reply_text("❌ Заказ отменен")
        context.user_data.clear()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "🛒 Оформить заказ":
        categories = await fetch_categories()
        if not categories:
            await update.message.reply_text("❌ Ошибка: не удалось загрузить категории.")
            return

        keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat_{i}")] for i, cat in enumerate(categories)]
        context.user_data["categories"] = categories
        await update.message.reply_text("📂 Выберите категорию:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "💰 Баланс":
        balance = await fetch_balance()
        await update.message.reply_text(f"💰 Ваш баланс: {balance} ₽")

    elif text == "📦 Статус заказа":
        await update.message.reply_text("🔎 Введите номер заказа:")
        context.user_data["awaiting_order_status"] = True

    elif text == "❌ Отменить заказ":
        await update.message.reply_text(
            "📝 Введите номера заказов для отмены через запятую (максимум 100 заказов):\n"
            "Пример: 12345,12346,12347"
        )
        context.user_data["awaiting_cancel_orders"] = True

    elif context.user_data.get("awaiting_link"):
        context.user_data["link"] = text
        context.user_data["awaiting_link"] = False
        context.user_data["awaiting_quantity"] = True
        await update.message.reply_text(
            "🔢 Введите количество (минимум 10, максимум 50 000):\n\n"
            "💡 После ввода количества будет показана итоговая стоимость заказа."
        )

    elif context.user_data.get("awaiting_quantity"):
        try:
            quantity = int(text)
            if quantity < 10 or quantity > 50000:
                await update.message.reply_text("❌ Ошибка: Количество должно быть от 10 до 50 000")
                return
                
            service_id = context.user_data.get("selected_service_id")
            link = context.user_data.get("link")
            
            if not all([service_id, link]):
                await update.message.reply_text("❌ Ошибка: Отсутствует информация об услуге или ссылке")
                return

            total_price, rate = await calculate_price(service_id, quantity)
            if total_price is None:
                await update.message.reply_text("❌ Ошибка при расчете стоимости заказа")
                return

            keyboard = [
                [
                    InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_order"),
                    InlineKeyboardButton("❌ Отменить", callback_data="cancel_order")
                ]
            ]
            confirmation_message = (
                f"📋 Подтверждение заказа:\n\n"
                f"🔗 Ссылка: {link}\n"
                f"📊 Количество: {quantity}\n"
                f"💰 Цена за 1000: {rate:.2f} ₽\n"
                f"💵 Итоговая стоимость: {total_price:.2f} ₽\n\n"
                "Подтвердите или отмените заказ:"
            )
            await update.message.reply_text(
                confirmation_message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            context.user_data["order_details"] = {
                "service_id": service_id,
                "link": link,
                "quantity": quantity
            }

        except ValueError:
            await update.message.reply_text("❌ Ошибка: Пожалуйста, введите корректное число")
            return

    elif context.user_data.get("awaiting_order_status"):
        order_id = text
        context.user_data["awaiting_order_status"] = False
        
        if not order_id.isdigit():
            await update.message.reply_text("❌ Ошибка: введите корректный номер заказа.")
            return
        
        status = await fetch_order_status(order_id)
        await update.message.reply_text(status, parse_mode="Markdown")

    elif context.user_data.get("awaiting_cancel_orders"):
        context.user_data["awaiting_cancel_orders"] = False
        
        order_ids = text.strip().split(",")
        if len(order_ids) > 100:
            await update.message.reply_text("❌ Ошибка: можно отменить максимум 100 заказов за раз")
            return
            
        if not all(order_id.strip().isdigit() for order_id in order_ids):
            await update.message.reply_text("❌ Ошибка: все ID заказов должны быть числами")
            return
            
        result = await cancel_orders(text.strip())
        await update.message.reply_text(result)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logging.info("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()