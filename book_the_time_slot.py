# python-telegram-bot-13.4.1 is used

# TODO: CREATE TABLE IF NOT EXISTS user_info

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, CallbackContext, Filters
from datetime import datetime, timedelta
# TODO:Should replace sqlite with another DB system - I need to be able to use datetime objects for date and time comparison
import sqlite3
import logging
import pytz
import locale
import requests
import json
import os
from concurrent.futures import ThreadPoolExecutor
from math import floor, ceil
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from dateutil.parser import parse as parse_time
from dotenv import load_dotenv

load_dotenv()  # Load the environment variables from .env file
token = os.getenv("TELEGRAM_LAUNDRY_BOT_TOKEN")
tz = os.getenv("TIMEZONE")

local_tz = pytz.timezone(tz)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)
# Create a SQLite database connection
conn = sqlite3.connect('bookings.db')

# Create a cursor object
c = conn.cursor()

# Create tables
c.execute('''CREATE TABLE IF NOT EXISTS bookings
             (id INTEGER PRIMARY KEY AUTOINCREMENT, 
              user_id text, 
              building_number text,
              floor_number text,
              start_booking_date text, 
              end_booking_date text, 
              start_time text, 
              end_time text)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_info
             (user_id INTEGER PRIMARY KEY, 
              building_number TEXT, 
              floor_number TEXT)''')

# Commit the changes to the DB
conn.commit()

# Create scheduler
scheduler = BackgroundScheduler()
scheduler.start()


def get_user_building_floor(user_id: str):
    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()
    c.execute('SELECT building_number, floor_number FROM user_info WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()

    if result:
        building, floor = result
        return building, floor
    else:
        return None, None
    
def update_user_info(user_id: str, building: str, floor: str):
    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO user_info (user_id, building_number, floor_number) VALUES (?, ?, ?)', (user_id, building, floor))
    conn.commit()
    conn.close()


def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("Забронировать", callback_data='1')],
        [InlineKeyboardButton("Отменить", callback_data='2')],
        [InlineKeyboardButton("Посмотреть свои стирки", callback_data='3')],
        [InlineKeyboardButton("Посмотреть все стирки", callback_data='4')],
        [InlineKeyboardButton("Главное меню", callback_data='5')],
        [InlineKeyboardButton("Автор", callback_data='6')]
    ]

    user_id = str(update.effective_user.id)
    building, floor = get_user_building_floor(user_id)

    if building and floor:
        keyboard.insert(0, [InlineKeyboardButton(
            f"Корпус: {building}, Этаж: {floor}", callback_data='7')])
    else:
        keyboard.insert(0, [InlineKeyboardButton(
            "Выбрать Корпус и Этаж", callback_data='7')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Check if update.message is None
    if update.message:
        update.message.reply_text(
            'Пожалуйста, выбери:', reply_markup=reply_markup)
    else:
        update.callback_query.message.reply_text(
            'Пожалуйста, выбери:', reply_markup=reply_markup)


# Helper function to generate the next 7 days


def generate_dates():
    # Set the locale to Russian
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except locale.Error:
        print("The desired locale is not supported on your system.")

    dates = [datetime.now(local_tz) + timedelta(days=i) for i in range(7)]
    return [date.strftime('%d.%m.%Y (%A)') for date in dates]


def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query

    query.answer()

    user_id = str(update.effective_user.id)
    building, floor = get_user_building_floor(user_id)

    if query.data == '1':
        # Check if building and floor settings exist
        if building and floor:
            # Proceed to date selection
            dates = generate_dates()
            keyboard = [[InlineKeyboardButton(
                date, callback_data=f'date_{date.split(" ")[0]}')] for date in dates]
            keyboard.append([InlineKeyboardButton(
                "Назад", callback_data='5')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            context.bot.send_message(
                chat_id=query.message.chat_id, text="Выбери дату:", reply_markup=reply_markup)
        else:
            # Prompt user to select building and floor
            context.bot.send_message(chat_id=query.message.chat_id,
                                     text="Пожалуйста, выбери корпус и этаж сначала.")
            start(update, context)
    elif query.data.startswith('date_'):
        selected_date = query.data[5:]
        context.user_data['selected_date'] = selected_date
        _floor = floor
        display_not_booked_times(update, context, selected_date, building, _floor)
        context.bot.send_message(chat_id=query.message.chat_id,
                                 text="Чтобы выйти в главное меню нажми /start\nОтправь мне время, которое хочешь забронировать в формате: '12:30-13:00'")
    elif query.data.startswith('building_'):
        # Extract building and floor information
        building, floor = query.data.split('_')[1], query.data.split('_')[3]
        # Update building and floor in the database
        update_user_info(user_id, building, floor)
        context.bot.send_message(chat_id=query.message.chat_id,
                                text=f"Корпус {building}, Этаж {floor} выбраны.")
        context.bot.send_message(chat_id=query.message.chat_id,
                                text="⚠️⚠️⚠️ ЕСЛИ У ВАС ОСТАВАЛИСЬ ЗАБРОНИРОВАНЫ СТИРКИ НА СТАРОМ МЕСТЕ, ПОЖАЛУЙСТА, СНАЧАЛА УДАЛИТЕ ИХ ВСЕ ⚠️⚠️⚠️")
        # Proceed to date selection
        dates = generate_dates()
        keyboard = [[InlineKeyboardButton(
            date, callback_data=f'date_{date.split(" ")[0]}')] for date in dates]
        keyboard.append([InlineKeyboardButton(
            "Назад", callback_data='5')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(
            chat_id=query.message.chat_id, text="Выбери дату:", reply_markup=reply_markup)
    elif query.data == '2':
        cancel_time(update, context)
    elif query.data == '3':
        view_bookings(update, context)
    elif query.data == '4':
        display_all_bookings(update, context)
    elif query.data == '5':
        start(update, context)  # Call the /start command
    elif query.data == '6':
        context.bot.send_message(
            chat_id=query.message.chat_id, text="Автор: @rdavidoff\nhttps://github.com/rdavydov/laundry-booking")
        start(update, context)
    elif query.data == '7':
            # Proceed to building and floor selection
            buildings = ["1", "2"]
            floors = ["1", "2", "3", "4", "5"]
            keyboard = [[InlineKeyboardButton(
                f"Корпус {building}, Этаж {floor}", callback_data=f'building_{building}_floor_{floor}')] for building in buildings for floor in floors]
            keyboard.append([InlineKeyboardButton(
                "Назад", callback_data='5')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            context.bot.send_message(
                chat_id=query.message.chat_id, text="Выбери корпус и этаж:", reply_markup=reply_markup)


def display_not_booked_times(update: Update, context: CallbackContext, selected_date: str, building: str, _floor: str) -> None:
    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()

    # Convert selected_date to datetime object
    selected_date_dt = datetime.strptime(selected_date, "%d.%m.%Y")

    # Calculate the next date
    next_date = (selected_date_dt + timedelta(days=1)).strftime("%d.%m.%Y")

    # Query the database for the bookings on the selected date and next date (4 hours into next day)
    c.execute("""
    SELECT *
    FROM bookings
    WHERE
        (start_booking_date = ? AND floor_number = ? AND building_number = ? AND strftime('%H:%M', end_time) > '00:00')
        OR (start_booking_date = ? AND floor_number = ? AND building_number = ? AND strftime('%H:%M', start_time) < '04:00')
        OR (end_booking_date = ? AND floor_number = ? AND building_number = ? AND strftime('%H:%M', end_time) >= '04:00')
    ORDER BY start_booking_date, start_time
""", (selected_date, _floor, building, next_date, _floor, building, selected_date, _floor, building))

    bookings = c.fetchall()

    conn.close()

    # List to keep track of free time slots
    free_time_slots = []

    # Beginning of the day
    day_beginning = datetime.strptime(
        selected_date + " 00:00", "%d.%m.%Y %H:%M")

    now_time = datetime.now(local_tz).replace(
        microsecond=0).replace(tzinfo=None)

    # Loop through the booked time slots
    for booking in bookings:
        id, user_id, building_number, floor_number, start_booking_date, end_booking_date, start_time, end_time = booking
        start_time_dt = datetime.strptime(
            f"{start_booking_date} {start_time}", "%d.%m.%Y %H:%M") - timedelta(minutes=30)
        end_time_dt = datetime.strptime(
            f"{end_booking_date} {end_time}", "%d.%m.%Y %H:%M") + timedelta(minutes=30)

        # Check if there is a free slot before this booking
        if (start_time_dt - day_beginning).total_seconds() > 0 and day_beginning > now_time:
            free_time_slots.append((day_beginning.strftime(
                "%d.%m.%Y %H:%M"), (start_time_dt - timedelta(minutes=1)).strftime("%d.%m.%Y %H:%M")))

        # Update the day_beginning to the end of this booking
        # 1-minute cooldown period
        day_beginning = end_time_dt + timedelta(minutes=1)

    # Check for free time slot between the last booking and 04:00 of the next day
    end_of_extended_day = datetime.strptime(
        next_date + " 04:00", "%d.%m.%Y %H:%M")
    if (end_of_extended_day - day_beginning).total_seconds() > 0:
        free_time_slots.append((day_beginning.strftime(
            "%d.%m.%Y %H:%M"), end_of_extended_day.strftime("%d.%m.%Y %H:%M")))

    # Construct and send the message
    if free_time_slots:
        message_text = "Свободное время в выбранный день + 4 часа после:\n"
        for start, end in free_time_slots:
            start_date, start_time = start.split(" ")
            end_date, end_time = end.split(" ")

            # Rounding start_time for display
            start_time_hour, start_time_minute = map(
                int, start_time.split(":"))
            start_time_minute = floor(start_time_minute / 5) * 5
            start_time = f"{start_time_hour:02d}:{start_time_minute:02d}"

            # Rounding end_time for display
            end_time_hour, end_time_minute = map(int, end_time.split(":"))
            end_time_minute = ceil(end_time_minute / 5) * 5
            if end_time_minute == 60:
                end_time_hour += 1
                end_time_minute = 0
            end_time = f"{end_time_hour:02d}:{end_time_minute:02d}"

            message_text += f"{start_date} - {end_date}        {start_time} - {end_time}\n"

        context.bot.send_message(
            chat_id=update.effective_chat.id, text=message_text)
    else:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="В этот день все занято, выбери другой день для стирки")


def book_time(update: Update, context: CallbackContext) -> None:
    if update.message is not None:
        message_text = update.message.text if update.message else update.callback_query.message.text
        if 'selected_date' in context.user_data:
            try:
                # Splitting the message text and striping leading and trailing whitespaces
                start_time, end_time = [
                    time.strip() for time in message_text.replace('\u2013', '-').split('-')]

                # Ensure that hours and minutes have two digits
                start_time = start_time.zfill(5)
                end_time = end_time.zfill(5)

                # Convert start_time and end_time to datetime objects for comparison
                start_time_dt = datetime.strptime(start_time, "%H:%M")
                end_time_dt = datetime.strptime(end_time, "%H:%M")

                # Combine the booking date with the start time and check if it is in the past
                booking_date = context.user_data['selected_date']
                combined_start_datetime_naive = datetime.strptime(
                    f"{booking_date} {start_time}", "%d.%m.%Y %H:%M")

                # Convert combined_start_datetime to timezone aware
                combined_start_datetime = local_tz.localize(
                    combined_start_datetime_naive)

                # Get current datetime with timezone
                current_datetime = datetime.now(local_tz)

                if combined_start_datetime < current_datetime:
                    update.message.reply_text(
                        "Время бронирования уже прошло. Выбери время в будущем.")
                    start(update, context)
                    return

                # Check if the start time is later than or equal to the end time
                if start_time_dt >= end_time_dt:
                    keyboard = [
                        [InlineKeyboardButton(
                            "Да", callback_data='confirm_yes')],
                        [InlineKeyboardButton(
                            "Нет", callback_data='confirm_no')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    update.message.reply_text(
                        "Время начала стирки позднее, чем время окончания.\nТы хочешь забронировать с текущего дня по следующий?", reply_markup=reply_markup)
                    context.user_data['start_time'] = start_time
                    context.user_data['end_time'] = end_time
                    return

                # Calculate booking duration in minutes
                booking_duration = (
                    end_time_dt - start_time_dt).total_seconds() / 60

                # Check if the booking duration is less than 30 minutes or longer than 180 minutes
                if booking_duration < 30 or booking_duration > 180:
                    keyboard = [
                        [InlineKeyboardButton(
                            "Да", callback_data='confirm_yes')],
                        [InlineKeyboardButton(
                            "Нет", callback_data='confirm_no')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    update.message.reply_text(
                        "Длительность стирки меньше получаса или дольше 3 часов.\nТы хочешь забронировать это время?", reply_markup=reply_markup)
                    context.user_data['start_time'] = start_time
                    context.user_data['end_time'] = end_time
                    return

                process_booking(update, context, start_time, end_time)

            except ValueError:
                update.message.reply_text(
                    "Пожалуйста, введи время в верном формате '12:30-13:00'")

        else:
            update.message.reply_text("Сначала выбери дату стирки")
            start(update, context)


def confirm_booking(update: Update, context: CallbackContext) -> None:
    if update.callback_query.data == 'confirm_yes':
        start_time = context.user_data['start_time']
        end_time = context.user_data['end_time']

        # Book from selected day till the next one
        # Set end_booking_date as the next day from selected_date
        context.user_data['selected_end_date'] = context.user_data['selected_date']

        process_booking(update, context, start_time, end_time)
    elif update.callback_query.data == 'confirm_no':
        start(update, context)  # Restart dialog


def process_booking(update: Update, context: CallbackContext, start_time: str, end_time: str) -> None:
    booking_start_date = context.user_data['selected_date']
    booking_end_date = booking_start_date
    user_id = update.message.from_user.id if update.message else update.callback_query.from_user.id

    # Store building and floor in user_data
    building, floor = get_user_building_floor(user_id)

    # To handle callback_query as well as message
    reply_func = update.message.reply_text if update.message else update.callback_query.message.reply_text

    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()

    # Ensure that hours and minutes have two digits
    start_time = start_time.zfill(5)
    end_time = end_time.zfill(5)

    # Convert the times to datetime objects
    start_time_datetime = parse_time(start_time)
    end_time_datetime = parse_time(end_time)

    try:
        # Subtract 30 minutes from the start time and add 30 minutes to the end time for buffer
        start_time_30_min_prior = (
            start_time_datetime - timedelta(minutes=30)).strftime('%H:%M')
        end_time_30_min_after = (
            end_time_datetime + timedelta(minutes=30)).strftime('%H:%M')

        # Check if the time slot is available
        c.execute("SELECT * FROM bookings WHERE start_booking_date = ? AND (start_time < ? AND end_time > ?)",
                  (booking_start_date, end_time_30_min_after, start_time_30_min_prior))
        if c.fetchone() is None:
            # If start_time is later than or equal to end_time, the booking spans across two days
            if start_time >= end_time:
                booking_end_date = (datetime.strptime(
                    booking_start_date, "%d.%m.%Y") + timedelta(days=1)).strftime('%d.%m.%Y')

            c.execute("INSERT INTO bookings (user_id, building_number, floor_number, start_booking_date, end_booking_date, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
          (user_id, building, floor, booking_start_date, booking_end_date, start_time, end_time))

            conn.commit()

            reply_func(
                f"Успешно забронирована стирка с {booking_start_date} {start_time} до {booking_end_date} {end_time}\n"
                f"Корпус: {building}, Этаж: {floor}")
        else:
            reply_func(
                "Время за 30 минут до начала или 30 минут после уже занято. Выбери другое время")

    finally:
        conn.close()

    start(update, context)


def view_bookings(update: Update, context: CallbackContext) -> None:
    user_id = update.callback_query.from_user.id

    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()

    # Get the current date and time
    current_date = datetime.now(local_tz).strftime('%d.%m.%Y')
    current_time = datetime.now(local_tz).strftime('%H:%M')

    # Retrieving the user's bookings
    c.execute("""
        SELECT * FROM bookings
        WHERE user_id = ? AND ((start_booking_date > ?) OR (start_booking_date = ? AND end_time > ?))
        ORDER BY start_booking_date, start_time
    """, (user_id, current_date, current_date, current_time))

    bookings = c.fetchall()

    conn.close()

    if bookings:
        message_text = "Твои стирки:\n"
        for booking in bookings:
            id, user_id, building, floor, start_booking_date, end_booking_date, start_time, end_time = booking
            message_text += f"С {start_booking_date} {start_time} до {end_booking_date} {end_time}"
            message_text += f" (к{building}э{floor})\n"
        context.bot.send_message(
            chat_id=update.effective_chat.id, text=message_text)
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id, text="У тебя нет предстоящих стирок")

    start(update, context)


def cancel_time(update: Update, context: CallbackContext) -> None:
    user_id = update.callback_query.from_user.id

    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()

    # Convert the datetime to the format used in the database
    current_datetime = datetime.now(local_tz).strftime('%d.%m.%Y %H:%M')

    # Retrieve the user's bookings that are later than the current time
    c.execute("""
        SELECT * FROM bookings
        WHERE user_id = ? AND start_booking_date || ' ' || end_time > ?
        ORDER BY start_booking_date, start_time
    """, (user_id, current_datetime))

    bookings = c.fetchall()

    conn.close()

    if bookings:
        keyboard = []
        for booking in bookings:
            id, user_id, building, floor, start_booking_date, end_booking_date, start_time, end_time = booking
            keyboard.append([InlineKeyboardButton(f"С {start_booking_date} {start_time} до {end_booking_date} {end_time}",
                            callback_data=f'cancel_{id}_{start_booking_date}_{end_booking_date}_{start_time}_{end_time}')])

        keyboard.append([InlineKeyboardButton(
            "Назад", callback_data='5')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text='Выбери время, которое хочешь отменить:', reply_markup=reply_markup)
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id, text="У тебя нет забронированных стирок")
        start(update, context)


def delete_booking(update: Update, context: CallbackContext) -> None:
    if update.callback_query.data.startswith('cancel_'):
        user_id = update.callback_query.from_user.id
        _, id, start_booking_date, end_booking_date, start_time, end_time = update.callback_query.data.split(
            '_')

        conn = sqlite3.connect('bookings.db')
        c = conn.cursor()

        # Delete the booking
        c.execute("DELETE FROM bookings WHERE id = ?", (id,))

        conn.commit()
        conn.close()

        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=f"Стирка с {start_booking_date} {start_time} до {end_booking_date} {end_time} была отменена")

        start(update, context)


def send_reminder(user_id: int, start_booking_date: str, end_booking_date: str, start_time: str, end_time: str) -> None:
    context.bot.send_message(
        chat_id=user_id, text=f"Ранее ты забронировал(а) стирку с {start_booking_date} {end_booking_date} до {start_time} {end_time}. Это твое 15-минутное напоминание.")


def get_username(user_id):
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getChat?chat_id={user_id}")
        data = json.loads(response.text)
        if "username" in data["result"] and data["result"]["username"]:
            return "@" + data["result"]["username"]
        elif "first_name" in data["result"] and data["result"]["first_name"]:
            if "last_name" in data["result"] and data["result"]["last_name"]:
                return f"{data['result']['first_name']} {data['result']['last_name']}"
            else:
                return data["result"]["first_name"]
        else:
            return "N/A"
    except KeyError as e:
        logging.error(f"KeyError: {e}. Response data: {data}")
        return "N/A"
    except Exception as e:
        logging.error(f"Error: {e}")
        return "N/A"


def get_usernames(user_ids):
    with ThreadPoolExecutor(max_workers=5) as executor:
        return list(executor.map(get_username, user_ids))


def display_all_bookings(update: Update, context: CallbackContext) -> None:
    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()

    c.execute("""
        SELECT * 
        FROM bookings 
        WHERE DATE(SUBSTR(start_booking_date, 7, 4) || '-' || SUBSTR(start_booking_date, 4, 2) || '-' || SUBSTR(start_booking_date, 1, 2)) >= DATE('now', '-3 day') 
        ORDER BY DATE(SUBSTR(start_booking_date, 7, 4) || '-' || SUBSTR(start_booking_date, 4, 2) || '-' || SUBSTR(start_booking_date, 1, 2)), start_time
    """)

    all_bookings = c.fetchall()

    usernames = get_usernames([booking[1] for booking in all_bookings])

    formatted_bookings = []
    for booking, username in zip(all_bookings, usernames):
        user_id, building, floor, start_date, end_date, start_time, end_time = booking[1:]
        formatted_booking = f"{username} ID{user_id[-2:]} - с {start_date} {start_time} до {end_date} {end_time}"
        formatted_booking += f" (к{building}э{floor})\n"
        formatted_bookings.append(formatted_booking)

    c.close()
    conn.close()

    if formatted_bookings:
        update.callback_query.message.reply_text('\n'.join(formatted_bookings))
    else:
        update.callback_query.message.reply_text(
            'No bookings in the last 3 days.')

    start(update, context)


def main() -> None:
    updater = Updater(token, use_context=True)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(
        button, pattern='^(?!cancel_|confirm_)'))
    dispatcher.add_handler(CallbackQueryHandler(
        delete_booking, pattern='^cancel_'))
    dispatcher.add_handler(CallbackQueryHandler(
        confirm_booking, pattern='^confirm_'))
    dispatcher.add_handler(MessageHandler(
        Filters.text & ~Filters.command, book_time))

    updater.start_polling()

    updater.idle()


if __name__ == '__main__':
    main()
