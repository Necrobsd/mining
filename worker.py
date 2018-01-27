from conf import nicehash_config, email_config
import requests
import time
import json
import smtplib
from email.mime.text import MIMEText
from email.header import Header


def get_json(params):
    URL = 'https://api.nicehash.com/api'
    r = requests.get(URL, params=params)
    if r.status_code == 200:
        print(r.content)
        result = r.json()
        if 'error' not in result['result']:
            return result


def get_concurrency():
    URL = 'https://api.cryptonator.com/api/ticker/btc-rub'
    r = requests.get(URL)
    if r.status_code == 200:
        data = r.json()
        concurrency = float(data['ticker']['price'])
        return concurrency


class NicehashClient:
    def __init__(self):
        self.wallet = nicehash_config['wallet']
        self.id = nicehash_config['api_id']
        self.key = nicehash_config['api_key']
        self.workers_status = None
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
                self.notification_text += 'Баланс кошелька: {:.2f} RUB\n'.format((balance_rub))

    def check_workers(self):
        params = {
            'method': 'stats.provider.workers',
            'addr': self.wallet
        }
        data = get_json(params)
        if data['result']['workers']:
            if not self.workers_status:
                # self.notification_text += 'Статус воркеров: Все воркеры работают\n'
                self.send_notification('Статус воркеров: Все воркеры работают\n')
            self.workers_status = True
        else:
            if self.workers_status:
                # self.notification_text += 'Статус воркеров: Воркеры остановлены\n'
                self.send_notification('Статус воркеров: Воркеры остановлены\n')
            self.workers_status = False

    def check_payments(self):
        params = {
            'method': 'stats.provider',
            'addr': self.wallet
        }
        data = get_json(params)
        if data:
            if self.payments != data['result']['payments']:
                concurrency = float(get_concurrency())
                self.payments = data['result']['payments']
                last_payment = float(self.payments[0]['amount']) * concurrency
                last_payment_date = self.payments[0]['time']
                self.notification_text += 'Произведена новая выплата на кошелек: {:.2f} от {}\n'.format(last_payment, last_payment_date)
                # self.notification_text += 'Последняя выплата: {:.2f} от {}\n'.format(last_payment, last_payment_date)
                unpaid_balance = sum([float(b['balance']) for b in data['result']['stats']]) * concurrency
                self.notification_text += 'Невыплаченный баланс на текущий момент: {:.2f} RUB\n'.format(unpaid_balance)
                self.send_notification(self.notification_text)

    def send_notification(self, text):
        print(text)
        msg = MIMEText(text)
        msg['Subject'] = Header(email_config['subject'], 'utf-8')
        server = smtplib.SMTP_SSL(host=email_config['host'], port=email_config['port'])
        server.login(email_config['login'], email_config['pass'])
        server.sendmail(from_addr=email_config['from_addr'], to_addrs=email_config['to_addr'], msg=msg.as_string())
        server.quit()
        self.notification_text = ''


def main():
    c = NicehashClient()
    # c.get_balance()
    # c.check_payments()
    # c.check_workers()
    # c.send_notification(c.notification_text)
    while True:
        c.check_workers()
        time.sleep(60 * 2)


if __name__ == '__main__':
    main()

