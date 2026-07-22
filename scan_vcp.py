import os
import requests

FINNHUB_API_KEY = os.environ['FINNHUB_API_KEY']

# Real stock exchanges only - this excludes OTC/pink-sheet penny stocks
MAJOR_EXCHANGES = ['XNYS', 'XNAS', 'XNGS', 'XNMS', 'XNCM', 'XASE', 'ARCX', 'BATS', 'IEXG']

def get_us_common_stocks():
    url = f'https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_API_KEY}'
    response = requests.get(url)
    all_symbols = response.json()

    common_stocks = [
        s for s in all_symbols
        if s.get('type') == 'Common Stock' and s.get('mic') in MAJOR_EXCHANGES
    ]

    return common_stocks

import time

def test_candle_access():
    to_ts = int(time.time())
    from_ts = to_ts - (180 * 24 * 60 * 60)  # 6 months back
    url = f'https://finnhub.io/api/v1/stock/candle?symbol=AAPL&resolution=D&from={from_ts}&to={to_ts}&token={FINNHUB_API_KEY}'
    response = requests.get(url)
    print('Status code:', response.status_code)
    print('Response:', response.text[:500])

if __name__ == '__main__':
    test_candle_access()
