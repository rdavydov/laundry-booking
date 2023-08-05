from apscheduler.schedulers.blocking import BlockingScheduler
import sqlite3
import datetime
import pytz
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def convert_date(date_str):
    """Converts a date from 'DD.MM.YYYY' format to 'YYYY-MM-DD'"""
    day, month, year = date_str.split('.')
    return '-'.join([year, month, day])

# Delete each column older than 1 week
def delete_old_entries():
    conn = sqlite3.connect('bookings.db')
    conn.create_function("CONVERT_DATE", 1, convert_date)
    c = conn.cursor()

    now = datetime.datetime.now()
    time_one_week_ago = now - datetime.timedelta(days=7)

    c.execute("DELETE FROM bookings WHERE CONVERT_DATE(start_booking_date) < ?", (time_one_week_ago.strftime('%Y-%m-%d'),))
    conn.commit()

    conn.close()

scheduler = BlockingScheduler(timezone=pytz.utc)

scheduler.add_job(delete_old_entries, 'interval', days=1)

scheduler.start()
