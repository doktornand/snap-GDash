# GDash — Mémo Technique d'Architecture
> **Globe Dashboard Backend FastAPI**  
> Version analysée : `2.0.0` · Python 3.8.10 · Mai 2026

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Stack technique](#2-stack-technique)
3. [Architecture applicative](#3-architecture-applicative)
4. [Catalogue des sources de données](#4-catalogue-des-sources-de-données)
5. [Carte des endpoints](#5-carte-des-endpoints)
6. [Flux de données et concurrence](#6-flux-de-données-et-concurrence)
7. [Configuration et secrets](#7-configuration-et-secrets)
8. [Containerisation et déploiement](#8-containerisation-et-déploiement)
9. [Analyse des risques](#9-analyse-des-risques)
10. [Suggestions d'amélioration](#10-suggestions-damélioration)

---

## 1. Vue d'ensemble

GDash est un **agrégateur de données mondiales en temps réel**, implémenté comme une API REST asynchrone. Il collecte simultanément des données provenant de **17 sources publiques gratuites** couvrant des domaines aussi variés que la météorologie, le trafic aérien, la sismologie, l'activité spatiale, les marchés financiers ou encore la cybersécurité.

### Philosophie du projet

- **Zéro dépendance payante** : toutes les sources sont publiques, gratuites, sans clé API obligatoire (sauf ACLED pour les conflits armés).
- **Asynchronisme radical** : chaque requête agrège jusqu'à 16 sources en parallèle via `asyncio.gather()`, minimisant la latence totale.
- **API granulaire** : chaque domaine de données est accessible individuellement *ou* via un endpoint `/summary` unifié.
- **Portabilité maximale** : compatible Python 3.8+, containerisé, déployable sur n'importe quelle plateforme cloud.

---

## 2. Stack technique

| Composant | Technologie | Version | Rôle |
|---|---|---|---|
| **Runtime** | Python | 3.8.10 | Compatibilité LTS étendue |
| **Framework web** | FastAPI | ≥ 0.100 | Routage, validation, doc auto |
| **Serveur ASGI** | Uvicorn | ≥ 0.22 | Serveur HTTP async (workers) |
| **Client HTTP** | httpx | ≥ 0.24 | Requêtes HTTP async (API JSON) |
| **Parser RSS** | feedparser | ≥ 6.0.8 | Parsing flux RSS/Atom |
| **Concurrence** | asyncio | stdlib | Parallélisation des fetchers |
| **Sérialisation** | json | stdlib | Config & réponses |
| **Typage** | typing | stdlib | Annotations (compatibilité 3.8) |

### Pourquoi FastAPI ?

FastAPI repose sur **Starlette** (ASGI) et **Pydantic** (validation). Pour un agrégateur I/O-bound comme GDash, le modèle async natif est idéal : pendant qu'une requête attend la réponse d'OpenSky, le serveur traite d'autres connexions sans bloquer de thread.

La **documentation interactive automatique** (Swagger UI sur `/docs`, ReDoc sur `/redoc`) est un bonus précieux pour explorer les 17 endpoints sans outil externe.

---

## 3. Architecture applicative

```
┌─────────────────────────────────────────────────────────┐
│                    CLIENT (browser / app)                │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP GET
┌─────────────────────▼───────────────────────────────────┐
│              UVICORN (ASGI server)                       │
│              host: 0.0.0.0 · port: 8000 · workers: 2    │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                 FASTAPI APPLICATION                       │
│  ┌──────────────┐  ┌─────────────────────────────────┐  │
│  │ CORS         │  │ ROUTER                          │  │
│  │ Middleware   │  │ / · /summary · /weather · ...   │  │
│  │ allow: *     │  └───────────────┬─────────────────┘  │
│  └──────────────┘                  │                     │
└───────────────────────────────────┼─────────────────────┘
                                    │ asyncio.gather()
          ┌─────────────────────────▼──────────────────────────────┐
          │              FETCHERS LAYER (16 fonctions async)        │
          │                                                          │
          │  fetch_weather()         fetch_weather_extremes()        │
          │  fetch_weather_alerts()  fetch_flights()                 │
          │  fetch_maritime()        fetch_conflicts()               │
          │  fetch_seismic()         fetch_space_data()              │
          │  fetch_crypto_prices()   fetch_stock_market()            │
          │  fetch_cybersecurity()   fetch_pandemic_data()           │
          │  fetch_aurora_forecast() fetch_volcanic_activity()       │
          │  fetch_wildfires()       fetch_ocean_data()              │
          └─────────────────────────┬──────────────────────────────┘
                                    │
          ┌─────────────────────────▼──────────────────────────────┐
          │              TRANSPORT LAYER                             │
          │   httpx.AsyncClient (JSON APIs)                         │
          │   feedparser.parse() (flux RSS/Atom)                    │
          └─────────────────────────┬──────────────────────────────┘
                                    │
          ┌─────────────────────────▼──────────────────────────────┐
          │              SOURCES EXTERNES (Internet)                 │
          │   17 APIs publiques gratuites (voir §4)                 │
          └─────────────────────────────────────────────────────────┘
```

### Pattern de résilience : `safe_fetch()`

Tous les appels HTTP passent par un wrapper centralisé :

```python
async def safe_fetch(client, url, **kwargs) -> Optional[dict]:
    try:
        r = await client.get(url, timeout=10, **kwargs)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}
```

Ce pattern garantit qu'**une source défaillante ne fait pas planter l'ensemble de la réponse** : l'erreur est encapsulée dans le champ `error` de la source concernée, et toutes les autres données sont retournées normalement.

### Gestion du client HTTP

`httpx.AsyncClient` est instancié **à chaque requête endpoint** dans un bloc `async with`, ce qui assure la fermeture propre des connexions et la libération des ressources. C'est un choix correct mais qui a un coût (voir §10 pour l'optimisation).

---

## 4. Catalogue des sources de données

### 4.1 Météorologie

| Source | Protocole | Données | Clé requise |
|---|---|---|---|
| **Open-Meteo** | JSON REST | Météo locale (temp, vent, pluie, pression), forecast 7j, extrêmes mondiaux | ❌ Non |
| **NOAA CAP** | RSS/Atom | Alertes météo USA en temps réel | ❌ Non |
| **Open-Meteo Marine** | JSON REST | Température surface de la mer | ❌ Non |

**Points remarquables :**
- Open-Meteo est une API **sans limite de taux déclarée** pour un usage raisonnable, hébergée en Europe (RGPD-friendly).
- 4 points géographiques extrêmes sont interrogés en parallèle (Death Valley, Oymyakon, Dallol, Vostok) pour constituer un tableau de températures mondiales.
- Le helper `wmo_code_to_text()` traduit les codes météo WMO en français lisible.

---

### 4.2 Trafic aérien

| Source | Protocole | Données | Clé requise |
|---|---|---|---|
| **OpenSky Network** | JSON REST | États de tous les avions en vol (monde entier) | ❌ Non (limité) / ✅ Optionnel |

**Structure d'une réponse OpenSky :**  
Chaque "state vector" est un tableau de 17 champs positionnels (pas de clés nommées). GDash accède aux champs par index :

```
s[1]  → callsign
s[2]  → pays d'origine
s[5]  → longitude
s[6]  → latitude
s[7]  → altitude barométrique (m)
s[9]  → vitesse sol (m/s)
```

**Post-traitement :** agrégation par pays, extraction des 5 avions volant le plus haut, comptage total mondial.

**Limitation :** Sans compte OpenSky, le taux est limité à ~100 req/jour depuis la même IP. Avec compte (gratuit), la limite monte à ~4 000 req/jour.

---

### 4.3 Trafic maritime

| Source | Protocole | Données | Clé requise |
|---|---|---|---|
| **MarineTraffic** | RSS | Mises à jour de position de navires | ❌ Non |
| **NavalNews** | RSS | Actualités navales mondiales | ❌ Non |

**Note :** Le flux RSS public MarineTraffic est très limité. L'API complète de MarineTraffic est payante. C'est un point d'amélioration identifié (voir §10).

---

### 4.4 Géophysique

| Source | Protocole | Données | Clé requise |
|---|---|---|---|
| **USGS Earthquake** | GeoJSON REST | Séismes significatifs du jour, séismes ≥4.5 de la semaine | ❌ Non |
| **Smithsonian GVP** | RSS | Alertes volcaniques hebdomadaires | ❌ Non |
| **NOAA Aurora** | JSON REST | Indice K planétaire (activité aurorale) | ❌ Non |
| **NOAA Tides** | JSON REST | Prédictions de marées (station San Francisco) | ❌ Non |

**Post-traitement séismes :** conversion du timestamp Unix milliseconds en ISO 8601 UTC, extraction des coordonnées depuis la géométrie GeoJSON.

**Calcul de visibilité aurorale :**  
L'indice K planétaire (0-9) est traduit en latitude minimale de visibilité :
- K > 5 → visible dès 50°N (France du Nord incluse !)
- K > 3 → visible dès 60°N (Scandinavie)

---

### 4.5 Espace

| Source | Protocole | Données | Clé requise |
|---|---|---|---|
| **Open Notify** | JSON REST | Position ISS en temps réel | ❌ Non |
| **Open Notify** | JSON REST | Astronautes actuellement dans l'espace | ❌ Non |
| **SpaceWeatherLive** | RSS | Alertes météo spatiale | ❌ Non |

---

### 4.6 Marchés et crypto

| Source | Protocole | Données | Clé requise |
|---|---|---|---|
| **CoinGecko** | JSON REST | Prix BTC, ETH, ADA, SOL, DOT (USD & EUR, variation 24h) | ❌ Non |
| **CoinGecko Global** | JSON REST | Dominance de marché par crypto | ❌ Non |
| **Open Exchange Rates (er-api)** | JSON REST | Taux de change USD → EUR, GBP, JPY... | ❌ Non |

---

### 4.7 Sécurité et crises

| Source | Protocole | Données | Clé requise |
|---|---|---|---|
| **GDACS (ONU)** | RSS | Catastrophes naturelles et alertes humanitaires mondiales | ❌ Non |
| **CISA** | RSS | Alertes cybersécurité USA | ❌ Non |
| **Krebs on Security** | RSS | Actualités cybersécurité | ❌ Non |
| **NASA EONET** | JSON REST | Incendies de forêt actifs | ❌ Non |

---

### 4.8 Santé publique

| Source | Protocole | Données | Clé requise |
|---|---|---|---|
| **disease.sh** | JSON REST | Statistiques COVID-19 mondiales (cumulatif) | ❌ Non |

---

## 5. Carte des endpoints

```
GET /                   → Index des routes + statut opérationnel
GET /summary            → Agrégation de TOUTES les sources (endpoint principal)
│
├── GET /weather        → Météo locale (Open-Meteo)
├── GET /weather/extremes → Températures extrêmes mondiales
├── GET /weather/alerts → Alertes NOAA CAP
│
├── GET /flights        → Trafic aérien mondial (OpenSky)
├── GET /maritime       → Trafic maritime + actualités navales
│
├── GET /seismic        → Séismes USGS
├── GET /volcanoes      → Activité volcanique Smithsonian
├── GET /aurora         → Indice K aurorale NOAA
├── GET /ocean          → Marées + température maritime
│
├── GET /space          → ISS + astronautes + météo spatiale
│
├── GET /crypto         → Prix cryptomonnaies (CoinGecko)
├── GET /markets        → Forex + sentiment de marché
│
├── GET /conflicts      → Catastrophes/conflits GDACS
├── GET /cyber          → Alertes cybersécurité CISA + Krebs
├── GET /wildfires      → Incendies NASA EONET
│
└── GET /pandemic       → Stats COVID disease.sh
```

**Documentation auto-générée :** `/docs` (Swagger UI) et `/redoc`

---

## 6. Flux de données et concurrence

### Endpoint `/summary` — chronologie d'exécution

```
Requête client
     │
     ▼
async with httpx.AsyncClient() as client:
     │
     ▼
asyncio.gather(                          ← LANCEMENT SIMULTANÉ
    fetch_weather(client),               ─┐
    fetch_weather_extremes(client),       │
    fetch_flights(client),                │  Groupe A
    fetch_seismic(client),                │  (nécessitent httpx.AsyncClient)
    fetch_space_data(client),             │
    fetch_crypto_prices(client),          │
    fetch_stock_market(client),           │
    fetch_pandemic_data(client),          │
    fetch_aurora_forecast(client),        │
    fetch_wildfires(client),              │
    fetch_ocean_data(client),            ─┘
)
     │
     ▼
asyncio.gather(                          ← SECOND GATHER (RSS feedparser)
    fetch_weather_alerts(),              ─┐
    fetch_maritime(),                     │  Groupe B
    fetch_conflicts(),                    │  (feedparser — synchrone en interne !)
    fetch_cybersecurity_news(),           │
    fetch_volcanic_activity(),           ─┘
)
     │
     ▼
Construction du dict de réponse
     │
     ▼
Retour JSON au client
```

### Latence théorique

La latence de `/summary` est dominée par **la plus lente des sources** dans chaque groupe (pas leur somme). Si toutes les APIs répondent en moins de 3 secondes, la réponse totale arrive en ~3-6 secondes, là où une approche séquentielle aurait pris 30-60 secondes.

| Source la plus lente | Timeout configuré |
|---|---|
| OpenSky Network | 15 s (explicite) |
| Toutes les autres | 10 s (via `safe_fetch`) |

---

## 7. Configuration et secrets

### Variables de configuration (en dur dans le code)

```python
DEFAULT_LAT = 48.85      # Paris — à paramétrer via env variable
DEFAULT_LON = 2.35
OPENSKY_USER = ""        # Optionnel
OPENSKY_PASS = ""        # Optionnel
```

**⚠️ Point d'attention :** Ces valeurs sont codées en dur dans `main_py38.py`. Pour un déploiement propre, elles doivent être externalisées en variables d'environnement (voir §10).

### Middleware CORS

```python
CORSMiddleware(
    allow_origins=["*"],    # Tous les domaines autorisés
    allow_methods=["GET"],  # Lecture seule — correct pour une API publique
    allow_headers=["*"],
)
```

`allow_origins=["*"]` est acceptable pour une API publique de consultation, mais devrait être restreint si l'API devient privée ou si des endpoints d'écriture sont ajoutés.

---

## 8. Containerisation et déploiement

### Image Docker

```
FROM python:3.8-slim
├── libxml2, libxslt1.1    (pour feedparser)
├── pip install requirements.txt
│   ├── fastapi ≥ 0.100
│   ├── uvicorn[standard] ≥ 0.22
│   ├── httpx ≥ 0.24
│   └── feedparser ≥ 6.0.8
└── CMD uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
```

### Stratégie de layers (mise en cache)

```
Layer 1 : python:3.8-slim          → changement : jamais
Layer 2 : apt-get install          → changement : rarement
Layer 3 : pip install requirements → changement : lors des mises à jour de deps
Layer 4 : COPY . .                 → changement : à chaque commit de code
```

Cette stratégie maximise la réutilisation du cache Docker et accélère les rebuilds.

### Déploiement SnapDeploy

```
GitHub Push
    │
    ▼
SnapDeploy détecte le Dockerfile
    │
    ▼
docker build → docker run
    │
    ▼
https://gdash.snapdeploy.app (URL publique)
```

**Tier gratuit SnapDeploy :**
- Auto-sleep après inactivité (cold start ~5s)
- 10 déploiements/jour
- Port 8000 auto-mappé en HTTPS

---

## 9. Analyse des risques

### 9.1 Risques de disponibilité

| Risque | Probabilité | Impact | Mitigation actuelle |
|---|---|---|---|
| Source externe indisponible | Haute | Faible | `safe_fetch()` retourne `{"error": ...}` |
| OpenSky rate limit dépassé | Moyenne | Moyen | Credentials optionnels configurables |
| CoinGecko throttling | Haute | Faible | API publique avec limits strictes |
| `feedparser` bloqué (timeout) | Faible | Faible | Pas de timeout sur feedparser ⚠️ |
| Cold start SnapDeploy (gratuit) | Certaine | Moyen | Passer en plan payant |

### 9.2 Risques de sécurité

| Point | Description |
|---|---|
| CORS `allow_origins=["*"]` | Acceptable en lecture seule, à restreindre si évolution |
| Credentials OpenSky en clair | Doivent impérativement passer en variables d'env |
| Pas d'authentification API | Normal pour une API publique de consultation |
| Pas de rate limiting | L'API peut être abusée — à ajouter (voir §10) |

### 9.3 Risques de données

| Point | Description |
|---|---|
| Données COVID disease.sh | API maintenue bénévolement, risque d'abandon |
| MarineTraffic RSS | Flux très limité, données peu exploitables |
| Coordonnées Paris hardcodées | Toutes les données "locales" pointent vers Paris |
| `fetch_nuclear_plants()` | URL invalide dans le code (`https://www RTE France/...`) |

---

## 10. Suggestions d'amélioration

### 🔴 Priorité haute

#### 1. Externaliser la configuration en variables d'environnement

```python
# Remplacer les valeurs en dur par :
import os

DEFAULT_LAT = float(os.getenv("DEFAULT_LAT", "48.85"))
DEFAULT_LON = float(os.getenv("DEFAULT_LON", "2.35"))
OPENSKY_USER = os.getenv("OPENSKY_USER", "")
OPENSKY_PASS = os.getenv("OPENSKY_PASS", "")
```

Injecter ensuite dans SnapDeploy via les variables d'environnement du container.  
**Pour Cherbourg :** `DEFAULT_LAT=49.63`, `DEFAULT_LON=-1.62`

---

#### 2. Partager le client `httpx` (lifespan)

Actuellement, un nouveau `httpx.AsyncClient` est créé **à chaque requête HTTP**. C'est coûteux (handshake TCP + TLS répété). La solution est d'utiliser le mécanisme `lifespan` de FastAPI pour créer un client partagé et réutilisable :

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        limits=httpx.Limits(max_connections=50),
    )
    yield
    await app.state.client.aclose()

app = FastAPI(lifespan=lifespan)
```

Gain attendu : **30-50% de réduction de latence** sur les endpoints.

---

#### 3. Corriger `fetch_nuclear_plants()`

La fonction contient une URL invalide (`https://www RTE France/api/...`). Elle doit soit être corrigée pour utiliser l'API RTE France réelle (avec clé OAuth2), soit remplacée par une source fonctionnelle.

---

#### 4. Ajouter un timeout sur `feedparser`

`feedparser.parse()` est synchrone et n'a pas de timeout natif. Un flux RSS lent bloque l'event loop. Solution :

```python
import asyncio

async def fetch_rss_safe(url: str, timeout: int = 8) -> list:
    loop = asyncio.get_event_loop()
    try:
        feed = await asyncio.wait_for(
            loop.run_in_executor(None, feedparser.parse, url),
            timeout=timeout
        )
        return feed.entries
    except asyncio.TimeoutError:
        return []
```

---

### 🟡 Priorité moyenne

#### 5. Ajouter un cache Redis (ou in-memory)

Les sources comme OpenSky, USGS ou CoinGecko n'ont pas besoin d'être interrogées à chaque requête client. Un cache TTL évite de dépasser les rate limits et accélère drastiquement les réponses :

```python
from functools import lru_cache
import time

_cache = {}

async def cached_fetch(key: str, fetcher, ttl: int = 60):
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < ttl:
        return _cache[key]["data"]
    data = await fetcher()
    _cache[key] = {"data": data, "ts": now}
    return data
```

**TTL recommandés par source :**

| Source | TTL suggéré |
|---|---|
| OpenSky (vols) | 30 secondes |
| USGS (séismes) | 2 minutes |
| Open-Meteo (météo) | 10 minutes |
| CoinGecko (crypto) | 1 minute |
| RSS GDACS, CISA | 15 minutes |
| disease.sh (COVID) | 1 heure |

---

#### 6. Ajouter du rate limiting sur l'API

Protéger l'API publique contre les abus avec `slowapi` (basé sur `limits`) :

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/summary")
@limiter.limit("10/minute")
async def summary(request: Request):
    ...
```

---

#### 7. Ajouter un endpoint `/health` standard

Pour les healthchecks SnapDeploy, Docker et monitoring :

```python
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
```

---

#### 8. Améliorer les données maritimes

Remplacer le flux RSS MarineTraffic (très pauvre) par :

- **AIS Hub** (gratuit, données AIS brutes) : `http://data.aishub.net/ws.php`
- **VesselFinder API** (tier gratuit disponible) : données de position en JSON
- **OpenSeaMap** : cartes et données ouvertes

---

### 🟢 Priorité basse / améliorations futures

#### 9. Ajouter WebSocket pour les données temps réel

Pour les données à haute fréquence (vols, ISS, crypto), une connexion WebSocket push serait plus efficace qu'un polling client :

```python
from fastapi import WebSocket

@app.websocket("/ws/flights")
async def flights_ws(websocket: WebSocket):
    await websocket.accept()
    while True:
        async with httpx.AsyncClient() as client:
            data = await fetch_flights(client)
        await websocket.send_json(data)
        await asyncio.sleep(30)
```

---

#### 10. Journalisation structurée

Remplacer les `print()` (absents mais courants) par un logger structuré compatible avec les agrégateurs de logs cloud :

```python
import logging
import json

logging.basicConfig(
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    level=logging.INFO
)
logger = logging.getLogger("gdash")
```

---

#### 11. Tests unitaires et d'intégration

Le projet ne contient aucun test. Un minimum viable avec `pytest` et `httpx` (qui inclut un `AsyncClient` de test) :

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "endpoints" in r.json()

def test_weather_returns_data():
    r = client.get("/weather")
    assert r.status_code == 200
    data = r.json()
    assert "current" in data or "error" in data
```

---

#### 12. Ajouter des sources francophones / européennes

GDash est centré sur des sources anglo-saxonnes. Pour une utilisation depuis Cherbourg, des sources pertinentes à ajouter :

| Source | Données | URL |
|---|---|---|
| **Météo-France** | Prévisions et vigilances France | `public.opendatasoft.com` |
| **RTE France** | Production électrique temps réel | `data.rte-france.com` |
| **BRGM** | Séismes France métropolitaine | `api.brgm.fr` |
| **Préfecture Maritime** | CROSS Jobourg (Manche) | Flux AIS Manche |
| **data.gouv.fr** | Données ouvertes françaises | `data.gouv.fr/api/1/` |

---

## Résumé des recommandations prioritaires

| # | Action | Effort | Impact |
|---|---|---|---|
| 1 | Variables d'environnement pour config | ⬛ Faible | ⬛⬛⬛ Critique |
| 2 | Client httpx partagé (lifespan) | ⬛⬛ Moyen | ⬛⬛⬛ Élevé |
| 3 | Corriger `fetch_nuclear_plants()` | ⬛ Faible | ⬛⬛ Moyen |
| 4 | Timeout feedparser (run_in_executor) | ⬛ Faible | ⬛⬛ Moyen |
| 5 | Cache in-memory avec TTL | ⬛⬛ Moyen | ⬛⬛⬛ Élevé |
| 6 | Rate limiting (`slowapi`) | ⬛ Faible | ⬛⬛ Moyen |
| 7 | Endpoint `/health` | ⬛ Minimal | ⬛ Utile |
| 8 | Sources maritimes alternatives | ⬛⬛ Moyen | ⬛⬛ Moyen |
| 9 | WebSocket pour données temps réel | ⬛⬛⬛ Élevé | ⬛⬛⬛ Élevé |
| 10 | Tests unitaires | ⬛⬛ Moyen | ⬛⬛ Moyen |

---

*Mémo généré le 15 mai 2026 · Basé sur l'analyse complète de `main_py38.py` v2.0.0*
