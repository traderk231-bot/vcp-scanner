import os
import requests

FINNHUB_API_KEY = os.environ['FINNHUB_API_KEY']

def get_us_common_stocks():
    url = f'https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_API_KEY}'
    response = requests.get(url)
    all_symbols = response.json()

    # Keep only common stocks - this skips ETFs, ADRs, warrants, etc.
    common_stocks = [s for s in all_symbols if s.get('type') == 'Common Stock']

    return common_stocks

if __name__ == '__main__':
    stocks = get_us_common_stocks()
    print(f'Total common stocks found: {len(stocks)}')
    print('First 10 examples:')
    for s in stocks[:10]:
        print(s['symbol'], '-', s['description'])
