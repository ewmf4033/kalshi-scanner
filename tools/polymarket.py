import logging
import httpx

log = logging.getLogger("polymarket")
POLY_CLOB = "https://clob.polymarket.com"

KALSHI_TO_POLY = {}

def get_polymarket_mid(kalshi_ticker):
    token_id = KALSHI_TO_POLY.get(kalshi_ticker)
    if not token_id:
        for prefix, tid in KALSHI_TO_POLY.items():
            if kalshi_ticker.startswith(prefix):
                token_id = tid
                break
    if not token_id:
        return None
    try:
        r = httpx.get(f"{POLY_CLOB}/book", params={"token_id": token_id}, timeout=10)
        r.raise_for_status()
        book = r.json()
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        best_bid = float(bids[0]["price"]) if bids else 0.0
        best_ask = float(asks[0]["price"]) if asks else 1.0
        if best_bid == 0.0 and best_ask == 1.0:
            return None
        return round((best_bid + best_ask) / 2, 4)
    except Exception as e:
        log.warning(f"Poly fetch failed for {kalshi_ticker}: {e}")
        return None

def evaluate_poly_consensus(trade):
    ticker = trade.get("ticker", "")
    implied_prob = trade.get("implied_prob") or trade.get("current_price") or 0.5
    direction = trade.get("direction", "YES")
    prob_range = trade.get("conservative_prob_range") or trade.get("prob_range")
    if prob_range and len(prob_range) == 2:
        model_mid = (prob_range[0] + prob_range[1]) / 2
    else:
        model_mid = implied_prob + (0.05 if direction == "YES" else -0.05)
    poly_price = get_polymarket_mid(ticker)
    if poly_price is None:
        trade["poly_price"] = None
        trade["poly_edge"] = None
        trade["poly_agrees"] = None
        trade["poly_version"] = "v2_no_poly_data"
        return trade
    model_edge = model_mid - implied_prob
    poly_edge = poly_price - implied_prob
    same_direction = (model_edge * poly_edge) > 0
    trade["poly_price"] = poly_price
    trade["poly_edge"] = round(poly_edge, 4)
    trade["poly_agrees"] = same_direction
    trade["poly_version"] = "v3_kalshi_poly_consensus" if same_direction else "v3_poly_disagree"
    log.info(f"POLY {'AGREES' if same_direction else 'DISAGREES'} on {ticker}: model_edge={model_edge:+.3f} poly_edge={poly_edge:+.3f}")
    return trade
