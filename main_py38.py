#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Globe Dashboard API v2.0 — Backend FastAPI
Sources OSINT : météo, séismes, trafic, conflits, santé, espace, crypto...
Compatible Python 3.8.10+

🦠 Endpoint /pandemic : Données sanitaires via HantaOSINT + fallback disease.sh
   Attribution requise : CC-BY-SA-4.0 (https://hantaosint.com)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import feedparser
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import json

app = FastAPI(title="Globe Dashboard API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

DEFAULT_LAT = 48.85
DEFAULT_LON = 2.35
OPENSKY_USER = ""
OPENSKY_PASS = ""

# HantaOSINT Configuration
HANTAOSINT_API_URL = "https://hantaosint.com/api/v1/public.json"
HANTAOSINT_DELAY_SECONDS = 10  # Respect du rate limiting

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

async def safe_fetch(client: httpx.AsyncClient, url: str, **kwargs) -> Optional[Union[dict, list]]:
    """Fetch sécurisé avec gestion d'erreur."""
    try:
        r = await client.get(url, timeout=15, **kwargs)
        r.raise_for_status()
        return r.json()
    except httpx.TimeoutException:
        return {"error": f"Timeout sur {url}"}
    except httpx.HTTPError as e:
        return {"error": f"HTTP {e.__class__.__name__}: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"error": f"JSON invalide: {str(e)}"}
    except Exception as e:
        return {"error": f"{e.__class__.__name__}: {str(e)}"}

def wmo_code_to_text(code: int) -> str:
    """Traduit le code WMO Open-Meteo en texte lisible."""
    codes = {
        0: "Ciel dégagé", 1: "Principalement dégagé", 2: "Partiellement nuageux",
        3: "Couvert", 45: "Brouillard", 48: "Brouillard givrant",
        51: "Bruine légère", 53: "Bruine modérée", 55: "Bruine dense",
        61: "Pluie légère", 63: "Pluie modérée", 65: "Pluie forte",
        71: "Neige légère", 73: "Neige modérée", 75: "Neige forte",
        80: "Averses légères", 81: "Averses modérées", 82: "Averses violentes",
        95: "Orage", 96: "Orage avec grêle", 99: "Orage violent avec grêle",
    }
    return codes.get(code, f"Code WMO {code}")

def format_timestamp(ts_ms: Optional[int]) -> Optional[str]:
    """Formate un timestamp millisecondes en ISO UTC."""
    if not ts_ms:
        return None
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
    except (ValueError, OSError):
        return None

# ─────────────────────────────────────────────
# SOURCES ORIGINALES AMÉLIORÉES
# ─────────────────────────────────────────────

async def fetch_weather(client: httpx.AsyncClient) -> dict:
    """Open-Meteo — météo détaillée locale et globale."""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={DEFAULT_LAT}&longitude={DEFAULT_LON}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m&timezone=UTC"
        data = await safe_fetch(client, url)
        if "error" in data:
            return data
        current = data.get("current", {})
        return {
            "location": {"lat": DEFAULT_LAT, "lon": DEFAULT_LON},
            "current": {
                "temperature": current.get("temperature_2m"),
                "feels_like": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "wind_speed": current.get("wind_speed_10m"),
                "wind_direction": current.get("wind_direction_10m"),
                "wind_gusts": current.get("wind_gusts_10m"),
                "pressure": current.get("pressure_msl"),
                "cloud_cover": current.get("cloud_cover"),
                "precipitation": current.get("precipitation"),
                "weather_code": current.get("weather_code"),
                "weather_text": wmo_code_to_text(current.get("weather_code", -1)),
            },
            "updated": data.get("current_weather", {}).get("time") or datetime.now(timezone.utc).isoformat(),
            "source": "Open-Meteo",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_weather_extremes(client: httpx.AsyncClient) -> dict:
    """Températures extrêmes actuelles dans le monde via Open-Meteo."""
    try:
        # Points de référence pour extrêmes (approximatifs)
        locations = [
            {"name": "Vostok (Antarctique)", "lat": -78.46, "lon": 106.83},
            {"name": "Dallol (Éthiopie)", "lat": 14.24, "lon": 40.30},
            {"name": "Oïmiakon (Russie)", "lat": 63.27, "lon": 143.15},
            {"name": "Koweït City", "lat": 29.37, "lon": 47.98},
            {"name": "Death Valley (USA)", "lat": 36.51, "lon": -116.93},
        ]
        results = []
        for loc in locations:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={loc['lat']}&longitude={loc['lon']}&current=temperature_2m&timezone=UTC"
            data = await safe_fetch(client, url)
            if data and "error" not in data:
                results.append({
                    "location": loc["name"],
                    "temperature": data.get("current", {}).get("temperature_2m"),
                })
            await asyncio.sleep(0.5)  # Rate limiting API
        return {
            "extremes": results,
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "Open-Meteo",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_flights(client: httpx.AsyncClient) -> dict:
    """OpenSky Network — avions en vol (monde entier)."""
    try:
        url = "https://opensky-network.org/api/states/all"
        if OPENSKY_USER and OPENSKY_PASS:
            data = await safe_fetch(client, url, auth=(OPENSKY_USER, OPENSKY_PASS))
        else:
            data = await safe_fetch(client, url)
        if "error" in data:
            return data
        states = data.get("states", [])[:50]  # Limite à 50 pour performance
        return {
            "total_aircraft": data.get("total", len(states)),
            "sample": [
                {
                    "icao24": s[0],
                    "callsign": s[1].strip() if s[1] else None,
                    "origin_country": s[2],
                    "altitude": s[13],
                    "velocity": s[9],
                    "heading": s[10],
                }
                for s in states if s[1] and s[1].strip()
            ][:20],
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "OpenSky Network",
            "note": "Données temps réel — authentification recommandée pour usage intensif",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_maritime() -> dict:
    """MarineTraffic via vesselfinder + RSS maritime."""
    try:
        # RSS publics pour démos (limités)
        rss_urls = [
            "https://www.marinetraffic.com/en/rss/news",
        ]
        items = []
        for rss in rss_urls:
            feed = feedparser.parse(rss)
            for entry in feed.entries[:3]:
                items.append({
                    "title": entry.get("title"),
                    "link": entry.get("link"),
                    "published": entry.get("published"),
                })
        return {
            "news": items,
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "MarineTraffic RSS + VesselFinder (démonstration)",
            "note": "Pour données AIS temps réel : API payante requise",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_conflicts() -> dict:
    """GDACS (UN) — alertes catastrophes naturelles et conflits."""
    try:
        url = "https://www.gdacs.org/xml/rss.xml"
        feed = feedparser.parse(url)
        alerts = []
        for entry in feed.entries[:10]:
            alerts.append({
                "title": entry.get("title"),
                "link": entry.get("link"),
                "published": entry.get("published"),
                "summary": entry.get("summary", "")[:200] + "...",
                "gdacs_id": entry.get("gdacs_id"),
            })
        return {
            "alerts": alerts,
            "count": len(alerts),
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "GDACS (Global Disaster Alert and Coordination System)",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_seismic(client: httpx.AsyncClient) -> dict:
    """USGS — séismes significatifs et ressentis."""
    try:
        # Séismes significatifs (M4.5+) dernière heure
        url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_hour.geojson"
        data = await safe_fetch(client, url)
        if "error" in data:
            return data
        features = data.get("features", [])
        quakes = []
        for f in features:
            props = f.get("properties", {})
            geom = f.get("geometry", {}).get("coordinates", [])
            quakes.append({
                "magnitude": props.get("mag"),
                "location": props.get("place"),
                "depth_km": geom[2] if len(geom) > 2 else None,
                "lat": geom[1] if len(geom) > 1 else None,
                "lon": geom[0] if len(geom) > 0 else None,
                "time": format_timestamp(props.get("time")),
                "url": props.get("url"),
                "felt": props.get("felt"),
                "tsunami": props.get("tsunami") == 1,
            })
        return {
            "earthquakes": quakes,
            "count": len(quakes),
            "updated": data.get("metadata", {}).get("generated") or datetime.now(timezone.utc).isoformat(),
            "source": "USGS Earthquake Hazards Program",
        }
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────
# NOUVELLES SOURCES CRÉATIVES
# ─────────────────────────────────────────────

async def fetch_space_data(client: httpx.AsyncClient) -> dict:
    """Données spatiales : ISS, météo spatiale, lancements."""
    try:
        # Position ISS via WhereTheISS.at (API publique)
        iss_url = "https://api.wheretheiss.at/v1/satellites/25544"
        iss_data = await safe_fetch(client, iss_url)
        
        # Météo spatiale NOAA (indice Kp)
        space_weather = {"kp_index": None, "status": "inconnu"}
        try:
            sw_url = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
            sw_data = await safe_fetch(client, sw_url)
            if sw_data and "error" not in sw_data:
                latest = sw_data[-1] if isinstance(sw_data, list) and sw_data else None
                if latest:
                    space_weather = {
                        "kp_index": latest.get("kp"),
                        "status": "calme" if (latest.get("kp", 0) or 0) < 4 else "actif" if (latest.get("kp", 0) or 0) < 7 else "tempête",
                    }
        except:
            pass
        
        return {
            "iss": {
                "latitude": iss_data.get("latitude") if iss_data and "error" not in iss_data else None,
                "longitude": iss_data.get("longitude") if iss_data and "error" not in iss_data else None,
                "altitude_km": iss_data.get("altitude") if iss_data and "error" not in iss_data else None,
                "velocity_kmh": iss_data.get("velocity") if iss_data and "error" not in iss_data else None,
                "footprint_km": iss_data.get("footprint") if iss_data and "error" not in iss_data else None,
                "updated": format_timestamp(int(iss_data.get("timestamp", 0) * 1000)) if iss_data and "error" not in iss_data else None,
            } if iss_data and "error" not in iss_data else None,
            "space_weather": space_weather,
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "WhereTheISS.at + NOAA SWPC",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_crypto_prices(client: httpx.AsyncClient) -> dict:
    """Prix crypto via CoinGecko (API publique)."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,cardano,solana,polkadot&vs_currencies=usd,eur&include_24hr_change=true&include_market_cap=true"
        data = await safe_fetch(client, url)
        if "error" in data:
            return data
        return {
            "prices": {
                coin: {
                    "usd": info.get("usd"),
                    "eur": info.get("eur"),
                    "change_24h": info.get("usd_24h_change"),
                    "market_cap_usd": info.get("usd_market_cap"),
                }
                for coin, info in data.items()
            },
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "CoinGecko API",
            "note": "API publique — limites : ~10-30 req/min",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_stock_market(client: httpx.AsyncClient) -> dict:
    """Marchés boursiers via Yahoo Finance (scrapping léger) ou alternative."""
    try:
        # Utilisation de l'API publique de Twelve Data (clé gratuite requise pour prod)
        # Pour démo : données statiques simulées
        indices = {
            "CAC40": {"value": 7850.2, "change": 0.45, "currency": "EUR"},
            "DAX": {"value": 18234.1, "change": -0.12, "currency": "EUR"},
            "SP500": {"value": 5420.8, "change": 0.78, "currency": "USD"},
            "NIKKEI": {"value": 38915.3, "change": 1.23, "currency": "JPY"},
        }
        return {
            "indices": indices,
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "Simulation (pour prod : Twelve Data / Yahoo Finance API)",
            "note": "Données indicatives — délai 15min pour marchés réels",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_cybersecurity_news() -> dict:
    """Alertes cybersécurité via RSS."""
    try:
        rss_urls = [
            "https://www.cert.ssi.gouv.fr/alerte/feed/",
            "https://www.us-cert.gov/ncas/alerts.xml",
        ]
        items = []
        for rss in rss_urls:
            feed = feedparser.parse(rss)
            for entry in feed.entries[:5]:
                items.append({
                    "title": entry.get("title"),
                    "link": entry.get("link"),
                    "published": entry.get("published"),
                    "source": feed.feed.get("title", "Inconnu"),
                })
        return {
            "alerts": items,
            "count": len(items),
            "updated": datetime.now(timezone.utc).isoformat(),
            "sources": ["CERT-FR", "CISA US-CERT"],
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_nuclear_plants(client: httpx.AsyncClient) -> dict:
    """État des réacteurs nucléaires via API IAEA ou équivalent."""
    try:
        # IAEA PRIS n'a pas d'API publique JSON simple — fallback RSS
        url = "https://pris.iaea.org/PRIS/News/Rss.aspx"
        feed = feedparser.parse(url)
        news = []
        for entry in feed.entries[:5]:
            news.append({
                "title": entry.get("title"),
                "link": entry.get("link"),
                "published": entry.get("published"),
            })
        return {
            "news": news,
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "IAEA PRIS",
            "note": "Pour données réacteurs temps réel : scraping HTML requis",
        }
    except Exception as e:
        return {"error": str(e)}

# ═══════════════════════════════════════════════════════
# 🦠 ENDPOINT PANDEMIC — INTÉGRATION HANTAOSINT + FALLBACK
# ═══════════════════════════════════════════════════════

async def fetch_pandemic_data(client: httpx.AsyncClient) -> dict:
    """
    Données sanitaires via HantaOSINT (source principale) + disease.sh (fallback).
    
    Attribution requise : HantaOSINT est sous licence CC-BY-SA-4.0
    Source : https://hantaosint.com | https://hantaosint.com/api.html
    
    Note : Le flux public HantaOSINT a un délai de 24h. 
    Pour surveillance critique temps réel, privilégier les sources officielles.
    """
    results = {}
    
    # ── SOURCE PRINCIPALE : HantaOSINT ──────────────────
    try:
        hanta_url = HANTAOSINT_API_URL
        hanta_data = await safe_fetch(client, hanta_url)
        
        if hanta_data and "error" not in hanta_data:
            results["hantaosint"] = {
                "updated": hanta_data.get("updated"),
                "stats": hanta_data.get("stats", {}),
                "countries": hanta_data.get("countries", [])[:10],  # Top 10 pays
                "outbreaks": hanta_data.get("outbreaks", [])[:5],   # Top 5 épidémies
                "briefs": hanta_data.get("briefs", [])[:3],         # 3 dernières brèves
                "license": "CC-BY-SA-4.0",
                "attribution": "HantaOSINT (https://hantaosint.com)",
                "note": "Données avec délai de 24h — ne pas utiliser pour surveillance critique temps réel",
            }
        else:
            results["hantaosint_warning"] = "Données HantaOSINT non disponibles ou format inattendu"
            
    except Exception as e:
        results["hantaosint_error"] = f"{e.__class__.__name__}: {str(e)}"
    
    # ── FALLBACK : disease.sh (COVID-19 temps réel) ─────
    try:
        disease_url = "https://disease.sh/v3/covid-19/all"
        disease_data = await safe_fetch(client, disease_url)
        
        if disease_data and "error" not in disease_data:
            results["covid_realtime"] = {
                "global_stats": {
                    "cases": disease_data.get("cases"),
                    "deaths": disease_data.get("deaths"),
                    "recovered": disease_data.get("recovered"),
                    "active": disease_data.get("active"),
                    "today_cases": disease_data.get("todayCases"),
                    "today_deaths": disease_data.get("todayDeaths"),
                    "critical": disease_data.get("critical"),
                },
                "updated": format_timestamp(disease_data.get("updated")),
                "source": "disease.sh (Open Disease Data API)",
                "note": "Données COVID-19 mondiales en temps quasi-réel",
            }
    except Exception as e:
        results["covid_error"] = f"{e.__class__.__name__}: {str(e)}"
    
    # ── MÉTADONNÉES DE RÉPONSE ─────────────────────────
    return {
        "data": results,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "attribution": "HantaOSINT (CC-BY-SA-4.0) + disease.sh",
        "disclaimer": "Données à titre informatif uniquement. Vérifier auprès des autorités sanitaires pour prise de décision.",
    }

# ─────────────────────────────────────────────
# AUTRES FONCTIONS (inchangées)
# ─────────────────────────────────────────────

async def fetch_aurora_forecast(client: httpx.AsyncClient) -> dict:
    """Prévisions aurores boréales via NOAA."""
    try:
        url = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
        data = await safe_fetch(client, url)
        if "error" in data:
            return data
        # Calcul simple de prévision
        latest = data[-1] if isinstance(data, list) and data else {}
        kp = latest.get("kp", 0) or 0
        return {
            "kp_index": kp,
            "activity": "calme" if kp < 4 else "modérée" if kp < 7 else "intense",
            "visibility_zones": {
                "high_latitudes": kp >= 3,
                "mid_latitudes": kp >= 5,
                "low_latitudes": kp >= 7,
            },
            "forecast_3h": [d.get("kp") for d in data[-3:]] if isinstance(data, list) else [],
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "NOAA Space Weather Prediction Center",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_volcanic_activity() -> dict:
    """Activité volcanique via Smithsonian/USGS."""
    try:
        # RSS du Smithsonian Global Volcanism Program
        url = "https://volcano.si.edu/rss/vp_weekly.xml"
        feed = feedparser.parse(url)
        volcanoes = []
        for entry in feed.entries[:10]:
            volcanoes.append({
                "name": entry.get("title"),
                "country": entry.get("volcano_country"),
                "activity": entry.get("volcano_activity"),
                "summary": entry.get("summary", "")[:200] + "...",
                "link": entry.get("link"),
                "published": entry.get("published"),
            })
        return {
            "volcanoes": volcanoes,
            "count": len(volcanoes),
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "Smithsonian Institution - Global Volcanism Program",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_wildfires(client: httpx.AsyncClient) -> dict:
    """Incendies de forêt via NASA FIRMS."""
    try:
        # API NASA FIRMS (nécessite token pour usage intensif)
        url = "https://firms.modaps.eosdis.nasa.gov/api/country/csv/966d2c3c782f1b3994c0e592e12b0f88/MODIS_NRT/USA/1"
        # Pour démo : retour simulé (l'API CSV nécessite parsing spécifique)
        return {
            "fires": [],
            "count": 0,
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "NASA FIRMS",
            "note": "Pour données réelles : API CSV avec token requis — voir https://firms.modaps.eosdis.nasa.gov/api/",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_ocean_data(client: httpx.AsyncClient) -> dict:
    """Données océaniques : marées, température eau."""
    try:
        # Exemple : marées via WorldTides.info (API limitée)
        # Pour démo : données statiques
        return {
            "tides": {
                "location": f"{DEFAULT_LAT}, {DEFAULT_LON}",
                "next_high": None,
                "next_low": None,
                "water_temp_c": None,
            },
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "Simulation (pour prod : WorldTides / Copernicus Marine)",
            "note": "API marées gratuites très limitées — solutions pro requises pour données fiables",
        }
    except Exception as e:
        return {"error": str(e)}

async def fetch_weather_alerts() -> dict:
    """Alertes météo via RSS nationaux."""
    try:
        # Météo-France vigilance
        url = "https://vigilance.meteofrance.fr/fr/rss"
        feed = feedparser.parse(url)
        alerts = []
        for entry in feed.entries[:10]:
            alerts.append({
                "department": entry.get("vigilance_department"),
                "phenomenon": entry.get("vigilance_phenomenon"),
                "color": entry.get("vigilance_color"),
                "title": entry.get("title"),
                "link": entry.get("link"),
            })
        return {
            "alerts": alerts,
            "count": len(alerts),
            "updated": datetime.now(timezone.utc).isoformat(),
            "source": "Météo-France Vigilance",
        }
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "message": "Globe Dashboard API v2.0 - Python 3.8.10 Compatible",
        "endpoints": [
            "/summary",
            "/weather",
            "/weather/extremes",
            "/weather/alerts",
            "/flights",
            "/maritime",
            "/conflicts",
            "/seismic",
            "/space",
            "/crypto",
            "/markets",
            "/cyber",
            "/pandemic",
            "/aurora",
            "/volcanoes",
            "/wildfires",
            "/ocean",
        ],
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pandemic_sources": ["HantaOSINT (CC-BY-SA-4.0)", "disease.sh"],
    }

@app.get("/summary")
async def summary():
    """Endpoint principal — toutes les données agrégées."""
    async with httpx.AsyncClient() as client:
        # Données nécessitant le client HTTP
        weather, weather_extremes, flights, seismic, space, crypto, markets, pandemic, aurora, wildfires, ocean = await asyncio.gather(
            fetch_weather(client),
            fetch_weather_extremes(client),
            fetch_flights(client),
            fetch_seismic(client),
            fetch_space_data(client),
            fetch_crypto_prices(client),
            fetch_stock_market(client),
            fetch_pandemic_data(client),  # ← Intègre HantaOSINT + fallback
            fetch_aurora_forecast(client),
            fetch_wildfires(client),
            fetch_ocean_data(client),
        )

        # Données RSS (pas besoin de client)
        weather_alerts, maritime, conflicts, cyber, volcanoes = await asyncio.gather(
            fetch_weather_alerts(),
            fetch_maritime(),
            fetch_conflicts(),
            fetch_cybersecurity_news(),
            fetch_volcanic_activity(),
        )

        return {
            "meta": {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "version": "2.0.0",
                "data_sources_count": 17,
            },
            "atmosphere": {
                "local_weather": weather,
                "global_extremes": weather_extremes,
                "alerts": weather_alerts,
            },
            "transport": {
                "aviation": flights,
                "maritime": maritime,
            },
            "geophysics": {
                "seismic": seismic,
                "volcanic": volcanoes,
                "ocean": ocean,
                "aurora": aurora,
            },
            "space": space,
            "markets": {
                "crypto": crypto,
                "forex_stocks": markets,
            },
            "security": {
                "conflicts_disasters": conflicts,
                "cybersecurity": cyber,
                "wildfires": wildfires,
            },
            "health": pandemic,  # ← Données HantaOSINT + disease.sh
        }

# Endpoints individuels pour accès granulaire
@app.get("/weather")
async def weather_endpoint():
    async with httpx.AsyncClient() as client:
        return await fetch_weather(client)

@app.get("/weather/extremes")
async def weather_extremes_endpoint():
    async with httpx.AsyncClient() as client:
        return await fetch_weather_extremes(client)

@app.get("/weather/alerts")
async def weather_alerts_endpoint():
    return await fetch_weather_alerts()

@app.get("/flights")
async def flights_endpoint():
    async with httpx.AsyncClient() as client:
        return await fetch_flights(client)

@app.get("/maritime")
async def maritime_endpoint():
    return await fetch_maritime()

@app.get("/conflicts")
async def conflicts_endpoint():
    return await fetch_conflicts()

@app.get("/seismic")
async def seismic_endpoint():
    async with httpx.AsyncClient() as client:
        return await fetch_seismic(client)

@app.get("/space")
async def space_endpoint():
    async with httpx.AsyncClient() as client:
        return await fetch_space_data(client)

@app.get("/crypto")
async def crypto_endpoint():
    async with httpx.AsyncClient() as client:
        return await fetch_crypto_prices(client)

@app.get("/markets")
async def markets_endpoint():
    async with httpx.AsyncClient() as client:
        return await fetch_stock_market(client)

@app.get("/cyber")
async def cyber_endpoint():
    return await fetch_cybersecurity_news()

@app.get("/pandemic")
async def pandemic_endpoint():
    """
    Endpoint santé : Données HantaOSINT (multi-pathogènes) + COVID-19 disease.sh.
    
    Attribution CC-BY-SA-4.0 requise pour l'usage des données HantaOSINT.
    """
    async with httpx.AsyncClient() as client:
        return await fetch_pandemic_data(client)

@app.get("/aurora")
async def aurora_endpoint():
    async with httpx.AsyncClient() as client:
        return await fetch_aurora_forecast(client)

@app.get("/volcanoes")
async def volcanoes_endpoint():
    return await fetch_volcanic_activity()

@app.get("/wildfires")
async def wildfires_endpoint():
    async with httpx.AsyncClient() as client:
        return await fetch_wildfires(client)

@app.get("/ocean")
async def ocean_endpoint():
    async with httpx.AsyncClient() as client:
        return await fetch_ocean_data(client)

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
