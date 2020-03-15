import logging
import os
import socket
import sys
from threading import Thread

from telegram.error import TelegramError
from telegram.ext import Updater, CommandHandler

from conf import nicehash_config, telegram_config
from nicehash import private_api
from yobit import api_call, get_concurrency, how_to_sell_my_btc

directory = os.path.dirname(os.path.abspath(__file__))
log_filename = os.path.join(directory, 'worker.log')
logging.basicConfig(filename=log_filename, level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

nicehash_api = private_api('https://api2.nicehash.com',
                           nicehash_config['org_id'],
                           nicehash_config['key'],
                           nicehash_config['secret'])

updater = Updater(token=telegram_config['api_token'])

dispatcher = updater.dispatcher


class NicehashClient:

    def __init__(self):
        self.notification_text = ''

    def get_balance(self):
        balance_btc = private_api.get_accounts_for_currency('BTC')
        concurrency = get_concurrency()
        if concurrency:
            balance_rub = balance_btc * concurrency
            self.notification_text += 'Баланс кошелька: {:.2f} RUB ({:.8f} BTC)\n'.format(balance_rub, balance_btc)
        else:
            self.notification_text += 'Баланс кошелька: {:.8f} BTC\n'.format(balance_btc)

    def send_notification(self):
        bot = dispatcher.bot
        logging.info('Отправка сообщения: {}'.format(self.notification_text))
        try:
            bot.send_message(chat_id=telegram_config['my_telegram_id'], text=self.notification_text)
        except (socket.error, TelegramError) as e:
            logging.warning('Ошибка отправки сообщения: {}'.format(e))
        self.notification_text = ''


def main():
    logging.info('Запуск телеграм-бота')

    c = NicehashClient()

    def stop_and_restart():
        """Останавливаем бота и перезапускаем процесс"""
        updater.stop()
        os.execl(sys.executable, sys.executable, *sys.argv)

    # КОМАНДЫ БОТА
    def start(bot, update):
        logging.info('Получена команда /start от chat_id = {}'.format(update.message.chat_id))
        bot.send_message(chat_id=telegram_config['my_telegram_id'], text="Добрый день, хозяинъ!")

    def balance(bot, update=None):
        logging.info('Получена команда /balance')
        c.get_balance()
        c.send_notification()

    def error(bot, update, error):
        logging.warning('Update "%s" caused error "%s"' % (update, error))
        logging.warning('Перезагрузка бота...')
        Thread(target=stop_and_restart).start()

    def yobit(bot, update):
        logging.info('Получена команда /yobit')
        c.notification_text = api_call(method='getInfo')
        c.send_notification()

    def sell(bot, update):
        logging.info('Получена команда /sell')
        c.notification_text = how_to_sell_my_btc()
        c.send_notification()

    # ХЕНДЛЕРЫ БОТА
    start_handler = CommandHandler('start', start)
    balance_handler = CommandHandler('balance', balance)
    yobit_handler = CommandHandler('yobit', yobit)
    sell_handler = CommandHandler('sell', sell)
    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(balance_handler)
    dispatcher.add_handler(yobit_handler)
    dispatcher.add_handler(sell_handler)
    # log all errors
    dispatcher.add_error_handler(error)

    # ЗАПУСК БОТА
    updater.start_polling()
    balance(bot=dispatcher.bot)  # Запрос баланса


if __name__ == '__main__':
    main()
