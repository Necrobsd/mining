from conf import nicehash_config, email_config, telegram_config
import requests
import time
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import logging
import socket
import pytz
from datetime import datetime
from telegram.ext import Updater, CommandHandler
from telegram.error import TelegramError


logging.basicConfig(filename='worker.log', level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
local_tz = pytz.timezone("Asia/Vladivostok")
utc_tz = pytz.utc

updater = Updater(token=telegram_config['api_token'])
dispatcher = updater.dispatcher

def get_json(params):
    URL = 'https://api.nicehash.com/api'
    r = requests.get(URL, params=params)
    if r.status_code == 200:
        logging.info(r.content)
        result = r.json()
        if 'error' not in result['result']:
            return result


def get_concurrency():
    # URL = 'https://api.cryptonator.com/api/ticker/btc-rub'
    URL = 'https://api.exmo.com/v1/ticker/'
    r = requests.get(URL)
    if r.status_code == 200:
        data = r.json()
        concurrency = float(data['BTC_RUB']['last_trade'])
        return concurrency


def get_localtime(timestamp):
    date_without_tz = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
    date_utc = utc_tz.localize(date_without_tz, is_dst=None)
    date_localtime = datetime.strftime(date_utc.astimezone(local_tz), '%d-%m-%Y %H:%M:%S')
    return date_localtime


class NicehashClient:
    REQUESTS_NUMBER_FOR_WORKERS_ERROR = 3
    # Количество последовательных запросов, вернувших ошибку, для формирования ошибки о работе воркеров

    def __init__(self):
        self.wallet = nicehash_config['wallet']
        self.id = nicehash_config['api_id']
        self.key = nicehash_config['api_key']
        self.workers_status = True
        self.workers_status_errors_count = 0
        self.payments = None
        self.notification_text = ''

    def get_balance(self):
        params = {
            'method': 'balance',
            'id': self.id,
            'key': self.key
        }
        data = get_json(params)
        if data:
            balance_btc = float(data['result']['balance_confirmed'])
            concurrency = get_concurrency()
            if concurrency:
                balance_rub = balance_btc * concurrency
                self.notification_text += 'Баланс кошелька: {:.2f} RUB\n'.format(balance_rub)
            else:
                self.notification_text += 'Баланс кошелька: {:.4f} BTC\n'.format(balance_btc)

    def check_workers(self):
        logging.info('check_workers')
        params = {
            'method': 'stats.provider.workers',
            'addr': self.wallet
        }
        data = get_json(params)
        if data['result']['workers']:
            if not self.workers_status:
                self.notification_text += 'Статус воркеров: Все воркеры работают\n'
                self.send_notification()
            self.workers_status = True
            self.workers_status_errors_count = 0
        else:
            if self.workers_status_errors_count < self.REQUESTS_NUMBER_FOR_WORKERS_ERROR - 1:
                self.workers_status_errors_count += 1
            else:
                if self.workers_status:
                    self.notification_text += 'Статус воркеров: Воркеры остановлены\n'
                    self.send_notification()
                self.workers_status = False

    def check_new_payments(self):
        logging.info('check_payments')
        params = {
            'method': 'stats.provider',
            'addr': self.wallet
        }
        data = get_json(params)
        if data:
            if self.payments != data['result']['payments']:
                concurrency = get_concurrency()
                self.payments = data['result']['payments']
                last_payment_date = get_localtime(self.payments[0]['time'])
                if concurrency:
                    currency_name = 'RUB'
                else:
                    concurrency = 1
                    currency_name = 'BTC'
                last_payment = float(self.payments[0]['amount']) * concurrency
                self.notification_text += 'Произведена новая выплата на кошелек: ' \
                                          '{:.4f} {} от {}\n'.format(last_payment,
                                                                     currency_name,
                                                                     last_payment_date)
                unpaid_balance = sum([float(b['balance'])
                                      for b in
                                      data['result']['stats']]) * concurrency
                self.notification_text += 'Невыплаченный баланс на текущий момент: ' \
                                          '{:.4f} {}\n'.format(unpaid_balance,
                                                               currency_name)
                self.send_notification()

    def get_last_payment(self):
        logging.info('get_last_payment')
        params = {
            'method': 'stats.provider',
            'addr': self.wallet
        }
        data = get_json(params)
        if data:
            concurrency = get_concurrency()
            if concurrency:
                currency_name = 'RUB'
            else:
                concurrency = 1
                currency_name = 'BTC'
            self.payments = data['result']['payments']
            last_payment = float(self.payments[0]['amount']) * concurrency
            last_payment_date = get_localtime(self.payments[0]['time'])
            self.notification_text += 'Последняя выплата: {:.4f} {} от' \
                                      ' {}\n'.format(last_payment,
                                                     currency_name,
                                                     last_payment_date)
            unpaid_balance = sum([float(b['balance'])
                                  for b in
                                  data['result']['stats']]) * concurrency
            self.notification_text += 'Невыплаченный баланс на текущий момент: ' \
                                      '{:.4f} {}\n'.format(unpaid_balance,
                                                           currency_name)
            self.send_notification()

    def send_notification(self):
        bot = dispatcher.bot
        logging.info('Отправка сообщения: {}'.format(self.notification_text))
        try:
            bot.send_message(chat_id=telegram_config['my_telegram_id'], text=self.notification_text)
        except (socket.error, TelegramError) as e:
            logging.info('Ошибка отправки сообщения: {}'.format(e))

        # msg = MIMEText(self.notification_text)
        # msg['Subject'] = Header(email_config['subject'], 'utf-8')
        # try:
        #     server = smtplib.SMTP_SSL(host=email_config['host'],
        #                               port=email_config['port'])
        #     server.login(email_config['login'], email_config['pass'])
        #     server.sendmail(from_addr=email_config['from_addr'],
        #                     to_addrs=email_config['to_addr'],
        #                     msg=msg.as_string())
        #     server.quit()
        # except smtplib.SMTPRecipientsRefused as e:
        #     logging.info('Ошибка отправки сообщения SMTPRecipientsRefused: {}'.format(e.recipients))
        # except (smtplib.SMTPException, socket.gaierror) as e:
        #     logging.info('Ошибка отправки сообщения: {}'.format(e))
        self.notification_text = ''


def main():
    logging.info('Запуск телеграм-бота')

    c = NicehashClient()

    # КОМАНДЫ БОТА
    def start(bot, update):
        logging.info('Получена команда /start от chat_id = {}'.format(update.message.chat_id))
        bot.send_message(chat_id=telegram_config['my_telegram_id'], text="Добрый день, хозяинъ!")

    def balance(bot, update=None):
        logging.info('Получена команда /balance')
        c.get_balance()
        c.get_last_payment()
        c.send_notification()

    def error(bot, update, error):
        logging.warning('Update "%s" caused error "%s"' % (update, error))

    # ХЕНДЛЕРЫ БОТА
    start_handler = CommandHandler('start', start)
    balance_handler = CommandHandler('balance', balance)
    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(balance_handler)
    # log all errors
    dispatcher.add_error_handler(error)

    # ЗАПУСК БОТА
    updater.start_polling()
    balance(bot=dispatcher.bot)  # Запрос баланса
    while True:
        time.sleep(60)
        c.check_workers()
        c.check_new_payments()


if __name__ == '__main__':
    main()

