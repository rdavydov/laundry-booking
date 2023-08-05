# Booking Bot for Coliving Spaces 🏘️

<div align="left">
    <img src="assets/screencast.gif" alt="Booking bot demo">
</div>

---

## 📖 Overview

Booking Bot is a Telegram bot built to streamline and automate the process of booking a washing machine in a coliving space.
It is built using the [python-telegram-bot v13.4.1](https://github.com/python-telegram-bot/python-telegram-bot/releases/tag/v13.4.1) library and uses SQLite3 as its database to store booking information.

## ✨ Features

- Book a time slot for using the washing machine.
- Cancel a previously booked time slot.
- View all booked time slots.
- Receive reminders 15 minutes prior to the start of a booking and immediately after the end of the booking.
- Automatic 30-minute cooldown period between bookings.
- Ability to view the bookings that other people have made.

## 🛠️ Installation

### Prerequisites

- Python 3.6 or higher
- SQLite3
- python-telegram-bot v13.4.1
- python-dotenv

### Steps

1. Clone the repository:

```
git clone https://github.com/rdavydov/laundry-booking.git
```

2. Navigate to the repository:

```
cd laundry-booking
```

3. Install the dependencies:

```
TODO: Make requirements.txt with this list:
pip install python-telegram-bot==13.4.1
pip install requests
pip install python-dotenv
pip install python-dateutil
pip install psycopg2
```

4. Add your Telegram Bot Token that you've recieved from the BotFather to the .env file in the same directory as your Python files:

```
TELEGRAM_LAUNDRY_BOT_TOKEN=your_telegram_bot_token_here
```

5. Start the bot and the additional services:

```
python3 book_the_time_slot.py
python3 reminder_service.py
python3 clear_db.py
```

6. Open Telegram, search for your bot's username and start a conversation.
Follow the instructions provided by the bot to book, cancel or view bookings.
