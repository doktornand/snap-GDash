"""
Globe Dashboard — Backend FastAPI
Agrège météo, trafic aérien, maritime, conflits, finance, espace, cybersécurité et plus.
Compatible Python 3.8.10
Lance avec : uvicorn main:app --reload --port 8000
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

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

async def safe_fetch(client: httpx.AsyncClient, url: str, **kwargs) -> Optional[Union[dict, list]]:
    """Fetch sécurisé avec gestion d'erreur."""
    try:
        r = await client.get(url, timeout=10, **kwargs)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


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


# ─────────────────────────────────────────────
# SOURCES ORIGINALES AMÉLIORÉES
# ─────────────────────────────────────────────

async def fetch_weather(client: httpx.AsyncClient) -> dict:
    """Open-Meteo — météo détaillée locale et globale."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={DEFAULT_LAT}&longitude={DEFAULT_LON}"
        f"&current=temperature_2m,wind_speed_10m,weathercode,precipitation,relative_humidity_2m,pressure_msl"
        f"&hourly=temperature_2m,precipitation_probability"
        f"&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset"
        f"&timezone=Europe/Paris"
    )
    data = await safe_fetch(client, url)
    if "error" in data:
        return data
    c = data.get("current", {})
    daily = data.get("daily", {})
    return {
        "location": {"lat": DEFAULT_LAT, "lon": DEFAULT_LON, "name": "Paris"},
        "current": {
            "temperature_c": c.get("temperature_2m"),
            "wind_kmh": c.get("wind_speed_10m"),
            "precipitation_mm": c.get("precipitation"),
            "humidity_percent": c.get("relative_humidity_2m"),
            "pressure_hpa": c.get("pressure_msl"),
            "weathercode": c.get("weathercode"),
            "description": wmo_code_to_text(c.get("weathercode", -1)),
        },
        "forecast": {
            "today_max": daily.get("temperature_2m_max", [None])[0],
            "today_min": daily.get("temperature_2m_min", [None])[0],
            "sunrise": daily.get("sunrise", [None])[0],
            "sunset": daily.get("sunset", [None])[0],
        },
        "updated": c.get("time"),
    }


async def fetch_weather_extremes(client: httpx.AsyncClient) -> dict:
    """Températures extrêmes actuelles dans le monde via Open-Meteo."""
    # Points extrêmes : Death Valley, Oymyakon, etc.
    extremes = [
        {"name": "Death Valley (USA)", "lat": 36.46, "lon": -116.87},
        {"name": "Oymyakon (Russie)", "lat": 64.63, "lon": 143.21},
        {"name": "Dallol (Éthiopie)", "lat": 14.24, "lon": 40.30},
        {"name": "Vostok (Antarctique)", "lat": -78.46, "lon": 106.83},
    ]

    results = []
    for loc in extremes:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={loc['lat']}&longitude={loc['lon']}&current=temperature_2m"
        data = await safe_fetch(client, url)
        if "error" not in data:
            results.append({
                "location": loc["name"],
                "temperature_c": data.get("current", {}).get("temperature_2m"),
                "lat": loc["lat"],
                "lon": loc["lon"]
            })
    return {"extreme_temperatures": results}


async def fetch_weather_alerts() -> list:
    """NOAA CAP — alertes météo mondiales via RSS."""
    try:
        feed = feedparser.parse("https://alerts.weather.gov/cap/us.php?x=1")
        alerts = []
        for entry in feed.entries[:8]:
            alerts.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", "")[:250],
                "published": entry.get("published", ""),
                "link": entry.get("link", ""),
                "severity": entry.get("cap_severity", "Unknown"),
            })
        return alerts
    except Exception as e:
        return [{"error": str(e)}]


async def fetch_flights(client: httpx.AsyncClient) -> dict:
    """OpenSky Network — avions en vol (monde entier)."""
    try:
        r = await client.get(
            "https://opensky-network.org/api/states/all",
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        states = data.get("states") or []

        # Statistiques globales
        total = len(states)
        by_country = {}
        high_altitude = []

        for s in states:
            if s[2]:  # country
                by_country[s[2]] = by_country.get(s[2], 0) + 1
            if s[7] and s[7] > 10000:  # altitude > 10km
                high_altitude.append({
                    "callsign": (s[1] or "").strip(),
                    "country": s[2],
                    "altitude_m": s[7],
                    "velocity_ms": s[9],
                    "lat": s[6],
                    "lon": s[5],
                })

        # Top 5 pays
        top_countries = sorted(by_country.items(), key=lambda x: x[1], reverse=True)[:5]
        # Top 5 altitude
        top_altitude = sorted(high_altitude, key=lambda x: x["altitude_m"], reverse=True)[:5]

        return {
            "total_aircraft_worldwide": total,
            "top_countries": [{"country": c, "count": n} for c, n in top_countries],
            "top5_altitude": top_altitude,
            "timestamp": data.get("time"),
        }
    except Exception as e:
        return {"error": str(e)}


async def fetch_maritime() -> dict:
    """MarineTraffic via vesselfinder + RSS maritime."""
    try:
        # VesselFinder API publique (limitée mais fonctionnelle)
        feed = feedparser.parse("https://www.marinetraffic.com/en/rss/course/ports")
        items = []
        for entry in feed.entries[:5]:
            items.append({
                "title": entry.get("title", ""),
                "vessel_type": entry.get("mt_vessel_type", "Unknown"),
                "position": entry.get("mt_position", ""),
                "link": entry.get("link", ""),
            })

        # Fallback NavalNews
        naval_feed = feedparser.parse("https://www.navalnews.com/feed/")
        naval_items = []
        for entry in naval_feed.entries[:3]:
            naval_items.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", "")[:150],
                "link": entry.get("link", ""),
            })

        return {
            "vessel_updates": items,
            "naval_news": naval_items,
            "source": "MarineTraffic + NavalNews"
        }
    except Exception as e:
        return {"error": str(e)}


async def fetch_conflicts() -> dict:
    """GDACS (UN) — alertes catastrophes naturelles et conflits."""
    try:
        feed = feedparser.parse("https://www.gdacs.org/xml/rss.xml")
        events = []
        for entry in feed.entries[:10]:
            events.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", "")[:300],
                "published": entry.get("published", ""),
                "link": entry.get("link", ""),
                "severity": entry.get("gdacs_severity", entry.get("gdacs_alertlevel", "Unknown")),
                "event_type": entry.get("gdacs_eventtype", "Unknown"),
                "country": entry.get("gdacs_country", "Unknown"),
            })
        return {"source": "GDACS (UN)", "count": len(events), "events": events}
    except Exception as e:
        return {"error": str(e)}


async def fetch_seismic(client: httpx.AsyncClient) -> dict:
    """USGS — séismes significatifs et ressentis."""
    # Derniers séismes significatifs
    url_sig = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_day.geojson"
    # Derniers 4.5+ dans la dernière semaine
    url_week = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"

    data_sig = await safe_fetch(client, url_sig)
    data_week = await safe_fetch(client, url_week)

    def parse_quakes(data):
        features = data.get("features", []) if isinstance(data, dict) else []
        quakes = []
        for f in features[:5]:
            p = f.get("properties", {})
            g = f.get("geometry", {}).get("coordinates", [None, None, None])
            quakes.append({
                "place": p.get("place"),
                "magnitude": p.get("mag"),
                "depth_km": g[2],
                "time": datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc).isoformat() if p.get("time") else None,
                "url": p.get("url"),
                "felt": p.get("felt"),  # nombre de personnes l'ayant ressenti
            })
        return quakes

    return {
        "significant_today": parse_quakes(data_sig),
        "recent_4.5plus": parse_quakes(data_week),
    }


# ─────────────────────────────────────────────
# NOUVELLES SOURCES CRÉATIVES
# ─────────────────────────────────────────────

async def fetch_space_data(client: httpx.AsyncClient) -> dict:
    """Données spatiales : ISS, météo spatiale, lancements."""
    results = {}

    # Position ISS
    try:
        iss_data = await safe_fetch(client, "http://api.open-notify.org/iss-now.json")
        if "error" not in iss_data:
            pos = iss_data.get("iss_position", {})
            results["iss_position"] = {
                "lat": float(pos.get("latitude", 0)),
                "lon": float(pos.get("longitude", 0)),
                "timestamp": iss_data.get("timestamp"),
            }

        # Astronautes dans l'espace
        astro_data = await safe_fetch(client, "http://api.open-notify.org/astros.json")
        if "error" not in astro_data:
            results["astronauts_in_space"] = {
                "count": astro_data.get("number", 0),
                "names": [a.get("name") for a in astro_data.get("people", [])],
                "crafts": list(set([a.get("craft") for a in astro_data.get("people", [])])),
            }
    except Exception as e:
        results["error"] = str(e)

    # Météo spatiale (NOAA)
    try:
        noaa_feed = feedparser.parse("https://services.swpc.noaa.gov/products/alerts.json")
        # Alternative : RSS des alertes
        space_weather = feedparser.parse("https://www.spaceweatherlive.com/rss.xml")
        alerts = []
        for entry in space_weather.entries[:3]:
            alerts.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", "")[:200],
            })
        results["space_weather_alerts"] = alerts
    except:
        pass

    return results


async def fetch_crypto_prices(client: httpx.AsyncClient) -> dict:
    """Prix crypto via CoinGecko (API publique)."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,cardano,solana,polkadot&vs_currencies=usd,eur&include_24hr_change=true"
        data = await safe_fetch(client, url)
        if "error" in data:
            return data

        formatted = {}
        for coin, values in data.items():
            formatted[coin] = {
                "usd": values.get("usd"),
                "eur": values.get("eur"),
                "change_24h_percent": values.get("usd_24h_change"),
            }
        return {"cryptocurrencies": formatted, "updated": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"error": str(e)}


async def fetch_stock_market(client: httpx.AsyncClient) -> dict:
    """Marchés boursiers via Yahoo Finance alternative (twelvedata ou autre)."""
    # Utilisation d'une API publique sans clé
    try:
        # Forex taux de change
        forex_url = "https://open.er-api.com/v6/latest/USD"
        forex = await safe_fetch(client, forex_url)

        # Crypto comme proxy de marché volatil
        btc_dominance = "https://api.coingecko.com/api/v3/global"
        global_data = await safe_fetch(client, btc_dominance)

        return {
            "forex": {
                "EUR/USD": forex.get("rates", {}).get("EUR"),
                "GBP/USD": forex.get("rates", {}).get("GBP"),
                "JPY/USD": forex.get("rates", {}).get("JPY"),
                "updated": forex.get("time_last_update_utc"),
            },
            "market_sentiment": global_data.get("data", {}).get("market_cap_percentage", {}),
        }
    except Exception as e:
        return {"error": str(e)}


async def fetch_cybersecurity_news() -> dict:
    """Alertes cybersécurité via RSS."""
    try:
        # CISA Alerts
        cisa_feed = feedparser.parse("https://www.cisa.gov/uscert/ncas/current-activity.xml")
        # Krebs on Security
        krebs_feed = feedparser.parse("https://krebsonsecurity.com/feed/")

        cisa_alerts = []
        for entry in cisa_feed.entries[:5]:
            cisa_alerts.append({
                "title": entry.get("title", ""),
                "published": entry.get("published", ""),
                "link": entry.get("link", ""),
                "severity": "High" if "critical" in entry.get("title", "").lower() else "Medium",
            })

        krebs_news = []
        for entry in krebs_feed.entries[:3]:
            krebs_news.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", "")[:200],
                "link": entry.get("link", ""),
            })

        return {
            "cisa_alerts": cisa_alerts,
            "security_news": krebs_news,
            "threat_level": "Elevated" if len(cisa_alerts) > 3 else "Normal",
        }
    except Exception as e:
        return {"error": str(e)}


async def fetch_nuclear_plants(client: httpx.AsyncClient) -> dict:
    """État des réacteurs nucléaires via API IAEA ou équivalent."""
    # Utilisation de données EDF ouvertes ou équivalent
    try:
        # Simulation basée sur données ouvertes RTE France
        url = "https://www RTE France/api/v2/tempoLikeSupplyContract"
        # Fallback : données statiques simulées avec RSS énergie
        energy_feed = feedparser.parse("https://www.energycentral.com/rss/feed/")

        items = []
        for entry in energy_feed.entries[:3]:
            items.append({
                "title": entry.get("title", ""),
                "category": entry.get("category", "General"),
            })

        return {
            "note": "Données nucléaires en temps réel nécessitent API spécifique (IAEA/RTE)",
            "energy_news": items,
            "global_reactors_status": "Consultez iaea.org pour état temps réel",
        }
    except Exception as e:
        return {"error": str(e)}


async def fetch_pandemic_data(client: httpx.AsyncClient) -> dict:
    """Données pandémie via disease.sh (API COVID-19 ouverte)."""
    try:
        # Données mondiales COVID-19
        url = "https://disease.sh/v3/covid-19/all"
        data = await safe_fetch(client, url)
        if "error" in data:
            return data

        return {
            "global_covid_stats": {
                "cases": data.get("cases"),
                "deaths": data.get("deaths"),
                "recovered": data.get("recovered"),
                "active": data.get("active"),
                "today_cases": data.get("todayCases"),
                "today_deaths": data.get("todayDeaths"),
                "critical": data.get("critical"),
            },
            "updated": datetime.fromtimestamp(data.get("updated", 0)/1000, tz=timezone.utc).isoformat() if data.get("updated") else None,
            "source": "disease.sh (Open Disease Data API)",
        }
    except Exception as e:
        return {"error": str(e)}


async def fetch_aurora_forecast(client: httpx.AsyncClient) -> dict:
    """Prévisions aurores boréales via NOAA."""
    try:
        # NOAA Aurora forecast
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
        data = await safe_fetch(client, url)
        if isinstance(data, list) and len(data) > 1:
            # Format: [time_tag, kp, observed/estimated]
            latest = data[-1]
            return {
                "planetary_k_index": latest[1] if len(latest) > 1 else None,
                "forecast_time": latest[0] if len(latest) > 0 else None,
                "activity_level": "High" if float(latest[1]) > 5 else "Moderate" if float(latest[1]) > 3 else "Low",
                "visible_at_latitudes": ">50°N" if float(latest[1]) > 5 else ">60°N",
            }
        return {"data": data}
    except Exception as e:
        return {"error": str(e)}


async def fetch_volcanic_activity() -> dict:
    """Activité volcanique via Smithsonian/USGS."""
    try:
        feed = feedparser.parse("https://volcano.si.edu/news/WeeklyVolcanoRSS.xml")
        alerts = []
        for entry in feed.entries[:5]:
            alerts.append({
                "volcano": entry.get("title", "").split(":")[0] if ":" in entry.get("title", "") else entry.get("title", ""),
                "activity": entry.get("title", "").split(":")[1] if ":" in entry.get("title", "") else "Unknown",
                "summary": entry.get("summary", "")[:200],
                "link": entry.get("link", ""),
            })
        return {"volcanic_alerts": alerts, "source": "Smithsonian Global Volcanism Program"}
    except Exception as e:
        return {"error": str(e)}


async def fetch_wildfires(client: httpx.AsyncClient) -> dict:
    """Incendies de forêt via NASA FIRMS ou équivalent."""
    try:
        # NASA EONET pour catastrophes naturelles
        url = "https://eonet.gsfc.nasa.gov/api/v3/events?category=wildfires&status=open"
        data = await safe_fetch(client, url)
        if "error" in data:
            return data

        events = data.get("events", [])
        fires = []
        for event in events[:8]:
            geom = event.get("geometry", [{}])[0]
            fires.append({
                "title": event.get("title"),
                "date": event.get("date"),
                "coordinates": geom.get("coordinates"),
                "source": event.get("sources", [{}])[0].get("id"),
            })
        return {"active_wildfires": fires, "count": len(fires), "source": "NASA EONET"}
    except Exception as e:
        return {"error": str(e)}


async def fetch_ocean_data(client: httpx.AsyncClient) -> dict:
    """Données océaniques : marées, température eau."""
    try:
        # NOAA Tides and Currents (exemple pour station spécifique)
        # Station 9414290 - San Francisco
        url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?date=today&station=9414290&product=predictions&datum=mllw&units=metric&time_zone=lst_ldt&format=json"
        tide_data = await safe_fetch(client, url)

        # Température eau mer Méditerranée (exemple)
        # Utilisation d'Open-Meteo marine
        marine_url = "https://marine-api.open-meteo.com/v1/forecast?latitude=43.3&longitude=5.4&hourly=sea_surface_temperature"
        marine_data = await safe_fetch(client, marine_url)

        return {
            "tide_predictions": tide_data.get("predictions", [])[:4] if isinstance(tide_data, dict) else [],
            "sea_temperature_c": marine_data.get("hourly", {}).get("sea_surface_temperature", [None])[0] if isinstance(marine_data, dict) else None,
            "location": "Mediterranée / San Francisco",
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
            fetch_pandemic_data(client),
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
        "health": pandemic,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
