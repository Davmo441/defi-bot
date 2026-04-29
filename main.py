import os
import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

MIN_TVL = 8_000_000
MIN_APY = 20
MAX_APY = 120

SOLID_PROTOCOLS = {
    "uniswap-v3","curve-dex","aave-v3","gmx","compound-v3",
    "balancer-v2","morpho-blue","beefy","convex-finance",
    "pendle","aerodrome-slipstream","camelot-v3",
    "yearn-finance","frax-finance"
}

CHAINS = {
    "Ethereum","Arbitrum","Base","Optimism","Polygon","Avalanche","BNB"
}

# 🟢 RANGE EN %
def recommended_range(p):
    symbol = (p.get("symbol") or "").upper()
    stable = p.get("stablecoin")
    il = p.get("ilRisk")
    apy = p.get("apy", 0)

    if stable:
        base = "±0.5% à ±2%"
    elif "BTC" in symbol:
        base = "±8% à ±15%"
    elif "ETH" in symbol:
        base = "±15% à ±30%"
    else:
        base = "±20% à ±40%"

    if apy > 80:
        base += " (élargir: volatilité élevée)"

    if il == "yes":
        base += " ⚠️ IL élevé → range large conseillé"

    return f"Range: {base}"

# 🧠 SCORE
def get_score(p):
    apy = p.get("apy", 0)
    tvl = p.get("tvlUsd", 0)
    il = p.get("ilRisk")
    project = p.get("project")

    score = 0

    if tvl > 50_000_000: score += 3
    elif tvl > 20_000_000: score += 2
    elif tvl > 10_000_000: score += 1

    if 25 <= apy <= 60: score += 3
    elif 60 < apy <= 100: score += 2

    if il == "yes": score -= 3
    if project in SOLID_PROTOCOLS: score += 2

    return score

def risk_label(p):
    s = get_score(p)
    if s >= 5: return "🟢 SAFE"
    elif s >= 3: return "🟠 MOYEN"
    return "🔴 RISQUÉ"

# 🧠 FAKE YIELD
def fake_yield(p):
    apy = p.get("apy", 0)
    apy_1d = p.get("apyPct1D")

    if apy > 100:
        return "⚠️ APY très élevé (possible inflation)"

    if apy_1d and abs(apy_1d) > 80:
        return "⚠️ APY instable"

    return "🧠 Yield OK"

# 💎 PREMIUM SNIPER
def sniper(p):
    tvl_1d = p.get("tvlUsdPct1D")
    apy_1d = p.get("apyPct1D")

    if tvl_1d and apy_1d:
        if tvl_1d > 20 and apy_1d >= 0:
            return "💎 PREMIUM SNIPER: TVL 24h > +20% ET APY stable ou en hausse"

    return ""

# 🎯 ENTRY
def entry(p):
    tvl_1d = p.get("tvlUsdPct1D")
    apy_1d = p.get("apyPct1D")

    if tvl_1d and tvl_1d > 20:
        return "🎯 Entrée: momentum (liquidity arrive)"

    if apy_1d and apy_1d < -10:
        return "🎯 Attendre (APY baisse)"

    return "🎯 Neutre"

def filter_pools(pools):
    results = []

    for p in pools:
        if p.get("chain") not in CHAINS:
            continue

        if p.get("project") not in SOLID_PROTOCOLS:
            continue

        if p.get("tvlUsd", 0) < MIN_TVL:
            continue

        apy = p.get("apy", 0)
        if apy < MIN_APY or apy > MAX_APY:
            continue

        if risk_label(p) == "🔴 RISQUÉ":
            continue

        results.append(p)

    return sorted(results, key=lambda x: x["apy"], reverse=True)[:8]

def format_msg(pools):
    if not pools:
        return "🛡️ SAFE MODE: aucune pool intéressante"

    msg = "🛡️ SAFE MODE + PRO + ELITE\n\n"

    for p in pools:
        msg += f"{risk_label(p)}\n"
        msg += f"{p['symbol']} | {p['project']}\n"
        msg += f"APY: {round(p.get('apy',0),2)}%\n"
        msg += f"TVL: ${round(p.get('tvlUsd',0)/1e6,2)}M\n"

        if p.get("apyPct1D") is not None:
            msg += f"APY 24h: {round(p['apyPct1D'],2)}%\n"

        if p.get("tvlUsdPct1D") is not None:
            msg += f"TVL 24h: {round(p['tvlUsdPct1D'],2)}%\n"

        msg += recommended_range(p) + "\n"
        msg += fake_yield(p) + "\n"

        snipe = sniper(p)
        if snipe:
            msg += snipe + "\n"

        msg += entry(p) + "\n"
        msg += "────────────\n\n"

    return msg

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

def run():
    pools = requests.get("https://yields.llama.fi/pools").json()["data"]
    best = filter_pools(pools)
    send(format_msg(best))

# 🚀 EXECUTION (CRON)
run()
