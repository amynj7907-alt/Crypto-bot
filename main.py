import os
import requests
import time
from datetime import datetime, timezone, timedelta

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PROXY_URL = os.getenv("PROXY_URL", "")

TOOBIT_API = "https://api.toobit.com/quote/v1"
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

BASE_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT',
                'BNBUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT']

MIN_SCORE = 65
MIN_SL_PCT = 0.008
CHECK_INTERVAL = 3600

SIGNAL_MEMORY = {}
JOURNAL = []

def toobit_klines(symbol, interval='15m', limit=300):
    try:
        url = f"{TOOBIT_API}/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            return None
        return [{
            'time': int(k[0]),
            'open': float(k[1]),
            'high': float(k[2]),
            'low': float(k[3]),
            'close': float(k[4]),
            'volume': float(k[5])
        } for k in data]
    except Exception as e:
        print(f"KLINES ERROR {symbol}: {e}")
        return None

def toobit_tickers():
    try:
        r = requests.get(f"{TOOBIT_API}/tickers", timeout=15)
        return r.json()
    except Exception as e:
        print(f"TICKERS ERROR: {e}")
        return None

def ema(data, period):
    if len(data) < period:
        return [None] * len(data)
    result = [None] * (period - 1)
    multiplier = 2 / (period + 1)
    sma = sum(data[:period]) / period
    result.append(sma)
    for price in data[period:]:
        sma = (price - sma) * multiplier + sma
        result.append(sma)
    return result

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return [None] * len(closes)
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsis = [None] * period
    rs = avg_gain / (avg_loss + 1e-10)
    rsis.append(100 - (100 / (1 + rs)))
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / (avg_loss + 1e-10)
        rsis.append(100 - (100 / (1 + rs)))
    return rsis

def macd(closes, fast=12, slow=26, signal=9):
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [f - s if f and s else None for f, s in zip(ema_fast, ema_slow)]
    valid = [m for m in macd_line if m is not None]
    if len(valid) < signal:
        return macd_line, [None] * len(macd_line), [None] * len(macd_line)
    signal_line = ema(valid, signal)
    signal_line = [None] * (len(macd_line) - len(signal_line)) + signal_line
    histogram = [m - s if m and s else None for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram

def atr(klines, period=14):
    if len(klines) < period + 1:
        return [None] * len(klines)
    trs = [None]
    for i in range(1, len(klines)):
        h, l, pc = klines[i]['high'], klines[i]['low'], klines[i-1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atrs = [None] * period
    sma = sum(trs[1:period+1]) / period
    atrs.append(sma)
    for tr in trs[period+1:]:
        sma = (sma * (period - 1) + tr) / period
        atrs.append(sma)
    return atrs

def detect_bos(klines, lookback=20):
    if len(klines) < lookback + 5:
        return None
    highs = [k['high'] for k in klines[-lookback-5:-1]]
    lows = [k['low'] for k in klines[-lookback-5:-1]]
    last_close = klines[-1]['close']
    if last_close > max(highs):
        return 'BULLISH_BOS'
    elif last_close < min(lows):
        return 'BEARISH_BOS'
    return None

def detect_choch(klines, lookback=10):
    if len(klines) < lookback * 2:
        return None
    rh = [k['high'] for k in klines[-lookback:]]
    rl = [k['low'] for k in klines[-lookback:]]
    ph = [k['high'] for k in klines[-lookback*2:-lookback]]
    pl = [k['low'] for k in klines[-lookback*2:-lookback]]
    if max(rh) < max(ph) and min(rl) > min(pl):
        return 'BULLISH_CHOCH'
    elif max(rh) > max(ph) and min(rl) < min(pl):
        return 'BEARISH_CHOCH'
    return None

def detect_fvg(klines):
    if len(klines) < 3:
        return None
    k1, k2, k3 = klines[-3], klines[-2], klines[-1]
    if k1['high'] < k3['low']:
        return {'type': 'BULLISH_FVG', 'top': k3['low'], 'bottom': k1['high']}
    if k1['low'] > k3['high']:
        return {'type': 'BEARISH_FVG', 'top': k1['low'], 'bottom': k3['high']}
    return None

def detect_engulfing(klines):
    if len(klines) < 2:
        return None
    prev, curr = klines[-2], klines[-1]
    body_prev = abs(prev['close'] - prev['open'])
    body_curr = abs(curr['close'] - curr['open'])
    if body_curr < body_prev:
        return None
    if curr['close'] > curr['open'] and prev['close'] < prev['open']:
        if curr['close'] > prev['open'] and curr['open'] < prev['close']:
            return 'BULLISH_ENGULF'
    elif curr['close'] < curr['open'] and prev['close'] > prev['open']:
        if curr['close'] < prev['open'] and curr['open'] > prev['close']:
            return 'BEARISH_ENGULF'
    return None

def detect_liquidity_sweep(klines, lookback=20):
    if len(klines) < lookback + 1:
        return None
    ph = [k['high'] for k in klines[-lookback-1:-1]]
    pl = [k['low'] for k in klines[-lookback-1:-1]]
    last = klines[-1]
    if last['high'] > max(ph) and last['close'] < max(ph):
        return 'BEARISH_SWEEP'
    if last['low'] < min(pl) and last['close'] > min(pl):
        return 'BULLISH_SWEEP'
    return None

def analyze(symbol):
    try:
        k4h = toobit_klines(symbol, '4h', 200)
        k1h = toobit_klines(symbol, '1h', 200)
        k15m = toobit_klines(symbol, '15m', 300)
        k5m = toobit_klines(symbol, '5m', 300)
        if not all([k4h, k1h, k15m, k5m]):
            return None
        c4h = [k['close'] for k in k4h]
        c1h = [k['close'] for k in k1h]
        c15m = [k['close'] for k in k15m]
        ema50_4h = ema(c4h, 50)
        ema200_4h = ema(c4h, 200)
        trend_4h = 0
        if ema50_4h[-1] and ema200_4h[-1]:
            trend_4h = 1 if ema50_4h[-1] > ema200_4h[-1] else -1
        ema50_1h = ema(c1h, 50)
        ema200_1h = ema(c1h, 200)
        trend_1h = 0
        if ema50_1h[-1] and ema200_1h[-1]:
            trend_1h = 1 if ema50_1h[-1] > ema200_1h[-1] else -1
        if trend_4h == 0 or trend_1h == 0:
            return None
        rsi_15m = rsi(c15m, 14)
        macd_line, signal_line, hist = macd(c15m)
        atr_5m = atr(k5m, 14)
        if not rsi_15m[-1] or not macd_line[-1] or not atr_5m[-1]:
            return None
        bos = detect_bos(k15m)
        choch = detect_choch(k15m)
        fvg = detect_fvg(k15m)
        engulf = detect_engulfing(k15m)
        sweep = detect_liquidity_sweep(k15m)
        score = 0
        reasons = []
        warnings = []
        if trend_4h == trend_1h:
            score += 20
            reasons.append(f"روند {'صعودی' if trend_4h == 1 else 'نزولی'}")
        else:
            return None
        direction = trend_4h
        if direction == 1 and bos == 'BULLISH_BOS':
            score += 15; reasons.append("BOS صعودی")
        elif direction == -1 and bos == 'BEARISH_BOS':
            score += 15; reasons.append("BOS نزولی")
        if direction == 1 and choch == 'BULLISH_CHOCH':
            score += 10; reasons.append("CHoCH صعودی")
        elif direction == -1 and choch == 'BEARISH_CHOCH':
            score += 10; reasons.append("CHoCH نزولی")
        if direction == 1 and sweep == 'BULLISH_SWEEP':
            score += 15; reasons.append("Sweep صعودی")
        elif direction == -1 and sweep == 'BEARISH_SWEEP':
            score += 15; reasons.append("Sweep نزولی")
        if fvg:
            if direction == 1 and fvg['type'] == 'BULLISH_FVG':
                score += 10; reasons.append("FVG صعودی")
            elif direction == -1 and fvg['type'] == 'BEARISH_FVG':
                score += 10; reasons.append("FVG نزولی")
        if direction == 1 and engulf == 'BULLISH_ENGULF':
            score += 10; reasons.append("Engulfing صعودی")
        elif direction == -1 and engulf == 'BEARISH_ENGULF':
            score += 10; reasons.append("Engulfing نزولی")
        if direction == 1 and 45 < rsi_15m[-1] < 65:
            score += 10; reasons.append(f"RSI: {rsi_15m[-1]:.1f}")
        elif direction == -1 and 35 < rsi_15m[-1] < 55:
            score += 10; reasons.append(f"RSI: {rsi_15m[-1]:.1f}")
        elif (direction == 1 and rsi_15m[-1] > 75) or (direction == -1 and rsi_15m[-1] < 25):
            warnings.append(f"RSI اشباع: {rsi_15m[-1]:.1f}")
        if direction == 1 and macd_line[-1] > signal_line[-1] and hist[-1] > hist[-2]:
            score += 10; reasons.append("MACD صعودی")
        elif direction == -1 and macd_line[-1] < signal_line[-1] and hist[-1] < hist[-2]:
            score += 10; reasons.append("MACD نزولی")
        if score < MIN_SCORE:
            return None
        entry = k5m[-1]['close']
        atr_val = atr_5m[-1]
        sl_pct = max(atr_val * 1.5 / entry, MIN_SL_PCT)
        if direction == 1:
            sl = entry * (1 - sl_pct)
            tp1 = entry * (1 + sl_pct * 2)
            tp2 = entry * (1 + sl_pct * 3)
            signal = "LONG"
        else:
            sl = entry * (1 + sl_pct)
            tp1 = entry * (1 - sl_pct * 2)
            tp2 = entry * (1 - sl_pct * 3)
            signal = "SHORT"
        return {
            'symbol': symbol, 'signal': signal, 'score': score,
            'direction': direction, 'entry': entry, 'sl': sl,
            'tp1': tp1, 'tp2': tp2, 'sl_pct': sl_pct * 100,
            'rsi': rsi_15m[-1], 'reasons': reasons, 'warnings': warnings
        }
    except Exception as e:
        print(f"ANALYZE ERROR {symbol}: {e}")
        return None

def send_telegram(message):
    try:
        if PROXY_URL:
            url = f"{PROXY_URL}/bot{TOKEN}/sendMessage"
        else:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        r = requests.post(url, data=data, timeout=20)
        return r.json()
    except Exception as e:
        print(f"TELEGRAM ERROR: {e}")
        return None

def format_signal(s):
    msg = f"<b>{s['signal']} - {s['symbol']}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"امتیاز اطمینان: <b>{s['score']}%</b>\n"
    msg += f"ورود: <code>{s['entry']:.6f}</code>\n"
    msg += f"SL: <code>{s['sl']:.6f}</code> ({s['sl_pct']:.2f}%)\n"
    msg += f"TP1: <code>{s['tp1']:.6f}</code>\n"
    msg += f"TP2: <code>{s['tp2']:.6f}</code>\n"
    msg += f"RSI: {s['rsi']:.1f}\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += "دلایل:\n"
    for r in s['reasons']:
        msg += f"  {r}\n"
    if s['warnings']:
        msg += "هشدارها:\n"
        for w in s['warnings']:
            msg += f"  {w}\n"
    now = datetime.now(IRAN_TZ).strftime("%Y-%m-%d %H:%M")
    msg += f"━━━━━━━━━━━━━━━━━━\n{now}"
    return msg

def get_active_symbols():
    tickers = toobit_tickers()
    if not tickers or not isinstance(tickers, dict):
        return BASE_SYMBOLS
    active = []
    for symbol, data in tickers.items():
        if symbol.endswith('USDT'):
            active.append(symbol)
    all_symbols = list(set(BASE_SYMBOLS + active[:30]))
    return all_symbols[:30]

def run_check():
    print(f"\n{'='*50}")
    print(f"CHECK: {datetime.now(IRAN_TZ).strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")
    symbols = get_active_symbols()
    print(f"Scanning {len(symbols)} symbols...")
    signals_found = 0
    for symbol in symbols:
        result = analyze(symbol)
        if not result:
            continue
        signal_key = f"{symbol}_{result['signal']}"
        last_time = SIGNAL_MEMORY.get(signal_key, 0)
        now = time.time()
        if now - last_time < 4 * 3600:
            continue
        msg = format_signal(result)
        send_telegram(msg)
        SIGNAL_MEMORY[signal_key] = now
        signals_found += 1
        JOURNAL.append({
            'time': now, 'symbol': symbol, 'signal': result['signal'],
            'score': result['score'], 'entry': result['entry'],
            'sl': result['sl'], 'tp1': result['tp1'], 'tp2': result['tp2']
        })
        print(f"SIGNAL: {symbol} | {result['signal']} | {result['score']}%")
        time.sleep(2)
    if signals_found == 0:
        print("No signals.")
    print(f"Done. Total signals sent: {len(JOURNAL)}")

if __name__ == '__main__':
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set!")
        exit(1)
    if not CHAT_ID:
        print("ERROR: TELEGRAM_CHAT_ID not set!")
        exit(1)
    print("="*50)
    print("AMIN SMART MONEY BOT")
    print("Toobit API - Direct")
    print("="*50)
    print(f"Token: {TOKEN[:15]}...")
    print(f"Chat ID: {CHAT_ID}")
    print("="*50)
    start_msg = "<b>ربات Smart Money فعال شد!</b>\n"
    start_msg += "━━━━━━━━━━━━━━━━━━\n"
    start_msg += "صرافی: توبیت (مستقیم)\n"
    start_msg += "استراتژی: Smart Money\n"
    start_msg += "اسکن خودکار: فعال\n"
    start_msg += "ضد تکرار: فعال\n"
    start_msg += "هر 1 ساعت بررسی می‌کنم\n"
    start_msg += "━━━━━━━━━━━━━━━━━━"
    send_telegram(start_msg)
    while True:
        try:
            run_check()
        except Exception as e:
            print(f"MAIN LOOP ERROR: {e}")
        print(f"Sleeping {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)
