import hmac, hashlib
import requests
import os
from conf import yobit_config


nonce_file = "nonce_count"
if not os.path.exists(nonce_file):
    with open(nonce_file, "w") as f:
        f.write('2')


def get_concurrency_in_rub(currency):
    pair_name = '{}_rur'.format(currency)
    url = 'https://yobit.net/api/3/ticker/' + pair_name
    try:
        res = requests.get(url).json()
        if pair_name in res:
            return res[pair_name]['sell']
    except:
        return None


def api_call(**kwargs):
    request_url = "https://yobit.io/tapi"
    result = ''
    with open(nonce_file, 'r+') as f:
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
    req = requests.post(request_url, params, headers=http_headers)
    # print(sign)
    data = req.json()
    # print(data)
    if 'error' in data:
        return 'Ошибка при выполнении запроса: {}'.format(data['error'])
    else:
        funds = data['return']['funds']
        for fund_name, value in funds.items():
            currency = get_concurrency_in_rub(fund_name)
            if currency:
                result += '{}: {} ({:.2f} рублей)\n'.format(fund_name,
                                                            value,
                                                            value * currency)
            else:
                result += '{}: {} ({:.6f} монет)\n'.format(fund_name,
                                                           value)
        return result
