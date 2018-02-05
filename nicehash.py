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
from yobit import api_call, get_concurrency_in_rub


log_filename = 'worker.log'
logging.basicConfig(filename=log_filename, level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
local_tz = pytz.timezone("Asia/Vladivostok")
utc_tz = pytz.utc

updater = Updater(token=telegram_config['api_token'])
dispatcher = updater.dispatcher

ALGORITHMS = {
    0: 'Scrypt',
    1: 'SHA256',
    2: 'ScryptNf',
    3: 'X11',
    4: 'X13',
    5: 'Keccak',
    6: 'X15',
    7: 'Nist5',
    8: 'NeoScrypt',
    9: 'Lyra2RE',
    10: 'WhirlpoolX',
    11: 'Qubit',
    12: 'Quark',
    13: 'Axiom',
    14: 'Lyra2REv2',
    15: 'ScryptJaneNf16',
    16: 'Blake256r8',
    17: 'Blake256r14',
    18: 'Blake256r8vnl',
    19: 'Hodl',
    20: 'DaggerHashimoto',
    21: 'Decred',
    22: 'CryptoNight',
    23: 'Lbry',
    24: 'Equihash',
    25: 'Pascal',
    26: 'X11Gost',
    27: 'Sia',
    28: 'Blake2s',
    29: 'Skunk'
}

def get_json(params):
    URL = 'https://api.nicehash.com/api'
    r = requests.get(URL, params=params)
    if r.status_code == 200:
        logging.info(r.content)
        result = r.json()
        if 'error' not in result['result']:
            return result


def get_concurrency():
    return get_concurrency_in_rub('btc')
    # URL = 'https://api.cryptonator.com/api/ticker/btc-rub'
    # URL = 'https://api.exmo.com/v1/ticker/'
    # try:
    #     r = requests.get(URL)
    #     if r.status_code == 200:
    #         data = r.json()
    #         concurrency = float(data['BTC_RUB']['last_trade'])
    #         return concurrency
    # except:
    #     pass


def get_localtime(timestamp):
    date_without_tz = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
    date_utc = utc_tz.localize(date_without_tz, is_dst=None)
    date_localtime = datetime.strftime(date_utc.astimezone(local_tz), '%d-%m-%Y %H:%M:%S')
    return date_localtime


class NicehashClient:
    REQUESTS_NUMBER_FOR_WORKERS_ERROR = 3
    # Количество последовательных запросов, вернувших ошибку, для формирования ошибки о работе воркеров
    ETH_SPEED_HISTORY_LENGTH = 10
    # Количество последних значений скорости эфира

    def __init__(self):
        self.wallet = nicehash_config['wallet']
        self.id = nicehash_config['api_id']
        self.key = nicehash_config['api_key']
        self.workers_status = True
        self.workers_status_errors_count = 0
        self.payments = None
        self.notification_text = ''
        self.speed = {}

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
        logging.info('DATA={}'.format(data))
        if data['result'] and data['result']['workers']:
            try:
                for alg in data['result']['workers']:
                    algorithm_id = alg[-1]
                    algorithm_speed_history = self.speed.get(algorithm_id, [])
                    if len(algorithm_speed_history) >= self.ETH_SPEED_HISTORY_LENGTH:
                        algorithm_speed_history.pop(0)
                    algorithm_speed_history.append(alg[1]['a'])
                    self.speed[algorithm_id] = algorithm_speed_history
                # self.speed.append(data['result']['workers'][0][1]['a'])
                # if len(self.speed) >= self.ETH_SPEED_HISTORY_LENGTH:
                #     self.speed.pop(0)
            except (KeyError, IndexError) as e:
                logging.info('Ошибка получения скорости рига: {}'.format(e))
            if not self.workers_status:
                self.notification_text += 'Статус воркеров: Все воркеры работают\n'
                self.send_notification()
            self.workers_status = True
            self.workers_status_errors_count = 0
        else:
            for alg in self.speed.keys():
                if len(self.speed[alg]) >= self.ETH_SPEED_HISTORY_LENGTH:
                    self.speed[alg].pop(0)
                self.speed[alg].append(0)
            # self.speed.append('0')
            # if len(self.speed) >= self.ETH_SPEED_HISTORY_LENGTH:
            #     self.speed.pop(0)
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
                    text_new_payment = 'Произведена новая выплата на кошелек: {:.2f} {} от {}\n'
                    text_unpaid_balance = 'Невыплаченный баланс на текущий момент: {:.2f} {}\n'
                else:
                    concurrency = 1
                    currency_name = 'BTC'
                    text_new_payment = 'Произведена новая выплата на кошелек: {:.5f} {} от {}\n'
                    text_unpaid_balance = 'Невыплаченный баланс на текущий момент: {:.5f} {}\n'
                last_payment = float(self.payments[0]['amount']) * concurrency
                self.notification_text += text_new_payment.format(last_payment,
                                                                  currency_name,
                                                                  last_payment_date)
                unpaid_balance = sum([float(b['balance'])
                                      for b in
                                      data['result']['stats']]) * concurrency
                self.notification_text += text_unpaid_balance.format(unpaid_balance,
                                                                     currency_name)
                self.get_balance()
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
                text_last_payment = 'Последняя выплата: {:.2f} {} от {}\n'
                text_unpaid_balance = 'Невыплаченный баланс на текущий момент: {:.2f} {}\n'
            else:
                concurrency = 1
                currency_name = 'BTC'
                text_last_payment = 'Последняя выплата: {:.5f} {} от {}\n'
                text_unpaid_balance = 'Невыплаченный баланс на текущий момент: {:.5f} {}\n'
            self.payments = data['result']['payments']
            last_payment = float(self.payments[0]['amount']) * concurrency
            last_payment_date = get_localtime(self.payments[0]['time'])
            self.notification_text += text_last_payment.format(last_payment,
                                                               currency_name,
                                                               last_payment_date)
            unpaid_balance = sum([float(b['balance'])
                                  for b in
                                  data['result']['stats']]) * concurrency
            self.notification_text += text_unpaid_balance.format(unpaid_balance,
                                                                 currency_name)

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

    def show_speed(self):
        self.notification_text = 'Скорость рига:\n'
        for alg, values in self.speed.items():
            self.notification_text += '{}: {}\n'.format(ALGORITHMS[alg], values)
        self.send_notification()


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

    def speed(bot, update):
        logging.info('Получена команда /speed')
        c.show_speed()

    def yobit(bot, update):
        logging.info('Получена команда /yobit')
        c.notification_text = api_call(method='getInfo')
        c.send_notification()

    # ХЕНДЛЕРЫ БОТА
    start_handler = CommandHandler('start', start)
    balance_handler = CommandHandler('balance', balance)
    speed_handler = CommandHandler('speed', speed)
    yobit_handler = CommandHandler('yobit', yobit)
    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(balance_handler)
    dispatcher.add_handler(speed_handler)
    dispatcher.add_handler(yobit_handler)
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

