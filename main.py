import os
import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": msg
    })

def get_pools():
    url = "https://yields.llama.fi/pools"
    return requests.get(url).json()["data"]

def filter_pools(pools):
    results = []

    for p in pools:
        apy = p.get("apy", 0)
        tvl = p.get("tvlUsd", 0)
        stable = p.get("stablecoin")
        il = p.get("ilRisk")

        # 🔥 FILTRES PRO
        if apy < 20 or apy > 200:
            continue

        if tvl < 2_000_000:
            continue

        if il == "yes" and apy < 50:
            continue

        results.append(p)

    return sorted(results, key=lambda x: x["apy"], reverse=True)[:5]

def format_msg(pools):
    msg = "🚀 TOP DeFi APY\n\n"

    for p in pools:
        msg += f"{p['symbol']} | {p['project']}\n"
        msg += f"APY: {round(p['apy'],2)}%\n"
        msg += f"TVL: ${round(p['tvlUsd']/1e6,2)}M\n\n"

    return msg

pools = get_pools()
best = filter_pools(pools)
send(format_msg(best))
