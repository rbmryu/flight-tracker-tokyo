#!/usr/bin/env python3
import json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
ROUTES_PATH = os.path.join(ROOT, "routes.json")
HISTORY_PATH = os.path.join(ROOT, "data", "price_history.json")
DASHBOARD_PATH = os.path.join(ROOT, "dashboard.html")
API_BASE = "https://serpapi.com/search.json"

def api_get(params, key):
    params = dict(params)
    params["api_key"] = key
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"AVISO: falha ao consultar SerpApi {params.get('type')}: {exc}", file=sys.stderr)
        return None

def cheapest_flight(resp):
    if not resp:
        return None
    offers = list(resp.get("best_flights", [])) + list(resp.get("other_flights", []))
    if not offers:
        return None
    cheapest = min(offers, key=lambda o: float(o["price"]))
    flights = cheapest.get("flights", [])
    airline = flights[0]["airline"] if flights else None
    departure_at = flights[0]["departure_airport"]["time"] if flights else None
    return_at = flights[-1]["arrival_airport"]["time"] if flights else None
    return {"price": float(cheapest["price"]), "airline": airline, "departureAt": departure_at, "returnAt": return_at}

def fetch_overall(origin, destination, outbound_date, return_date, currency, key):
    resp = api_get({"engine": "google_flights", "type": 1, "departure_id": origin, "arrival_id": destination, "outbound_date": outbound_date, "return_date": return_date, "currency": currency, "hl": "en"}, key)
    return cheapest_flight(resp)

def fetch_route(origin, via_iata, destination, out_date, connect_date, return_date, currency, key):
    legs = [{"departure_id": origin, "arrival_id": via_iata, "date": out_date}, {"departure_id": via_iata, "arrival_id": destination, "date": connect_date}, {"departure_id": destination, "arrival_id": origin, "date": return_date}]
    resp = api_get({"engine": "google_flights", "type": 3, "multi_city_json": json.dumps(legs), "currency": currency, "hl": "en"}, key)
    return cheapest_flight(resp)

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
        return json.loads(raw) if raw else default

def main():
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        print("ERRO: SERPAPI_KEY nao definida.", file=sys.stderr); sys.exit(1)
    routes_config = load_json(ROUTES_PATH, None)
    if routes_config is None:
        print(f"ERRO: {ROUTES_PATH} nao encontrado.", file=sys.stderr); sys.exit(1)
    history = load_json(HISTORY_PATH, [])
    search = routes_config["search"]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_entries = []
    overall = fetch_overall(search["originIata"], search["destinationIata"], search["outboundDate"], search["returnDate"], search["currency"], key)
    if overall:
        new_entries.append({"timestamp": timestamp, "routeId": "overall", "region": "Geral", "airline": overall["airline"], "viaCity": None, "departureAt": overall["departureAt"], "returnAt": overall["returnAt"], "price": overall["price"], "currency": search["currency"], "kind": "real"})
        print(f"overall: {search['currency']} {overall['price']} (cia {overall['airline']})")
    else:
        print("AVISO: overall sem oferta encontrada", file=sys.stderr)
    for route in routes_config["routes"]:
        result = fetch_route(search["originIata"], route["viaIata"], search["destinationIata"], search["outboundDate"], search["connectDate"], search["returnDate"], search["currency"], key)
        if result:
            new_entries.append({"timestamp": timestamp, "routeId": route["id"], "region": route["region"], "airline": result["airline"], "viaCity": route["viaCity"], "departureAt": result["departureAt"], "returnAt": result["returnAt"], "price": result["price"], "currency": search["currency"], "kind": "real"})
            print(f"{route['id']}: {search['currency']} {result['price']} (cia {result['airline']}, via {route['viaCity']})")
        else:
            print(f"AVISO: {route['id']} sem oferta encontrada", file=sys.stderr)
    history.extend(new_entries)
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    if os.path.exists(DASHBOARD_PATH):
        with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
            html = f.read()
        def replace_block(html_text, block_id, payload):
            pattern = re.compile(r'(<script type="application/json" id="' + re.escape(block_id) + r'">\n)(.*?)(\n</script>)', re.DOTALL)
            replacement = json.dumps(payload, ensure_ascii=False, indent=2)
            new_html, count = pattern.subn(lambda m: m.group(1) + replacement + m.group(3), html_text)
            if count != 1:
                print(f"AVISO: bloco {block_id} nao atualizado ({count} ocorrencias)", file=sys.stderr)
            return new_html
        html = replace_block(html, "routes-config", routes_config)
        html = replace_block(html, "price-data", history)
        with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
            f.write(html)
        print("dashboard.html atualizado.")
    else:
        print(f"AVISO: {DASHBOARD_PATH} nao encontrado.", file=sys.stderr)
    print(f"\n{len(new_entries)} ponto(s) adicionado(s). Historico total: {len(history)} pontos.")

if __name__ == "__main__":
    main()
