import os
import time
import datetime
import requests
import pandas as pd

FINNHUB_API_KEY = os.environ['FINNHUB_API_KEY']
ALPACA_KEY = os.environ['ALPACA_API_KEY']
ALPACA_SECRET = os.environ['ALPACA_SECRET_KEY']
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

MAJOR_EXCHANGES = ['XNYS', 'XNAS', 'XNGS', 'XNMS', 'XNCM', 'XASE', 'ARCX', 'BATS', 'IEXG']
ALPACA_HEADERS = {
    'APCA-API-KEY-ID': ALPACA_KEY,
    'APCA-API-SECRET-KEY': ALPACA_SECRET
}


def get_us_common_stocks():
    url = f'https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_API_KEY}'
    response = requests.get(url)
    all_symbols = response.json()
    return [
        s['symbol'] for s in all_symbols
        if s.get('type') == 'Common Stock' and s.get('mic') in MAJOR_EXCHANGES
    ]


def fetch_bars_batch(symbols, start_date, end_date):
    url = 'https://data.alpaca.markets/v2/stocks/bars'
    params = {
        'symbols': ','.join(symbols),
        'timeframe': '1Day',
        'start': start_date,
        'end': end_date,
        'limit': 10000,
        'adjustment': 'split'
    }
    all_bars = {}
    while True:
        response = requests.get(url, headers=ALPACA_HEADERS, params=params)
        if response.status_code != 200:
            break
        data = response.json()
        bars = data.get('bars') or {}
        for symbol, bar_list in bars.items():
            all_bars.setdefault(symbol, []).extend(bar_list)
        token = data.get('next_page_token')
        if not token:
            break
        params['page_token'] = token
    return all_bars


def check_vcp(bars):
    if len(bars) < 160:
        return 'not_enough_data'

    df = pd.DataFrame(bars)
    df['t'] = pd.to_datetime(df['t'])
    df = df.sort_values('t').reset_index(drop=True)

    df['sma50'] = df['c'].rolling(50).mean()
    df['sma150'] = df['c'].rolling(150).mean()

    last = df.iloc[-1]
    if pd.isna(last['sma50']) or pd.isna(last['sma150']):
        return 'not_enough_data'

    in_uptrend = (last['c'] > last['sma50']) and (last['c'] > last['sma150']) and (last['sma50'] > last['sma150'])
    if not in_uptrend:
        return 'not_in_uptrend'

    recent = df.tail(60).reset_index(drop=True)
    swing_highs = []
    swing_lows = []
    window = 3

    for i in range(window, len(recent) - window):
        seg_h = recent['h'][i - window:i + window + 1]
        seg_l = recent['l'][i - window:i + window + 1]
        if recent['h'][i] == seg_h.max():
            swing_highs.append(i)
        if recent['l'][i] == seg_l.min():
            swing_lows.append(i)

    pullbacks = []
    for h in swing_highs:
        later_lows = [l for l in swing_lows if l > h]
        if later_lows:
            l = later_lows[0]
            depth_pct = (recent['h'][h] - recent['l'][l]) / recent['h'][h] * 100
            avg_volume = recent['v'][h:l + 1].mean()
            pullbacks.append({'depth': depth_pct, 'volume': avg_volume})

    if len(pullbacks) < 2:
        return 'not_enough_pullbacks'

    depths = [p['depth'] for p in pullbacks[-3:]]
    contracting = all(depths[i] > depths[i + 1] for i in range(len(depths) - 1))

    volumes = [p['volume'] for p in pullbacks[-3:]]
    volume_drying_up = all(volumes[i] > volumes[i + 1] for i in range(len(volumes) - 1))

    if not contracting:
        return 'not_contracting'
    if not volume_drying_up:
        return 'volume_not_drying_up'

    return 'match'


def send_telegram_message(text):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    for i in range(0, len(text), 4000):
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': text[i:i + 4000]})


def main():
    today = datetime.date.today()
    if today.weekday() >= 5:
        return

    end_date = today.isoformat()
    start_date = (today - datetime.timedelta(days=300)).isoformat()

    stocks = get_us_common_stocks()
    print(f'Scanning {len(stocks)} stocks...')

    matches = []
    stage_counts = {}
    batch_size = 200

    for i in range(0, len(stocks), batch_size):
        batch = stocks[i:i + batch_size]
        bars_by_symbol = fetch_bars_batch(batch, start_date, end_date)
        for symbol, bars in bars_by_symbol.items():
            result = check_vcp(bars)
            stage_counts[result] = stage_counts.get(result, 0) + 1
            if result == 'match':
                matches.append(symbol)
        print(f'Processed {min(i + batch_size, len(stocks))}/{len(stocks)}, matches so far: {len(matches)}')
        time.sleep(1)

    print('Funnel breakdown:', stage_counts)

    if matches:
        message = f'VCP candidates found ({len(matches)}):\n' + '\n'.join(matches)
    else:
        message = 'No VCP candidates found today.'

    send_telegram_message(message)


if __name__ == '__main__':
    main()
