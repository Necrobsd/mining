from conf import nicehash_config, email_config
import requests
import time
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import logging
import socket
import pytz
from datetime import datetime


logging.basicConfig(filename='worker.log', level=logging.INFO,
                    format='[%(asctime)s]  %(message)s')
local_tz = pytz.timezone("Asia/Vladivostok")
utc_tz = pytz.utc


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

    def check_workers(self, send=False):
        params = {
            'method': 'stats.provider.workers',
            'addr': self.wallet
        }
        data = get_json(params)
        if data['result']['workers']:
            if not self.workers_status:
                self.notification_text += 'Статус воркеров: Все воркеры работают\n'
                if send:
                    self.send_notification()
            self.workers_status = True
            self.workers_status_errors_count = 0
        else:
            if self.workers_status_errors_count < self.REQUESTS_NUMBER_FOR_WORKERS_ERROR - 1:
                self.workers_status_errors_count += 1
            else:
                if self.workers_status:
                    self.notification_text += 'Статус воркеров: Воркеры остановлены\n'
                    if send:
                        self.send_notification()
                self.workers_status = False

    def check_payments(self, send=False):
        params = {
            'method': 'stats.provider',
            'addr': self.wallet
        }
        data = get_json(params)
        if data:
            if self.payments != data['result']['payments']:
                concurrency = get_concurrency()
                self.payments = data['result']['payments']
                last_payment_date_without_tz = datetime.strptime(self.payments[0]['time'], '%Y-%m-%d %H:%M:%S')
                last_payment_date_utc = utc_tz.localize(last_payment_date_without_tz, is_dst=None)
                last_payment_date = datetime.strftime(last_payment_date_utc.astimezone(local_tz), '%d-%m-%Y %H:%M:%S')
                if concurrency:
                    currency_name = 'RUB'
                else:
                    concurrency = 1
                    currency_name = 'BTC'
                last_payment = float(self.payments[0]['amount']) * concurrency
                if send:
                    self.notification_text += 'Произведена новая выплата на кошелек: ' \
                                              '{:.4f} {} от {}\n'.format(last_payment,
                                                                         currency_name,
                                                                         last_payment_date)
                else:
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
                if send:
                    self.send_notification()

    def send_notification(self):
        logging.info('Отправка сообщения: {}'.format(self.notification_text))
        msg = MIMEText(self.notification_text)
        msg['Subject'] = Header(email_config['subject'], 'utf-8')
        try:
            server = smtplib.SMTP_SSL(host=email_config['host'],
                                      port=email_config['port'])
            server.login(email_config['login'], email_config['pass'])
            server.sendmail(from_addr=email_config['from_addr'],
                            to_addrs=email_config['to_addr'],
                            msg=msg.as_string())
            server.quit()
        except smtplib.SMTPRecipientsRefused as e:
            logging.info('Ошибка отправки сообщения SMTPRecipientsRefused: {}'.format(e.recipients))
        except (smtplib.SMTPException, socket.gaierror) as e:
            logging.info('Ошибка отправки сообщения: {}'.format(e))
        self.notification_text = ''


def main():
    logging.info('Запуск программы')
    c = NicehashClient()
    c.get_balance()
    c.check_payments()
    c.check_workers()
    c.send_notification()
    while True:
        time.sleep(60)
        c.check_workers(send=True)
        c.check_payments(send=True)


if __name__ == '__main__':
    main()

