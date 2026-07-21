#!/usr/bin/env python3
import json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
ROUTES_PATH = os.path.join(ROOT, "routes.json")
HISTORY_PATH = os.path.join(ROOT, "data", "price_history.json")
DASHBOARD_PATH = os.path.join(ROOT, "dashboard.html")
API_BASE = "https://api.travelpayouts.com"

def api_get(path, params, token):
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}{path}?{query}"
    req = urllib.request.Request(url, headers={"x-access-token": token})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"AVISO: falha ao consultar {path} {params}: {exc}", file=sys.stderr)
        return None

def get_cheapest_roundtrip(origin, destination, currency, token):
    resp = api_get("/v1/prices/cheap", {"origin": origin, "destination": destination, "currency": currency}, token)
    if not resp or not resp.get("success") or not resp.get("data"):
        return None
    dest_node = next(iter(resp["data"].values()), None)
    if not dest_node:
        return None
    offers = list(dest_node.values())
    if not offers:
        return None
    cheapest = min(offers, key=lambda o: float(o["price"]))
    return {"price": float(cheapest["price"]), "airline": cheapest.get("airline"), "departureAt": cheapest.get("departure_at"), "returnAt": cheapest.get("return_at")}

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
        return json.loads(raw) if raw else default

def main():
    token = os.environ.get("TRAVELPAYOUTS_TOKEN")
    if not token:
        print("ERRO: TRAVELPAYOUTS_TOKEN nao definida.", file=sys.stderr); sys.exit(1)
    routes_config = load_json(ROUTES_PATH, None)
    if routes_config is None:
        print(f"ERRO: {ROUTES_PATH} nao encontrado.", file=sys.stderr); sys.exit(1)
    history = load_json(HISTORY_PATH, [])
    search = routes_config["search"]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_entries = []
    overall = get_cheapest_roundtrip(search["originIata"], search["destinationCity"], search["currency"], token)
    if overall:
        new_entries.append({"timestamp": timestamp, "routeId": "overall", "region": "Geral", "airline": overall["airline"], "viaCity": None, "departureAt": overall["departureAt"], "returnAt": overall["returnAt"], "price": overall["price"], "currency": search["currency"], "kind": "real"})
        print(f"overall: {search['currency']} {overall['price']} (cia {overall['airline']})")
    else:
        print("AVISO: overall sem oferta encontrada", file=sys.stderr)
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
