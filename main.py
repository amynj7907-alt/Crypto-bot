import os
import requests
import time
from datetime import datetime, timezone, timedelta

# ================== تنظیمات ==================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PROXY_URL = os.getenv("PROXY_URL", "")

TOOBIT_API = "https://api.toobit.com/quote/v1"
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

# تنظیمات اسکلپ
SCALP_TIMEFRAME = "15m"
SCALP_MIN_SCORE = 50
SCALP_CHECK_INTERVAL = 300  # ۵ دقیقه
SCALP_ANTI_DUP = 3600  # ۱ ساعت

# تنظیمات سویینگ
SWING_TIMEFRAME_1 = "1h"
SWING_TIMEFRAME_2 = "4h"
SWING_MIN_SCORE = 50
SWING_CHECK_INTERVAL = 1800  # ۳۰ دقیقه
SWING_ANTI_DUP = 14400  # ۴ ساعت

# حافظه ضد تکرار
SIGNAL_MEMORY = {}

# ================== توابع توبیت ==================
def toobit_klines(symbol, interval="15m", limit=300):
    """دریافت کندل‌ها از توبیت"""
    try:
        url = f"{TOOBIT_API}/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            return None
        return [{
            "time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5])
        } for k in data]
    except Exception as e:
        print(f"KLINES ERROR {symbol}: {e}")
        return None

def toobit_tickers():
    """دریافت همه تیکرها (برای شکارچی)"""
    try:
        r = requests.get(f"{TOOBIT_API}/ticker/24hr", timeout=15)
        return r.json()
    except Exception as e:
        print(f"TICKERS ERROR: {e}")
        return None

def get_active_symbols():
    """شکارچی: ۳۰ نماد پرحجم"""
    tickers = toobit_tickers()
    if not tickers or not isinstance(tickers, dict):
        # fallback
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
                "BNBUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"]
    
    # فیلتر: USDT + حجم بالا
    active = []
    for symbol, data in tickers.items():
        if symbol.endswith("USDT") and "volume" in str(data).lower():
            active.append(symbol)
    
    # ۳۰ نماد اول
    return active[:30] if len(active) >= 30 else active

# ================== اندیکاتورها ==================
def ema(data, period):
    """میانگین متحرک نمایی"""
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
    """شاخص قدرت نسبی"""
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
    """MACD"""
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
    """ATR"""
    if len(klines) < period + 1:
        return [None] * len(klines)
    trs = [None]
    for i in range(1, len(klines)):
        h, l, pc = klines[i]["high"], klines[i]["low"], klines[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atrs = [None] * period
    sma = sum(trs[1:period+1]) / period
    atrs.append(sma)
    for tr in trs[period+1:]:
        sma = (sma * (period - 1) + tr) / period
        atrs.append(sma)
    return atrs

# ================== Smart Money ==================
def detect_bos(klines, lookback=20):
    """Break of Structure"""
    if len(klines) < lookback + 5:
        return None
    highs = [k["high"] for k in klines[-lookback-5:-1]]
    lows = [k["low"] for k in klines[-lookback-5:-1]]
    last_close = klines[-1]["close"]
    
    if last_close > max(highs):
        return "BULLISH_BOS"
    elif last_close < min(lows):
        return "BEARISH_BOS"
    return None

def detect_choch(klines, lookback=10):
    """Change of Character"""
    if len(klines) < lookback * 2:
        return None
    rh = [k["high"] for k in klines[-lookback:]]
    rl = [k["low"] for k in klines[-lookback:]]
    ph = [k["high"] for k in klines[-lookback*2:-lookback]]
    pl = [k["low"] for k in klines[-lookback*2:-lookback]]
    
    if max(rh) < max(ph) and min(rl) > min(pl):
        return "BULLISH_CHOCH"
    elif max(rh) > max(ph) and min(rl) < min(pl):
        return "BEARISH_CHOCH"
    return None

def detect_fvg(klines):
    """Fair Value Gap"""
    if len(klines) < 3:
        return None
    k1, k2, k3 = klines[-3], klines[-2], klines[-1]
    
    if k1["high"] < k3["low"]:
        return {"type": "BULLISH_FVG", "top": k3["low"], "bottom": k1["high"]}
    if k1["low"] > k3["high"]:
        return {"type": "BEARISH_FVG", "top": k1["low"], "bottom": k3["high"]}
    return None

def detect_engulfing(klines):
    """کندل اینگولفینگ"""
    if len(klines) < 2:
        return None
    prev, curr = klines[-2], klines[-1]
    body_prev = abs(prev["close"] - prev["open"])
    body_curr = abs(curr["close"] - curr["open"])
    
    if body_curr < body_prev:
        return None
    
    if curr["close"] > curr["open"] and prev["close"] < prev["open"]:
        if curr["close"] > prev["open"] and curr["open"] < prev["close"]:
            return "BULLISH_ENGULF"
    elif curr["close"] < curr["open"] and prev["close"] > prev["open"]:
        if curr["close"] < prev["open"] and curr["open"] > prev["close"]:
            return "BEARISH_ENGULF"
    return None

def detect_liquidity_sweep(klines, lookback=20):
    """Liquidity Sweep"""
    if len(klines) < lookback + 1:
        return None
    ph = [k["high"] for k in klines[-lookback-1:-1]]
    pl = [k["low"] for k in klines[-lookback-1:-1]]
    last = klines[-1]
    
    if last["high"] > max(ph) and last["close"] < max(ph):
        return "BEARISH_SWEEP"
    if last["low"] < min(pl) and last["close"] > min(pl):
        return "BULLISH_SWEEP"
    return None

def detect_order_block(klines, lookback=10):
    """Order Block"""
    if len(klines) < lookback + 2:
        return None
    
    # بررسی ۱۰ کندل آخر
    for i in range(-lookback, -1):
        curr = klines[i]
        next_k = klines[i+1] if i+1 < 0 else klines[-1]
        
        body = abs(curr["close"] - curr["open"])
        if body < 0.001:
            continue
        
        # کندل سبز کوچیک + حرکت صعودی قوی
        if curr["close"] > curr["open"]:
            move = next_k["close"] - next_k["open"]
            if move > body * 2:
                return {"type": "BULLISH_OB", "low": curr["low"], "high": curr["high"]}
        
        # کندل قرمز کوچیک + حرکت نزولی قوی
        if curr["close"] < curr["open"]:
            move = next_k["open"] - next_k["close"]
            if move > body * 2:
                return {"type": "BEARISH_OB", "low": curr["low"], "high": curr["high"]}
    return None

def detect_premium_discount(klines, lookback=50):
    """Premium/Discount"""
    if len(klines) < lookback:
        return None
    highs = [k["high"] for k in klines[-lookback:]]
    lows = [k["low"] for k in klines[-lookback:]]
    high, low = max(highs), min(lows)
    mid = (high + low) / 2
    current = klines[-1]["close"]
    
    if current > mid:
        return "PREMIUM"  # گرون
    else:
        return "DISCOUNT"  # ارزون

# ================== تحلیل ==================
def analyze(symbol, mode="scalp"):
    """تحلیل کامل یه نماد"""
    try:
        if mode == "scalp":
            k_entry = toobit_klines(symbol, "15m", 300)
            k_1h = toobit_klines(symbol, "1h", 200)
            k_4h = toobit_klines(symbol, "4h", 200)
        else:  # swing
            k_entry = toobit_klines(symbol, "1h", 200)
            k_1h = toobit_klines(symbol, "4h", 200)
            k_4h = toobit_klines(symbol, "1d", 200)
        
        if not all([k_entry, k_1h, k_4h]):
            return None
        
        closes = [k["close"] for k in k_entry]
        closes_1h = [k["close"] for k in k_1h]
        closes_4h = [k["close"] for k in k_4h]
        
        # روند 4H
        ema50_4h = ema(closes_4h, 50)
        ema200_4h = ema(closes_4h, 200)
        trend_4h = 0
        if ema50_4h[-1] and ema200_4h[-1]:
            trend_4h = 1 if ema50_4h[-1] > ema200_4h[-1] else -1
        
        # روند 1H
        ema50_1h = ema(closes_1h, 50)
        ema200_1h = ema(closes_1h, 200)
        trend_1h = 0
        if ema50_1h[-1] and ema200_1h[-1]:
            trend_1h = 1 if ema50_1h[-1] > ema200_1h[-1] else -1
        
        if trend_4h == 0 or trend_1h == 0:
            return None
        
        # اندیکاتورها
        rsi_entry = rsi(closes, 14)
        macd_line, signal_line, hist = macd(closes)
        atr_entry = atr(k_entry, 14)
        
        if not rsi_entry[-1] or not macd_line[-1] or not atr_entry[-1]:
            return None
        
        # Smart Money
        bos = detect_bos(k_entry)
        choch = detect_choch(k_entry)
        fvg = detect_fvg(k_entry)
        engulf = detect_engulfing(k_entry)
        sweep = detect_liquidity_sweep(k_entry)
        ob = detect_order_block(k_entry)
        pd = detect_premium_discount(k_entry)
        
        # ===== امتیازدهی =====
        score = 0
        reasons = []
        
        # ۱. هم‌جهتی 4H و 1H (۲۰)
        if trend_4h == trend_1h:
            score += 20
            reasons.append(f"روند {'صعودی' if trend_4h == 1 else 'نزولی'}")
        else:
            return None
        
        direction = trend_4h
        
        # ۲. BOS (۱۵)
        if direction == 1 and bos == "BULLISH_BOS":
            score += 15; reasons.append("BOS صعودی")
        elif direction == -1 and bos == "BEARISH_BOS":
            score += 15; reasons.append("BOS نزولی")
        
        # ۳. Sweep (۱۵)
        if direction == 1 and sweep == "BULLISH_SWEEP":
            score += 15; reasons.append("Sweep صعودی")
        elif direction == -1 and sweep == "BEARISH_SWEEP":
            score += 15; reasons.append("Sweep نزولی")
        
        # ۴. CHoCH (۱۰)
        if direction == 1 and choch == "BULLISH_CHOCH":
            score += 10; reasons.append("CHoCH صعودی")
        elif direction == -1 and choch == "BEARISH_CHOCH":
            score += 10; reasons.append("CHoCH نزولی")
        
        # ۵. Order Block (۱۰)
        if ob:
            if direction == 1 and ob["type"] == "BULLISH_OB":
                score += 10; reasons.append("Order Block صعودی")
            elif direction == -1 and ob["type"] == "BEARISH_OB":
                score += 10; reasons.append("Order Block نزولی")
        
        # ۶. FVG (۱۰)
        if fvg:
            if direction == 1 and fvg["type"] == "BULLISH_FVG":
                score += 10; reasons.append("FVG صعودی")
            elif direction == -1 and fvg["type"] == "BEARISH_FVG":
                score += 10; reasons.append("FVG نزولی")
        
        # ۷. Engulfing (۱۰)
        if direction == 1 and engulf == "BULLISH_ENGULF":
            score += 10; reasons.append("Engulfing صعودی")
        elif direction == -1 and engulf == "BEARISH_ENGULF":
            score += 10; reasons.append("Engulfing نزولی")
        
        # ۸. RSI (۱۰)
        if direction == 1 and 40 < rsi_entry[-1] < 65:
            score += 10; reasons.append(f"RSI: {rsi_entry[-1]:.1f}")
        elif direction == -1 and 35 < rsi_entry[-1] < 60:
            score += 10; reasons.append(f"RSI: {rsi_entry[-1]:.1f}")
        
        # ۹. MACD (۱۰)
        if direction == 1 and macd_line[-1] > signal_line[-1] and hist[-1] > hist[-2]:
            score += 10; reasons.append("MACD صعودی")
        elif direction == -1 and macd_line[-1] < signal_line[-1] and hist[-1] < hist[-2]:
            score += 10; reasons.append("MACD نزولی")
        
        # ۱۰. Premium/Discount (۱۰)
        if direction == 1 and pd == "DISCOUNT":
            score += 10; reasons.append("Discount (ارزون)")
        elif direction == -1 and pd == "PREMIUM":
            score += 10; reasons.append("Premium (گرون)")
        
        # ===== حداقل امتیاز =====
        min_score = SCALP_MIN_SCORE if mode == "scalp" else SWING_MIN_SCORE
        if score < min_score:
            return None
        
        # ===== ورود، SL، TP =====
        entry = k_entry[-1]["close"]
        atr_val = atr_entry[-1]
        
        sl_pct = max(atr_val * 1.5 / entry, 0.008)
        
        if direction == 1:
            sl = entry * (1 - sl_pct)
            tp1 = entry * (1 + sl_pct * 1.5)
            tp2 = entry * (1 + sl_pct * 2.5)
            signal = "🟢 LONG"
        else:
            sl = entry * (1 + sl_pct)
            tp1 = entry * (1 - sl_pct * 1.5)
            tp2 = entry * (1 - sl_pct * 2.5)
            signal = "🔴 SHORT"
        
        return {
            "symbol": symbol,
            "signal": signal,
            "score": score,
            "mode": mode,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "sl_pct": sl_pct * 100,
            "rsi": rsi_entry[-1],
            "reasons": reasons
        }
    except Exception as e:
        print(f"ANALYZE ERROR {symbol}: {e}")
        return None

# ================== ارسال تلگرام ==================
def send_telegram(message):
    """ارسال پیام به تلگرام"""
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
    """فرمت سیگنال"""
    mode_fa = "اسکلپ" if s["mode"] == "scalp" else "سویینگ"
    msg = f"🚨 <b>{s['signal']} - {s['symbol']}</b>\n"
    msg += f"📊 نوع: {mode_fa}\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"امتیاز اطمینان: <b>{s['score']}%</b>\n"
    msg += f"ورود: <code>{s['entry']:.6f}</code>\n"
    msg += f"SL: <code>{s['sl']:.6f}</code> ({s['sl_pct']:.2f}%)\n"
    msg += f"TP1: <code>{s['tp1']:.6f}</code>\n"
    msg += f"TP2: <code>{s['tp2']:.6f}</code>\n"
    msg += f"RSI: {s['rsi']:.1f}\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += "دلایل:\n"
    for r in s["reasons"]:
        msg += f"  ✅ {r}\n"
    now = datetime.now(IRAN_TZ).strftime("%Y-%m-%d %H:%M")
    msg += f"━━━━━━━━━━━━━━━━━━\n⏰ {now}"
    return msg

# ================== حلقه اصلی ==================
def check_signals(mode="scalp"):
    """بررسی سیگنال‌ها"""
    mode_fa = "اسکلپ" if mode == "scalp" else "سویینگ"
    print(f"\n{'='*50}")
    print(f"چک {mode_fa}: {datetime.now(IRAN_TZ).strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")
    
    symbols = get_active_symbols()
    print(f"اسکن {len(symbols)} نماد...")
    
    anti_dup = SCALP_ANTI_DUP if mode == "scalp" else SWING_ANTI_DUP
    signals_found = 0
    
    for symbol in symbols:
        result = analyze(symbol, mode)
        if not result:
            continue
        
        # ضد تکرار
        key = f"{mode}_{symbol}_{result['signal']}"
        last_time = SIGNAL_MEMORY.get(key, 0)
        now = time.time()
        
        if now - last_time < anti_dup:
            continue
        
        # ارسال
        msg = format_signal(result)
        send_telegram(msg)
        SIGNAL_MEMORY[key] = now
        signals_found += 1
        
        print(f"✅ سیگنال: {symbol} | {result['signal']} | {result['score']}%")
        time.sleep(2)
    
    if signals_found == 0:
        print("سیگنالی نبود.")
    return signals_found

# ================== START ==================
if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN تنظیم نشده!")
        exit(1)
    if not CHAT_ID:
        print("ERROR: TELEGRAM_CHAT_ID تنظیم نشده!")
        exit(1)
    
    print("="*50)
    print("AMIN SMART MONEY BOT")
    print("صرافی: توبیت (مستقیم)")
    print("="*50)
    print(f"Token: {TOKEN[:15]}...")
    print(f"Chat ID: {CHAT_ID}")
    print(f"آستانه اسکلپ: {SCALP_MIN_SCORE}%")
    print(f"آستانه سویینگ: {SWING_MIN_SCORE}%")
    print("="*50)
    
    # پیام شروع
    start_msg = "<b>ربات Smart Money فعال شد!</b>\n"
    start_msg += "━━━━━━━━━━━━━━━━━━\n"
    start_msg += "صرافی: توبیت (مستقیم)\n"
    start_msg += "اسکلپ: ۱۵ دقیقه\n"
    start_msg += "سویینگ: ۱ ساعته + ۴ ساعته\n"
    start_msg += f"آستانه: {SCALP_MIN_SCORE}%\n"
    start_msg += "شکارچی: ۳۰ نماد\n"
    start_msg += "━━━━━━━━━━━━━━━━━━"
    send_telegram(start_msg)
    
    # شمارنده
    last_scalp = 0
    last_swing = 0
    
    # حلقه اصلی
    while True:
        try:
            now = time.time()
            
            # اسکلپ: هر ۵ دقیقه
            if now - last_scalp >= SCALP_CHECK_INTERVAL:
                check_signals("scalp")
                last_scalp = now
            
            # سویینگ: هر ۳۰ دقیقه
            if now - last_swing >= SWING_CHECK_INTERVAL:
                check_signals("swing")
                last_swing = now
            
            time.sleep(60)  # هر دقیقه چک کن
            
        except Exception as e:
            print(f"MAIN LOOP ERROR: {e}")
            time.sleep(60)
