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
        'adjustment': 'split',
        'feed': 'iex'
    }
    all_bars = {}
    while True:
        response = requests.get(url, headers=ALPACA_HEADERS, params=params)
        if response.status_code != 200:
            print(f'Batch failed: status {response.status_code}, response: {response.text[:300]}')
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


def check_cup_handle(bars):
    if len(bars) < 260:
        return 'not_enough_data'

    df = pd.DataFrame(bars)
    df['t'] = pd.to_datetime(df['t'])
    df = df.sort_values('t').reset_index(drop=True)

    window = df.tail(300).reset_index(drop=True)
    closes = window['c'].values
    n = len(closes)

    peak_span = 10
    candidates = []
    for i in range(30, n - 40):
        segment = closes[i - peak_span:i + peak_span + 1]
        if closes[i] == segment.max():
            candidates.append(i)

    if not candidates:
        return 'no_left_rim_found'

    for left_idx in reversed(candidates):
        left_price = closes[left_idx]

        lead_in_start = max(0, left_idx - 60)
        lead_in_end = max(lead_in_start + 1, left_idx - 15)
        lead_in_price = closes[lead_in_start:lead_in_end].mean()
        if lead_in_price <= 0:
            continue
        prior_gain_pct = (left_price - lead_in_price) / lead_in_price * 100
        if prior_gain_pct < 20:
            continue

        search_zone = closes[left_idx:]
        if len(search_zone) < 40:
            continue

        cup_search_end = min(len(search_zone), 180)
        cup_zone = search_zone[:cup_search_end]
        bottom_rel = int(cup_zone.argmin())
        bottom_idx = left_idx + bottom_rel
        bottom_price = closes[bottom_idx]

        cup_depth_pct = (left_price - bottom_price) / left_price * 100
        if cup_depth_pct < 12 or cup_depth_pct > 50:
            continue

        right_search = closes[bottom_idx:left_idx + cup_search_end]
        if len(right_search) < 10:
            continue
        right_rel = int(right_search.argmax())
        right_idx = bottom_idx + right_rel
        right_price = closes[right_idx]

        recovery_pct = (right_price - left_price) / left_price * 100
        if recovery_pct < -15:
            continue

        cup_length = right_idx - left_idx
        if cup_length < 25 or cup_length > 260:
            continue

        handle_data = closes[right_idx:]
        if len(handle_data) < 5 or len(handle_data) > 40:
            continue

        handle_low = handle_data.min()
        handle_depth_pct = (right_price - handle_low) / right_price * 100
        if handle_depth_pct > 15:
            continue
        if handle_depth_pct > cup_depth_pct * 0.6:
            continue

        cup_midpoint = (left_price + bottom_price) / 2
        if handle_low < cup_midpoint:
            continue

        current_price = closes[-1]
        if current_price < right_price * 0.90:
            continue

        return 'match'

    return 'no_valid_cup_found'


def send_telegram_message(text):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    for i in range(0, len(text), 4000):
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': text[i:i + 4000]})


def main():
    today = datetime.date.today()
    if today.weekday() >= 5:
        return

    end_date = today.isoformat()
    start_date = (today - datetime.timedelta(days=500)).isoformat()

    stocks = get_us_common_stocks()
    print(f'Scanning {len(stocks)} stocks...')

    vcp_matches = []
    cup_matches = []
    vcp_stage_counts = {}
    cup_stage_counts = {}
    batch_size = 200

    for i in range(0, len(stocks), batch_size):
        batch = stocks[i:i + batch_size]
        bars_by_symbol = fetch_bars_batch(batch, start_date, end_date)
        for symbol, bars in bars_by_symbol.items():
            vcp_result = check_vcp(bars)
            vcp_stage_counts[vcp_result] = vcp_stage_counts.get(vcp_result, 0) + 1
            if vcp_result == 'match':
                vcp_matches.append(symbol)

            cup_result = check_cup_handle(bars)
            cup_stage_counts[cup_result] = cup_stage_counts.get(cup_result, 0) + 1
            if cup_result == 'match':
                cup_matches.append(symbol)

        print(f'Processed {min(i + batch_size, len(stocks))}/{len(stocks)}, VCP: {len(vcp_matches)}, Cup&Handle: {len(cup_matches)}')
        time.sleep(1)

    print('VCP funnel:', vcp_stage_counts)
    print('Cup & Handle funnel:', cup_stage_counts)

    message = 'Pattern Scan Results - ' + today.isoformat() + '\n\n'
    message += 'VCP candidates (' + str(len(vcp_matches)) + '):\n'
    message += ('\n'.join(vcp_matches) if vcp_matches else 'None found today') + '\n\n'
    message += 'Cup & Handle candidates (' + str(len(cup_matches)) + '):\n'
    message += ('\n'.join(cup_matches) if cup_matches else 'None found today')

    send_telegram_message(message)


if __name__ == '__main__':
    main()
