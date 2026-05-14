#!/usr/bin/env python3
"""
Testa permissões de uma Planet API key contra os principais endpoints.
Uso: python test_planet_api.py [API_KEY]
Se não passar a key, lê do .env do plugin.
"""

import sys
import os
import json
import urllib.request
import urllib.error
import urllib.parse

def load_key_from_env():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_paths = [
        os.path.join(script_dir, 'qgis_satellite_downloader', '.env'),
        os.path.join(script_dir, '.env'),
    ]
    for env_path in env_paths:
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('PLANET_API='):
                        url = line.split('=', 1)[1]
                        parsed = urllib.parse.urlparse(url)
                        params = urllib.parse.parse_qs(parsed.query)
                        key = params.get('api_key', [None])[0]
                        if key:
                            return key
    return None

def test_endpoint(name, url, api_key):
    sep = '=' * 60
    print(f"\n{sep}")
    print(f"  {name}")
    print(f"  URL: {url.split('?')[0]}...")
    print(f"{sep}")
    try:
        req = urllib.request.Request(url)
        if not url.startswith('https://api.planet.com/basemaps'):
            # Data/Orders API uses Basic auth
            import base64
            credentials = base64.b64encode(f'{api_key}:'.encode()).decode()
            req.add_header('Authorization', f'Basic {credentials}')
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            status = resp.status
            body = resp.read().decode('utf-8', errors='replace')
            # Truncate long responses
            if len(body) > 2000:
                body = body[:2000] + '\n... [truncado]'
            print(f"  Status: {status} OK")
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    count_key = data.get('count') or data.get('length') or data.get('total')
                    if count_key is not None:
                        print(f"  Total de itens: {count_key}")
                    if 'mosaics' in data:
                        print(f"  Mosaicos disponíveis: {len(data['mosaics'])}")
                    if 'item_types' in data:
                        print(f"  Tipos de item disponíveis: {len(data['item_types'])}")
                print(f"\n  Resposta:\n{json.dumps(data, indent=2, ensure_ascii=False)[:1500]}")
            except json.JSONDecodeError:
                print(f"  Resposta (texto):\n{body[:1000]}")
        except urllib.error.HTTPError as e:
            status = e.code
            body = e.read().decode('utf-8', errors='replace')
            if len(body) > 500:
                body = body[:500]
            print(f"  Status: {status} {e.reason}")
            print(f"  Resposta: {body}")
    except urllib.error.URLError as e:
        print(f"  Erro de conexão: {e.reason}")
    except Exception as e:
        print(f"  Erro: {e}")

def main():
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
    else:
        api_key = load_key_from_env()

    if not api_key:
        print("Uso: python test_planet_api.py [API_KEY]")
        print("Ou configure PLANET_API no .env")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  TESTE DE PERMISSOES - PLANET API")
    print(f"  Key: {api_key[:8]}...{api_key[-4:]}")
    print(f"{'=' * 60}")

    # 1. Basemaps (WMTS / mosaicos)
    test_endpoint(
        "1. BASEMAPS API - Listar Mosaicos",
        f"https://api.planet.com/basemaps/v1/mosaics?api_key={api_key}&limit=3",
        api_key
    )

    # 2. Data API - Item Types (verifica acesso a cenas)
    test_endpoint(
        "2. DATA API - Item Types (cenas individuais)",
        f"https://api.planet.com/data/v1/item-types/",
        api_key
    )

    # 3. Data API - PSScene search (cenas PlanetScope)
    test_endpoint(
        "3. DATA API - Busca PSScene (cenas PlanetScope 3m)",
        f"https://api.planet.com/data/v1/quick-search?api_key={api_key}",
        api_key
    )
    # POST search
    print(f"\n{'=' * 60}")
    print(f"  3b. DATA API - Quick Search PSScene (POST)")
    print(f"{'=' * 60}")
    search_url = "https://api.planet.com/data/v1/quick-search"
    search_body = json.dumps({
        "item_types": ["PSScene"],
        "filter": {
            "type": "AndFilter",
            "config": [
                {
                    "type": "GeometryFilter",
                    "field_name": "geometry",
                    "config": {
                        "type": "Point",
                        "coordinates": [-48.5, -1.5]
                    }
                },
                {
                    "type": "DateRangeFilter",
                    "field_name": "acquired",
                    "config": {
                        "gte": "2024-01-01T00:00:00Z",
                        "lte": "2024-01-31T00:00:00Z"
                    }
                },
                {
                    "type": "RangeFilter",
                    "field_name": "cloud_cover",
                    "config": {"lte": 0.1}
                }
            ]
        }
    }).encode()
    try:
        req = urllib.request.Request(search_url, data=search_body, method='POST')
        req.add_header('Content-Type', 'application/json')
        import base64
        credentials = base64.b64encode(f'{api_key}:'.encode()).decode()
        req.add_header('Authorization', f'Basic {credentials}')
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        print(f"  Status: {resp.status} OK")
        print(f"  Cenas encontradas: {data.get('total_count', 'N/A')}")
        if data.get('features'):
            for f in data['features'][:3]:
                props = f.get('properties', {})
                print(f"    - {f['id']}: {props.get('acquired','?')} | nuvens: {props.get('cloud_cover','?')}")
    except urllib.error.HTTPError as e:
        print(f"  Status: {e.code} {e.reason}")
        print(f"  Resposta: {e.read().decode('utf-8', errors='replace')[:500]}")
    except Exception as e:
        print(f"  Erro: {e}")

    # 4. Orders API (verifica se pode solicitar downloads)
    test_endpoint(
        "4. ORDERS API - Verificar acesso",
        f"https://api.planet.com/compute/ops/orders/v2/",
        api_key
    )

    # 5. Subscriptions API
    test_endpoint(
        "5. SUBSCRIPTIONS API - Verificar acesso",
        f"https://api.planet.com/subscriptions/v1/",
        api_key
    )

    # Resumo
    print(f"\n\n{'=' * 60}")
    print(f"  RESUMO DAS PERMISSOES")
    print(f"{'=' * 60}")
    print("""
  Endpoint                  | O que permite
  --------------------------|------------------------------------------
  Basemaps (200)           | Mosaicos WMTS (já funciona no plugin)
  Data API (200)           | Buscar cenas individuais com filtro
  PSScene Search (200)     | Cenas PlanetScope 3m (analítico)
  Orders API (200)         | Download de cenas geotiff
  Subscriptions API (200) | Monitoramento contínuo

  Se Data/Orders retornam 401, sua key nao tem acesso a cenas individuais.
  Para isso, e necessario o plano Planet Scope ou similar.
  """)

if __name__ == '__main__':
    main()