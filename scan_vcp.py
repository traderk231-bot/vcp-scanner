def test_alpaca_access():
    ALPACA_KEY = os.environ['ALPACA_API_KEY']
    ALPACA_SECRET = os.environ['ALPACA_SECRET_KEY']
    headers = {
        'APCA-API-KEY-ID': ALPACA_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET
    }
    url = 'https://data.alpaca.markets/v2/stocks/bars'
    params = {
        'symbols': 'AAPL',
        'timeframe': '1Day',
        'start': '2026-01-01',
        'end': '2026-07-01',
        'limit': 1000
    }
    response = requests.get(url, headers=headers, params=params)
    print('Status code:', response.status_code)
    print('Response:', response.text[:500])

if __name__ == '__main__':
    test_alpaca_access()
