# Globe Dashboard — Backend FastAPI

Agrège en temps réel : météo, trafic aérien, maritime, conflits, séismes.

## Installation

```bash
cd backend
pip install -r requirements.txt
```

## Lancement

```bash
uvicorn main:app --reload --port 8000
```

## Endpoints

| Endpoint      | Description                              |
|---------------|------------------------------------------|
| `GET /`       | Index + liste des endpoints              |
| `GET /summary`| **Toutes les données** en une requête    |
| `GET /weather`| Météo locale (Open-Meteo, sans clé)      |
| `GET /flights`| Trafic aérien Europe (OpenSky)           |
| `GET /maritime`| Actualités maritimes (RSS NavalNews)    |
| `GET /conflicts`| Alertes catastrophes/conflits (GDACS) |
| `GET /seismic`| Séismes significatifs 24h (USGS)         |

## Configuration

Edite les constantes en haut de `main.py` :

```python
DEFAULT_LAT = 48.85   # Ta latitude
DEFAULT_LON = 2.35    # Ta longitude

OPENSKY_USER = ""     # Compte OpenSky (optionnel, augmente les limites)
OPENSKY_PASS = ""

ACLED_KEY   = ""      # Clé ACLED (gratuite sur acleddata.com) pour données conflits précises
ACLED_EMAIL = ""
```

## Sources utilisées

| Source | Données | Clé requise |
|--------|---------|-------------|
| [Open-Meteo](https://open-meteo.com) | Météo locale | ❌ Non |
| [NOAA CAP](https://alerts.weather.gov) | Alertes météo USA | ❌ Non |
| [OpenSky Network](https://opensky-network.org) | Trafic aérien | ❌ (limité anonyme) |
| [NavalNews RSS](https://navalnews.com) | Actualités maritimes | ❌ Non |
| [GDACS (UN)](https://gdacs.org) | Catastrophes & conflits | ❌ Non |
| [USGS](https://earthquake.usgs.gov) | Séismes | ❌ Non |
| [ACLED](https://acleddata.com) | Conflits armés détaillés | ✅ Gratuit |

## Documentation interactive

Après lancement : http://localhost:8000/docs (Swagger UI auto-généré par FastAPI)

## Prochaine étape

→ **frontend/index.html** — Page tuiles satellites (écran droit)
