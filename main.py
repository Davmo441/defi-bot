import os
import requests
import psycopg2
from datetime import datetime

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")

MIN_TVL = 8_000_000
MIN_APY = 20
MAX_APY = 120

CAPITAL_TOTAL = 10_000  # adapte ici ton capital total en €

SOLID_PROTOCOLS = {
    "uniswap-v3", "curve-dex", "aave-v3", "gmx", "compound-v3",
    "balancer-v2", "morpho-blue", "beefy", "convex-finance",
    "pendle", "aerodrome-slipstream", "camelot-v3",
    "yearn-finance", "frax-finance"
}

CHAINS = {
    "Ethereum", "Arbitrum", "Base", "Optimism", "Polygon", "Avalanche", "BNB"
}

# 🔌 DATABASE
def connect_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            pool_id TEXT PRIMARY KEY,
            last_apy FLOAT,
            last_tvl FLOAT,
            last_decision TEXT,
            updated_at TIMESTAMP
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

# 🟢 RANGE
def recommended_range(p):
    symbol = (p.get("symbol") or "").upper()
    stable = p.get("stablecoin")
    il = p.get("ilRisk")
    apy = p.get("apy") or 0

    if stable:
        base = "±0.5% à ±2%"
    elif "BTC" in symbol:
        base = "±8% à ±15%"
    elif "ETH" in symbol:
        base = "±15% à ±30%"
    else:
        base = "±20% à ±40%"

    if apy > 80:
        base += " (volatilité élevée)"

    if il == "yes":
        base += " ⚠️ IL élevé → range large conseillé"

    return f"Range: {base}"

# 🧠 SCORE
def get_score(p):
    apy = p.get("apyMean30d") or p.get("apy") or 0
    tvl = p.get("tvlUsd") or 0
    il = p.get("ilRisk")
    project = p.get("project")

    score = 0

    if tvl > 50_000_000:
        score += 3
    elif tvl > 20_000_000:
        score += 2
    elif tvl > 10_000_000:
        score += 1

    if 25 <= apy <= 60:
        score += 3
    elif 60 < apy <= 100:
        score += 2

    if il == "yes":
        score -= 3

    if project in SOLID_PROTOCOLS:
        score += 2

    return score

def risk_label(p):
    s = get_score(p)
    if s >= 5:
        return "🟢 SAFE"
    elif s >= 3:
        return "🟠 MOYEN"
    return "🔴 RISQUÉ"

# 💰 CAPITAL ALLOCATION
def capital_allocation(p):
    score = get_score(p)
    d = decision(p)

    if d == "🔴 SORTIE À ENVISAGER" or d == "🔴 SORTIE À SURVEILLER (TVL baisse)":
        return "💰 Allocation: 0€ — sortie / pas d'entrée"

    if "SNIPER" in sniper(p):
        amount = CAPITAL_TOTAL * 0.10
        return f"💰 Allocation sniper: ~{round(amount, 2)}€ max (10% du capital)"

    if sweet_spot(p):
        if score >= 5:
            amount = CAPITAL_TOTAL * 0.15
            return f"💰 Allocation sweet spot: ~{round(amount, 2)}€ max (15% du capital)"
        else:
            amount = CAPITAL_TOTAL * 0.08
            return f"💰 Allocation prudente: ~{round(amount, 2)}€ max (8% du capital)"

    if d == "🟢 ENTRÉE POSSIBLE":
        if score >= 5:
            amount = CAPITAL_TOTAL * 0.12
            return f"💰 Allocation entrée: ~{round(amount, 2)}€ max (12% du capital)"
        elif score >= 3:
            amount = CAPITAL_TOTAL * 0.06
            return f"💰 Allocation entrée prudente: ~{round(amount, 2)}€ max (6% du capital)"

    return "💰 Allocation: 0€ — signal insuffisant"

# 🧠 FAKE YIELD
def fake_yield(p):
    apy = p.get("apy") or 0
    apy_1d = p.get("apyPct1D")

    if apy > 100:
        return "⚠️ APY très élevé (possible inflation)"

    if apy_1d is not None and abs(apy_1d) > 80:
        return "⚠️ APY très instable"

    if apy_1d is not None and apy_1d > 25:
        return "⚠️ APY instable (hausse rapide)"

    return "🧠 Yield OK"

# 📈 MOMENTUM
def momentum(p):
    tvl_1d = p.get("tvlUsdPct1D")
    apy_1d = p.get("apyPct1D")

    if tvl_1d is not None and apy_1d is not None:
        if tvl_1d > 10 and apy_1d > 0:
            return "📈 Momentum positif"
        if tvl_1d < -10:
            return "📉 Momentum négatif"

    return ""

# 💎 SNIPER
def sniper(p):
    tvl_1d = p.get("tvlUsdPct1D")
    apy = p.get("apy") or 0
    apy_30d = p.get("apyMean30d") or apy

    if tvl_1d is not None and tvl_1d > 20 and apy > apy_30d:
        return "💎 SNIPER: flux entrant + rendement supérieur"

    return ""

# 🟢 SWEET SPOT
def sweet_spot(p):
    apy = p.get("apy") or 0
    apy_30d = p.get("apyMean30d") or apy
    apy_1d = p.get("apyPct1D")

    if apy_1d is not None and 0 < apy_1d < 15 and apy >= apy_30d:
        return "🟢 SWEET SPOT DETECTED"

    return ""

# 🎯 DECISION
def decision(p):
    apy = p.get("apy") or 0
    apy_30d = p.get("apyMean30d") or apy
    apy_1d = p.get("apyPct1D")
    tvl_1d = p.get("tvlUsdPct1D")

    if apy >= apy_30d and apy_1d is not None and 0 <= apy_1d < 15:
        return "🟢 ENTRÉE POSSIBLE"

    if apy_1d is not None and apy_1d > 25:
        return "🟠 ATTENDRE (surchauffe)"

    if apy < apy_30d * 0.7:
        return "🔴 SORTIE À ENVISAGER"

    if tvl_1d is not None and tvl_1d < -10:
        return "🔴 SORTIE À SURVEILLER (TVL baisse)"

    return "🎯 NEUTRE"

# 🔍 FILTER
def filter_pools(pools):
    results = []

    for p in pools:
        if p.get("chain") not in CHAINS:
            continue

        if p.get("project") not in SOLID_PROTOCOLS:
            continue

        if (p.get("tvlUsd") or 0) < MIN_TVL:
            continue

        apy_current = p.get("apy") or 0
        apy_30d = p.get("apyMean30d") or apy_current

        if apy_current < MIN_APY:
            continue

        if apy_30d < MIN_APY or apy_30d > MAX_APY:
            continue

        if risk_label(p) == "🔴 RISQUÉ":
            continue

        # ✅ Ignore les pools neutres
        if decision(p) == "🎯 NEUTRE":
            continue

        results.append(p)

    return sorted(
        results,
        key=lambda x: x.get("apyMean30d") or x.get("apy") or 0,
        reverse=True
    )[:8]

# 🧠 POSTGRES ANTI-DOUBLON
def get_old_signal(pool_id):
    conn = connect_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT last_apy, last_tvl, last_decision FROM alerts WHERE pool_id = %s",
        (pool_id,)
    )

    row = cur.fetchone()

    cur.close()
    conn.close()

    return row

def is_new_signal(pool_id, apy, tvl, current_decision):
    old = get_old_signal(pool_id)

    if old is None:
        return True

    last_apy, last_tvl, last_decision = old

    if abs(apy - last_apy) >= 5:
        return True

    if abs(tvl - last_tvl) >= 5_000_000:
        return True

    if current_decision != last_decision:
        return True

    return False

def save_signal(pool_id, apy, tvl, current_decision):
    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO alerts (pool_id, last_apy, last_tvl, last_decision, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (pool_id)
        DO UPDATE SET
            last_apy = EXCLUDED.last_apy,
            last_tvl = EXCLUDED.last_tvl,
            last_decision = EXCLUDED.last_decision,
            updated_at = EXCLUDED.updated_at
    """, (pool_id, apy, tvl, current_decision, datetime.utcnow()))

    conn.commit()
    cur.close()
    conn.close()

# 📝 MESSAGE
def format_pool(p):
    pool_id = p.get("pool")
    symbol = p.get("symbol")
    project = p.get("project")
    chain = p.get("chain")

    apy = p.get("apy") or 0
    apy_30d = p.get("apyMean30d") or apy
    tvl = p.get("tvlUsd") or 0
    apy_1d = p.get("apyPct1D")
    tvl_1d = p.get("tvlUsdPct1D")

    msg = ""
    msg += f"{risk_label(p)}\n"
    msg += f"{symbol} | {project}\n"
    msg += f"Chain: {chain}\n"
    msg += f"APY actuel: {round(apy, 2)}%\n"
    msg += f"APY 30j: {round(apy_30d, 2)}%\n"
    msg += f"TVL: ${round(tvl / 1e6, 2)}M\n"

    if apy_1d is not None:
        msg += f"APY 24h: {round(apy_1d, 2)}%\n"

    if tvl_1d is not None:
        msg += f"TVL 24h: {round(tvl_1d, 2)}%\n"

    msg += f"🔗 https://defillama.com/yields/pool/{pool_id}\n"

    token = (symbol or "").split("-")[0]
    if token:
        msg += f"📊 Chart: https://dexscreener.com/search?q={token}\n"

    s = sweet_spot(p)
    if s:
        msg += s + "\n"

    m = momentum(p)
    if m:
        msg += m + "\n"

    sn = sniper(p)
    if sn:
        msg += sn + "\n"

    msg += fake_yield(p) + "\n"
    msg += decision(p) + "\n"
    msg += capital_allocation(p) + "\n"
    msg += recommended_range(p) + "\n"
    msg += "────────────\n\n"

    return msg

# 📤 TELEGRAM
def send(msg):
    if not msg:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    for i in range(0, len(msg), 3500):
        chunk = msg[i:i + 3500]
        requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": chunk,
                "disable_web_page_preview": True
            },
            timeout=20
        )

# 🚀 RUN
def run():
    init_db()

    response = requests.get("https://yields.llama.fi/pools", timeout=30)
    response.raise_for_status()

    pools = response.json()["data"]
    best = filter_pools(pools)

    msg = "🚨 ALERTES DEFI — POSTGRES PRO\n\n"
    alerts_sent = 0

    for p in best:
        pool_id = p.get("pool")
        if not pool_id:
            continue

        apy = p.get("apy") or 0
        tvl = p.get("tvlUsd") or 0
        current_decision = decision(p)

        if is_new_signal(pool_id, apy, tvl, current_decision):
            msg += format_pool(p)
            save_signal(pool_id, apy, tvl, current_decision)
            alerts_sent += 1

    if alerts_sent > 0:
        send(msg)
        print(f"{alerts_sent} alerte(s) envoyée(s).")
    else:
        print("Aucune nouvelle alerte.")

run()
