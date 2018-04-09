import hmac, hashlib
import requests
import os
from conf import yobit_config
import cfscrape


directory = os.path.dirname(os.path.abspath(__file__))
nonce_file = "nonce_count"
path = os.path.join(directory, nonce_file)
if not os.path.exists(path):
    with open(path, "w") as f:
        f.write('1')


def get_concurrency(from_currency='btc', to_currency='rur'):
    pair_name = '{}_{}'.format(from_currency, to_currency)
    url = 'https://yobit.net/api/3/ticker/{}'.format(pair_name)
    #  Пытаемся получить курс валюты в рублях с помощью библиотеки requests
    try:
        res = requests.get(url).json()
        if pair_name in res:
            return res[pair_name]['sell']
    except:
        try:
            # В случае включение защиты сайта Yobit от DDoS получаем курсы через cfscrape
            scraper = cfscrape.create_scraper()
            res = scraper.get(url).json()
            if pair_name in res:
                return res[pair_name]['buy']
        except:
            pass
        return None


def how_to_sell_my_btc():
    btc_to_rur_concurrency = get_concurrency()
    btc_to_usd_concurrency = get_concurrency(to_currency='usd')
    eth_to_rur_concurrency = get_concurrency(from_currency='eth')
    eth_to_usd_concurrency = get_concurrency(from_currency='eth',
                                             to_currency='usd')
    return '1 BTC = {:.2f}руб;\n' \
           '1 BTC = {:.2f}usd;\n' \
           '1 ETH = {:.2f}руб;\n' \
           '1 ETH = {:.2f}usd;'.format(btc_to_rur_concurrency,
                                       btc_to_usd_concurrency,
                                       eth_to_rur_concurrency,
                                       eth_to_usd_concurrency)


def api_call(**kwargs):
    request_url = "https://yobit.io/tapi"
    result = ''
    with open(path, 'r+') as f:
        nonce = int(f.read())
        f.seek(0)
        f.write(str(nonce + 1))
        f.truncate()
    key = yobit_config['key']
    secret = bytes(yobit_config['secret'].encode('utf-8'))
    params = {'nonce': nonce}
    if kwargs:
        params.update(kwargs)
    # print('params: ', params)
    H = hmac.new(key=secret, digestmod=hashlib.sha512)
    request_body = ''
    for counter, k in enumerate(params.keys()):
        if counter:
            request_body += '&'
        request_body += '{}={}'.format(k, params[k])
    # print('request_body: ', request_body)
    H.update(bytes(request_body.encode('utf-8')))
    sign = H.hexdigest()
    http_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Key": key,
        "Sign": sign
    }
    scraper = cfscrape.create_scraper()
    try:
        req = scraper.post(request_url, params, headers=http_headers)
        data = req.json()
        # print(data)
        if 'error' in data:
            return 'Ошибка при выполнении запроса: {}'.format(data['error'])
        else:
            funds = data['return']['funds']
            for fund_name, value in funds.items():
                currency = get_concurrency(fund_name)
                if currency:
                    result += '{}: {} ({:.2f} рублей)\n'.format(fund_name,
                                                                value,
                                                                value * currency)
                else:
                    result += '{}: {}\n'.format(fund_name, value)
            return result
    except Exception as e:
        return 'Ошибка при выполнении запроса: {}'.format(e)


if __name__ == '__main__':
    print(api_call(method='getInfo'))
