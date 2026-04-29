import os
import requests
import time

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

MIN_TVL = 8_000_000
MIN_APY = 20
MAX_APY = 200

SOLID_PROTOCOLS = {
    "uniswap-v3",
    "uniswap-v2",
    "curve-dex",
    "aave-v3",
    "aave-v2",
    "gmx",
    "compound-v3",
    "compound-v2",
    "balancer-v2",
    "morpho-blue",
    "beefy",
    "convex-finance",
    "pendle",
    "aerodrome-slipstream",
    "aerodrome-v1",
    "camelot-v3",
    "frax-finance",
    "yearn-finance",
    "stargate",
    "silo",
    "radiant-v2",
}

CHAINS = {
    "Ethereum",
    "Arbitrum",
    "Base",
    "Optimism",
    "Polygon",
    "Avalanche",
    "BNB",
}

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": msg,
        "disable_web_page_preview": True
    })

def get_pools():
    url = "https://yields.llama.fi/pools"
    return requests.get(url, timeout=30).json()["data"]

def get_risk_score(p):
    apy = p.get("apy") or 0
    tvl = p.get("tvlUsd") or 0
    il = p.get("ilRisk")
    project = p.get("project")
    stable = p.get("stablecoin")
    apy_1d = p.get("apyPct1D")
    tvl_1d = p.get("tvlUsdPct1D")

    risk = 0

    if tvl < 5_000_000:
        risk += 3
    elif tvl < 10_000_000:
        risk += 2
    elif tvl < 50_000_000:
        risk += 1

    if apy > 100:
        risk += 3
    elif apy > 60:
        risk += 2
    elif apy > 35:
        risk += 1

    if il == "yes":
        risk += 3

    if project not in SOLID_PROTOCOLS:
        risk += 2

    if stable:
        risk -= 1

    if apy_1d is not None and abs(apy_1d) > 50:
        risk += 2

    if tvl_1d is not None and tvl_1d < -20:
        risk += 3

    if risk <= 2:
        return "🟢 SAFE"
    elif risk <= 5:
        return "🟠 MOYEN"
    else:
        return "🔴 RISQUÉ"

def filter_pools(pools):
    results = []

    for p in pools:
        apy = p.get("apy") or 0
        tvl = p.get("tvlUsd") or 0
        project = p.get("project")
        chain = p.get("chain")

        if chain not in CHAINS:
            continue

        if project not in SOLID_PROTOCOLS:
            continue

        if tvl < MIN_TVL:
            continue

        if apy < MIN_APY or apy > MAX_APY:
            continue

        score = get_risk_score(p)

        if score == "🔴 RISQUÉ":
            continue

        results.append(p)

    return sorted(results, key=lambda x: x.get("apy") or 0, reverse=True)[:8]

def format_msg(pools):
    if not pools:
        return "Aucune pool intéressante selon les filtres actuels."

    msg = "🚀 TOP DeFi APY — Smart Filter\n\n"

    for p in pools:
        score = get_risk_score(p)

        symbol = p.get("symbol")
        project = p.get("project")
        chain = p.get("chain")
        apy = round(p.get("apy") or 0, 2)
        tvl = round((p.get("tvlUsd") or 0) / 1_000_000, 2)
        il = p.get("ilRisk")
        stable = p.get("stablecoin")
        apy_1d = p.get("apyPct1D")
        tvl_1d = p.get("tvlUsdPct1D")
        pool_id = p.get("pool")

        msg += f"{score}\n"
        msg += f"{symbol} | {project}\n"
        msg += f"Chain: {chain}\n"
        msg += f"APY: {apy}%\n"
        msg += f"TVL: ${tvl}M\n"
        msg += f"Stablecoin: {stable}\n"
        msg += f"IL risk: {il}\n"

        if apy_1d is not None:
            msg += f"APY 24h: {round(apy_1d, 2)}%\n"

        if tvl_1d is not None:
            msg += f"TVL 24h: {round(tvl_1d, 2)}%\n"
            if tvl_1d < -20:
                msg += "⚠️ ALERTE: chute TVL importante\n"

        msg += f"Lien: https://defillama.com/yields/pool/{pool_id}\n\n"

    msg += "⚠️ Pas un conseil financier. Vérifie toujours."
    return msg

def run():
    pools = get_pools()
    best = filter_pools(pools)
    send(format_msg(best))

while True:
    try:
        run()
    except Exception as e:
        send(f"Erreur bot: {e}")

    time.sleep(3600)
