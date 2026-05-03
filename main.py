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

CAPITAL_TOTAL = 10_000

STABLES = {"USDC", "USDT", "DAI", "FRAX", "LUSD", "USDE", "SUSDE", "USDS", "GHO", "PYUSD"}
ETH_ASSETS = {"ETH", "WETH", "STETH", "WSTETH", "RETH", "CBETH"}
BTC_ASSETS = {"BTC", "WBTC", "CBBTC", "TBTC"}

SOLID_PROTOCOLS = {
    "uniswap-v3", "curve-dex", "aave-v3", "gmx", "compound-v3",
    "balancer-v2", "morpho-blue", "beefy", "convex-finance",
    "pendle", "aerodrome-slipstream", "camelot-v3",
    "yearn-finance", "frax-finance"
}

CHAINS = {
    "Ethereum", "Arbitrum", "Base", "Optimism", "Polygon", "Avalanche", "BNB"
}

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

def get_tokens(p):
    symbol = (p.get("symbol") or "").upper()
    clean = symbol.replace("/", "-").replace("_", "-")
    return [x.strip() for x in clean.split("-") if x.strip()]

def token_category(token):
    token = token.upper()
    if token in STABLES:
        return "stable"
    if token in ETH_ASSETS:
        return "eth"
    if token in BTC_ASSETS:
        return "btc"
    return "alt"

def pair_name(p):
    tokens = get_tokens(p)
    if len(tokens) < 2:
        return "Inconnu"

    cats = [token_category(t) for t in tokens[:2]]

    if cats[0] == "stable" and cats[1] == "stable":
        return "Stable / Stable"
    if set(cats) == {"eth", "btc"}:
        return "ETH / BTC"
    if "eth" in cats and "stable" in cats:
        return "ETH / Stable"
    if "btc" in cats and "stable" in cats:
        return "BTC / Stable"
    if "stable" in cats and "alt" in cats:
        return "Altcoin / Stable"
    if cats[0] == "alt" and cats[1] == "alt":
        return "Altcoin / Altcoin"

    return "Mixte / Autre"

def pair_type(p):
    return f"Type paire: {pair_name(p)}"

def il_estimator(p):
    pair = pair_name(p)

    if pair == "Stable / Stable":
        return "🟢 IL FAIBLE (<1%)", "faible", 0.00

    if pair == "ETH / BTC":
        return "🟡 IL FAIBLE À MODÉRÉ (0.5–3%)", "modere", 0.10

    if pair == "ETH / Stable":
        return "⚠️ IL MODÉRÉ (1–5%)", "modere", 0.15

    if pair == "BTC / Stable":
        return "⚠️ IL MODÉRÉ (1–5%)", "modere", 0.15

    if pair == "Altcoin / Stable":
        return "⚠️ IL ÉLEVÉ (5–15%)", "eleve", 0.50

    if pair == "Altcoin / Altcoin":
        return "⚠️ IL POTENTIEL TRÈS ÉLEVÉ (>20%)", "tres_eleve", 1.00

    return "⚠️ IL INCONNU — à vérifier manuellement", "inconnu", 0.30

def real_il_risk(p):
    text, _, _ = il_estimator(p)
    return f"Risque IL estimé: {text}"

def is_pair_too_dangerous(p):
    pair = pair_name(p)
    apy = p.get("apy") or 0
    tvl = p.get("tvlUsd") or 0
    _, danger, _ = il_estimator(p)

    if pair == "Altcoin / Altcoin":
        return True

    if danger == "tres_eleve":
        return True

    if pair == "Altcoin / Stable" and tvl < 20_000_000:
        return True

    if pair == "Altcoin / Stable" and apy > 80:
        return True

    return False

def recommended_range(p):
    pair = pair_name(p)
    apy = p.get("apy") or 0
    il = p.get("ilRisk")

    if pair == "Stable / Stable":
        base = "±0.5% à ±2%"
    elif pair == "ETH / BTC":
        base = "±8% à ±15%"
    elif pair == "ETH / Stable":
        base = "±15% à ±30%"
    elif pair == "BTC / Stable":
        base = "±12% à ±25%"
    elif pair == "Altcoin / Stable":
        base = "±30% à ±60%"
    elif pair == "Altcoin / Altcoin":
        base = "±50% à ±100% — déconseillé"
    else:
        base = "±20% à ±40%"

    if apy > 80:
        base += " (élargir: volatilité élevée)"
    if il == "yes":
        base += " ⚠️ IL élevé → range large conseillé"

    return f"Range ajustée: {base}"

def get_score(p):
    apy = p.get("apyMean30d") or p.get("apy") or 0
    tvl = p.get("tvlUsd") or 0
    il = p.get("ilRisk")
    project = p.get("project")
    pair = pair_name(p)
    _, danger, _ = il_estimator(p)

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
        score -= 2
    if project in SOLID_PROTOCOLS:
        score += 2

    if pair == "Stable / Stable":
        score += 2
    elif pair == "ETH / BTC":
        score += 1
    elif pair in ["ETH / Stable", "BTC / Stable"]:
        score -= 1
    elif pair == "Altcoin / Stable":
        score -= 3
    elif pair == "Altcoin / Altcoin":
        score -= 5

    if danger == "eleve":
        score -= 2
    elif danger == "tres_eleve":
        score -= 5

    return score

def risk_label(p):
    s = get_score(p)
    if s >= 5:
        return "🟢 SAFE"
    elif s >= 3:
        return "🟠 MOYEN"
    return "🔴 RISQUÉ"

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

def momentum(p):
    tvl_1d = p.get("tvlUsdPct1D")
    apy_1d = p.get("apyPct1D")

    if tvl_1d is not None and apy_1d is not None:
        if tvl_1d > 10 and apy_1d > 0:
            return "📈 Momentum positif"
        if tvl_1d < -10:
            return "📉 Momentum négatif"

    return ""

def sniper(p):
    tvl_1d = p.get("tvlUsdPct1D")
    apy = p.get("apy") or 0
    apy_30d = p.get("apyMean30d") or apy

    if tvl_1d is not None and tvl_1d > 20 and apy > apy_30d:
        return "💎 SNIPER: flux entrant + rendement supérieur"

    return ""

def sweet_spot(p):
    apy = p.get("apy") or 0
    apy_30d = p.get("apyMean30d") or apy
    apy_1d = p.get("apyPct1D")

    if apy_1d is not None and 0 < apy_1d < 15 and apy >= apy_30d:
        return "🟢 SWEET SPOT DETECTED"

    return ""

def decision(p):
    apy = p.get("apy") or 0
    apy_30d = p.get("apyMean30d") or apy
    apy_1d = p.get("apyPct1D")
    tvl_1d = p.get("tvlUsdPct1D")
    score = get_score(p)
    _, danger, _ = il_estimator(p)

    if danger == "tres_eleve":
        return "🔴 ÉVITER (IL trop élevé)"

    if tvl_1d is not None and tvl_1d <= -15:
        return "🔴 SORTIE URGENTE (TVL chute forte)"

    if apy < apy_30d * 0.60:
        return "🔴 SORTIE URGENTE (APY effondré)"

    if tvl_1d is not None and tvl_1d < -10:
        return "🔴 SORTIE À SURVEILLER (TVL baisse)"

    if apy < apy_30d * 0.70:
        return "🔴 SORTIE À ENVISAGER"

    if apy_1d is not None and -15 <= apy_1d < -5:
        return "🟠 DÉGRADATION (APY baisse)"

    if tvl_1d is not None and -10 <= tvl_1d < -3:
        return "🟠 DÉGRADATION (TVL baisse légère)"

    if apy_1d is not None and apy_1d > 25:
        return "🟠 ATTENDRE (surchauffe)"

    if sweet_spot(p):
        return "🟢 ENTRÉE POSSIBLE — SWEET SPOT"

    if sniper(p) and score >= 3:
        return "🟢 ENTRÉE POSSIBLE — SNIPER"

    if apy >= apy_30d and apy_1d is not None and 0 <= apy_1d < 15 and score >= 3:
        return "🟢 ENTRÉE POSSIBLE"

    if apy >= apy_30d * 0.90 and score >= 3:
        return "🟡 SURVEILLER — encore correct"

    return "🎯 NEUTRE"

def capital_allocation(p):
    score = get_score(p)
    d = decision(p)
    pair = pair_name(p)
    _, danger, reduction = il_estimator(p)

    if "SORTIE" in d or "ÉVITER" in d:
        return "💰 Allocation: 0€ — sortie / pas d'entrée"

    if pair == "Altcoin / Stable":
        base_pct = 0.03
    elif sniper(p):
        base_pct = 0.08
    elif sweet_spot(p):
        base_pct = 0.15 if score >= 5 else 0.08
    elif "ENTRÉE POSSIBLE" in d:
        base_pct = 0.12 if score >= 5 else 0.06
    else:
        base_pct = 0.00

    adjusted_pct = base_pct * (1 - reduction)
    amount = CAPITAL_TOTAL * adjusted_pct

    if adjusted_pct == 0:
        return "💰 Allocation: 0€ — signal insuffisant"

    return f"💰 Allocation ajustée IL: ~{round(amount, 2)}€ max ({round(adjusted_pct*100, 1)}% du capital)"

def priority_score(p):
    d = decision(p)

    if "SORTIE URGENTE" in d:
        return 20_000
    if "SORTIE" in d:
        return 10_000
    if "ÉVITER" in d:
        return -10_000

    score = get_score(p)

    if sweet_spot(p):
        score += 500
    if sniper(p):
        score += 400
    if "ENTRÉE POSSIBLE" in d:
        score += 300
    if momentum(p) == "📈 Momentum positif":
        score += 100
    if "DÉGRADATION" in d:
        score += 50

    return score

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
        if is_pair_too_dangerous(p):
            continue
        if risk_label(p) == "🔴 RISQUÉ":
            continue
        if decision(p) == "🎯 NEUTRE":
            continue

        results.append(p)

    return sorted(results, key=priority_score, reverse=True)[:5]

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

    if abs(apy - last_apy) >= 3:
        return True
    if abs(tvl - last_tvl) >= 3_000_000:
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
    d = decision(p)

    msg = ""

    if "SORTIE URGENTE" in d:
        msg += "🚨🚨🚨 EXIT URGENT — SORTIE IMMÉDIATE À ANALYSER 🚨🚨🚨\n"
    elif "SORTIE" in d:
        msg += "🚨🚨 EXIT — ALERTE SORTIE 🚨🚨\n"

    if sweet_spot(p) or sniper(p):
        msg += "🔥 PRIORITÉ ENTRÉE — SIGNAL FORT 🔥\n"

    if "DÉGRADATION" in d:
        msg += "🟠 WARNING — POSITION À SURVEILLER 🟠\n"

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

    msg += pair_type(p) + "\n"
    msg += real_il_risk(p) + "\n"
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
    msg += d + "\n"
    msg += capital_allocation(p) + "\n"
    msg += recommended_range(p) + "\n"
    msg += "────────────\n\n"

    return msg

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
