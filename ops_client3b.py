#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     GLOBE OPS CENTER — TERMINAL INTERFACE                    ║
║                          [ SYSTEME DE SURVEILLANCE ]                         ║
║                        Version 2.0 - Prête à l'emploi                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import httpx
import json
import logging
import os
import sys
import time
import signal
import argparse
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Deque
from collections import deque
from logging.handlers import RotatingFileHandler

# ── Dépendances Rich (terminal UI) ────────────────────────────────
try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.align import Align
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.spinner import Spinner
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    from rich.style import Style
    from rich.padding import Padding
    from rich.markup import escape
except ImportError:
    print("❌ Module 'rich' manquant. Installez-le : pip install rich")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("❌ Module 'httpx' manquant. Installez-le : pip install httpx")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"

# Palette de couleurs "Ops Center"
OPS_COLORS = {
    "background": "#0a0a0a",
    "primary": "#00ff9d",      # Vert néon
    "primary_dim": "#00aa66",
    "secondary": "#00b8ff",     # Bleu électrique
    "alert_critical": "#ff0044", # Rouge vif
    "alert_warning": "#ffaa00",  # Orange/jaune
    "alert_normal": "#00ff9d",   # Vert néon
    "header": "#ffffff",         # Blanc pur
    "border": "#1a5f7a",         # Bleu foncé
    "border_bright": "#00b8ff",
    "dim": "#666666",
    "highlight": "#ffffff",
    "glitch": "#ff00aa",         # Rose pour effets glitch
    "scan_line": "#00ff9d20",    # Vert très transparent
}

def load_config(path: Optional[str] = None) -> Dict:
    """Charge la configuration depuis un fichier JSON."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        print(f"⚠ Fichier de config introuvable : {config_path}")
        print("  Utilisation de la configuration par défaut.")
        return _default_config()
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # Injecter notre palette de couleurs
    if "display" in cfg and "color_scheme" in cfg["display"]:
        cfg["display"]["color_scheme"].update(OPS_COLORS)
    return cfg

def _default_config() -> Dict:
    return {
        "client": {
            "name": "GLOBE OPS CENTER", 
            "version": "1.0.0",
            "subtitle": "SYSTEME DE SURVEILLANCE MONDIAL", 
            "operator": "ADMIN",
            "classification": "TOP SECRET//SI//NOFORN"
        },
        "server": {
            "base_url": "http://localhost:8000", 
            "timeout_seconds": 15,
            "retry_attempts": 3, 
            "retry_delay_seconds": 2
        },
        "refresh": {
            "auto_refresh": True, 
            "interval_seconds": 30
        },
        "display": {
            "color_scheme": OPS_COLORS, 
            "max_items_per_panel": 5,
            "date_format": "%H:%M:%S UTC",
            "show_timestamps": True
        },
        "layout": {
            "columns": 2,
            "show_status_bar": True,
            "show_clock": True,
            "show_uptime": True,
            "panel_padding": 1
        },
        "modules": {
            "weather": {
                "enabled": True,
                "label": "🌤 MÉTÉO LOCALE",
                "endpoint": "/weather",
                "priority": 1,
                "alert_thresholds": {
                    "wind_kmh_warning": 50,
                    "wind_kmh_critical": 90,
                    "temperature_heat_warning": 35,
                    "temperature_cold_warning": -5
                }
            },
            "seismic": {
                "enabled": True,
                "label": "🌍 ACTIVITÉ SISMIQUE",
                "endpoint": "/seismic",
                "priority": 1,
                "alert_thresholds": {
                    "magnitude_warning": 5.0,
                    "magnitude_critical": 7.0
                }
            },
            "cyber": {
                "enabled": True,
                "label": "🔐 CYBERSÉCURITÉ",
                "endpoint": "/cyber",
                "priority": 1,
                "alert_thresholds": {
                    "threat_elevated": True
                }
            },
            "conflicts": {
                "enabled": True,
                "label": "⚠ CONFLITS",
                "endpoint": "/conflicts",
                "priority": 1
            },
            "wildfires": {
                "enabled": True,
                "label": "🔥 INCENDIES",
                "endpoint": "/wildfires",
                "priority": 1,
                "alert_thresholds": {
                    "count_warning": 5,
                    "count_critical": 10
                }
            },
            "space": {
                "enabled": True,
                "label": "🛸 ESPACE",
                "endpoint": "/space",
                "priority": 2
            },
            "crypto": {
                "enabled": True,
                "label": "₿ CRYPTO",
                "endpoint": "/crypto",
                "priority": 3
            },
            "flights": {
                "enabled": True,
                "label": "✈ TRAFIC AÉRIEN",
                "endpoint": "/flights",
                "priority": 2
            }
        },
        "alerts": {
            "enabled": True, 
            "log_to_file": False, 
            "flash_on_critical": True,
            "log_file": "ops_alerts.log"
        },
        "logging": {
            "enabled": False,
            "level": "INFO",
            "file": "ops_client.log"
        },
        "summary_mode": {
            "use_summary_endpoint": True,
            "summary_endpoint": "/summary",
            "fallback_to_individual": True
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging(cfg: Dict) -> logging.Logger:
    log_cfg = cfg.get("logging", {})
    logger = logging.getLogger("ops_client")
    logger.setLevel(getattr(logging, log_cfg.get("level", "INFO")))
    if log_cfg.get("enabled", False):
        handler = RotatingFileHandler(
            log_cfg.get("file", "ops_client.log"),
            maxBytes=log_cfg.get("max_size_mb", 10) * 1024 * 1024,
            backupCount=3,
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    return logger


# ══════════════════════════════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def wmo_code_to_text(code: int) -> str:
    """Traduit le code WMO Open-Meteo en texte lisible."""
    if code is None or not isinstance(code, (int, float)):
        return "—"
    
    codes = {
        0: "Ciel dégagé", 1: "Principalement dégagé", 2: "Partiellement nuageux",
        3: "Couvert", 45: "Brouillard", 48: "Brouillard givrant",
        51: "Bruine légère", 53: "Bruine modérée", 55: "Bruine dense",
        56: "Bruine verglaçante", 57: "Bruine verglaçante dense",
        61: "Pluie légère", 63: "Pluie modérée", 65: "Pluie forte",
        66: "Pluie verglaçante", 67: "Pluie verglaçante forte",
        71: "Neige légère", 73: "Neige modérée", 75: "Neige forte",
        77: "Grains de neige", 80: "Averses légères", 81: "Averses modérées",
        82: "Averses violentes", 85: "Averses de neige", 86: "Fortes averses de neige",
        95: "Orage", 96: "Orage avec grêle", 99: "Orage violent avec grêle",
    }
    return codes.get(int(code), f"Code {code}")


# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCHER
# ══════════════════════════════════════════════════════════════════════════════

class DataFetcher:
    def __init__(self, cfg: Dict, logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger
        self.base_url = cfg["server"]["base_url"].rstrip("/")
        self.timeout = cfg["server"].get("timeout_seconds", 15)
        self.retries = cfg["server"].get("retry_attempts", 3)
        self.retry_delay = cfg["server"].get("retry_delay_seconds", 2)
        self.use_summary = cfg.get("summary_mode", {}).get("use_summary_endpoint", False)
        self.summary_endpoint = cfg.get("summary_mode", {}).get("summary_endpoint", "/summary")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch(self, endpoint: str) -> Dict:
        """Récupère un endpoint spécifique."""
        url = f"{self.base_url}{endpoint}"
        for attempt in range(self.retries):
            try:
                client = await self._get_client()
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
                self.logger.debug(f"OK {endpoint}")
                return {"ok": True, "data": data, "endpoint": endpoint,
                        "fetched_at": datetime.now(timezone.utc).isoformat()}
            except httpx.ConnectError:
                return {"ok": False, "error": "SERVEUR INACCESSIBLE", "endpoint": endpoint}
            except httpx.TimeoutException:
                if attempt < self.retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    continue
                return {"ok": False, "error": "TIMEOUT", "endpoint": endpoint}
            except httpx.HTTPStatusError as e:
                return {"ok": False, "error": f"HTTP {e.response.status_code}", "endpoint": endpoint}
            except Exception as e:
                return {"ok": False, "error": str(e)[:80].upper(), "endpoint": endpoint}
        return {"ok": False, "error": "MAX RETRIES", "endpoint": endpoint}

    async def fetch_summary(self) -> Dict[str, Any]:
        """Récupère le résumé global."""
        result = await self.fetch(self.summary_endpoint)
        if result.get("ok"):
            data = result.get("data", {})
            # Aplatir la structure du summary
            flattened = {}
            if isinstance(data, dict):
                for category, category_data in data.items():
                    if isinstance(category_data, dict):
                        for key, value in category_data.items():
                            if isinstance(value, (dict, list)):
                                flattened[key] = {"ok": True, "data": value}
            return flattened
        return {}

    async def fetch_all(self, modules: Dict) -> Dict[str, Any]:
        """Récupère toutes les données."""
        # Essayer d'abord le mode summary
        if self.use_summary:
            summary_data = await self.fetch_summary()
            if summary_data:
                self.logger.info(f"Données summary reçues: {list(summary_data.keys())}")
                return summary_data
            if not self.cfg.get("summary_mode", {}).get("fallback_to_individual", True):
                return {}

        # Mode individuel (parallélisé)
        tasks = {}
        for mod_name, mod_cfg in modules.items():
            if mod_cfg.get("enabled", True):
                tasks[mod_name] = self.fetch(mod_cfg["endpoint"])

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        output = {}
        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                output[name] = {"ok": False, "error": str(result)}
            else:
                output[name] = result
        return output

    async def check_health(self) -> bool:
        try:
            client = await self._get_client()
            r = await client.get(f"{self.base_url}/", timeout=5)
            return r.status_code == 200
        except Exception:
            return False


# ══════════════════════════════════════════════════════════════════════════════
# ALERT MANAGER WITH SCROLLING FEED
# ══════════════════════════════════════════════════════════════════════════════

class AlertManager:
    def __init__(self, cfg: Dict, logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger
        self.alert_cfg = cfg.get("alerts", {})
        self.alert_log: Deque[Dict] = deque(maxlen=100)
        self.feed_items: Deque[Dict] = deque(maxlen=50)
        self._alert_file = self.alert_cfg.get("log_file", "ops_alerts.log")

    def _create_feed_item(self, module: str, level: str, msg: str, data: Any = None) -> Dict:
        """Crée un élément pour le feed scrolling."""
        return {
            "timestamp": datetime.now(timezone.utc),
            "module": module.upper(),
            "level": level,
            "message": msg,
            "raw_data": data,
        }

    def evaluate(self, module_name: str, data: Any, mod_cfg: Dict) -> Optional[Dict]:
        """Évalue les seuils d'alerte et ajoute au feed."""
        thresholds = mod_cfg.get("alert_thresholds", {})
        if not thresholds or not isinstance(data, dict):
            return None

        # Sismique
        if module_name == "seismic":
            quakes = data.get("significant_today", []) + data.get("recent_4.5plus", [])
            for q in quakes[:3]:
                mag = q.get("magnitude")
                if mag:
                    if mag >= thresholds.get("magnitude_critical", 7.0):
                        self.add_to_feed("SEISMIC", "CRITICAL", 
                                        f"SÉISME M{mag:.1f} — {q.get('place', 'LIEU INCONNU')[:40]}")
                    elif mag >= thresholds.get("magnitude_warning", 5.0):
                        self.add_to_feed("SEISMIC", "WARNING", 
                                        f"Séisme M{mag:.1f} — {q.get('place', 'LIEU INCONNU')[:40]}")

        # Météo
        elif module_name == "weather":
            current = data.get("current", {})
            wind = current.get("wind_kmh", 0) or 0
            temp = current.get("temperature_c", 20) or 20
            if wind >= thresholds.get("wind_kmh_critical", 90):
                self.add_to_feed("WEATHER", "CRITICAL", f"VENT VIOLENT: {wind} KM/H")
            elif wind >= thresholds.get("wind_kmh_warning", 50):
                self.add_to_feed("WEATHER", "WARNING", f"VENT FORT: {wind} KM/H")
            if temp >= thresholds.get("temperature_heat_warning", 35):
                self.add_to_feed("WEATHER", "WARNING", f"CHALEUR EXTRÊME: {temp}°C")
            elif temp <= thresholds.get("temperature_cold_warning", -5):
                self.add_to_feed("WEATHER", "WARNING", f"FROID EXTRÊME: {temp}°C")

        # Cyber
        elif module_name == "cyber":
            cisa_alerts = data.get("cisa_alerts", [])
            threat = data.get("threat_level", "Normal")
            if threat == "Elevated":
                self.add_to_feed("CYBER", "WARNING", "NIVEAU MENACE ÉLEVÉ")
            for alert in cisa_alerts[:2]:
                if alert.get("severity") == "High":
                    self.add_to_feed("CYBER", "CRITICAL", f"CISA: {alert.get('title', '')[:60]}")

        # Incendies
        elif module_name == "wildfires":
            count = data.get("count", 0)
            if count >= thresholds.get("count_critical", 10):
                self.add_to_feed("WILDFIRES", "CRITICAL", f"{count} INCENDIES ACTIFS")
            elif count >= thresholds.get("count_warning", 5):
                self.add_to_feed("WILDFIRES", "WARNING", f"{count} INCENDIES ACTIFS")

        # Conflits
        elif module_name == "conflicts":
            events = data.get("events", [])
            for event in events[:2]:
                severity = event.get("severity", "").lower()
                if severity in ["red", "extreme"]:
                    self.add_to_feed("CONFLICT", "CRITICAL", event.get("title", "")[:70])

        return None

    def add_to_feed(self, module: str, level: str, message: str, data: Any = None):
        """Ajoute un élément au feed scrolling."""
        item = self._create_feed_item(module, level, message, data)
        self.feed_items.appendleft(item)
        self.alert_log.appendleft(item)

        if self.alert_cfg.get("log_to_file", False):
            self._write_alert(item)

        self.logger.warning(f"FEED [{level}] {module}: {message}")

    def _write_alert(self, alert: Dict):
        try:
            with open(self._alert_file, "a") as f:
                f.write(json.dumps({
                    "timestamp": alert["timestamp"].isoformat(),
                    "module": alert["module"],
                    "level": alert["level"],
                    "message": alert["message"]
                }) + "\n")
        except Exception:
            pass

    def get_recent_alerts(self, n: int = 5) -> List[Dict]:
        return list(self.alert_log)[:n]

    def get_feed_items(self, n: int = 10) -> List[Dict]:
        return list(self.feed_items)[:n]


# ══════════════════════════════════════════════════════════════════════════════
# SCROLLING FEED RENDERER
# ══════════════════════════════════════════════════════════════════════════════

class ScrollingFeed:
    """Gère l'affichage du feed scrolling en bas de l'écran."""

    def __init__(self, height: int = 5):
        self.height = height
        self.lines: Deque[Text] = deque(maxlen=height)

    def add_item(self, item: Dict, colors: Dict):
        """Ajoute un item au feed."""
        timestamp = item["timestamp"].strftime("%H:%M:%S")
        level_color = colors["alert_critical"] if item["level"] == "CRITICAL" else colors["alert_warning"]

        text = Text()
        text.append(f"[{timestamp}] ", style=f"bold {colors['dim']}")
        text.append(f"[{item['module']}] ", style=f"bold {colors['secondary']}")
        text.append(f"{item['message']}", style=f"{level_color}")

        self.lines.appendleft(text)

    def render(self, colors: Dict) -> Panel:
        """Rend le panel du feed."""
        if not self.lines:
            content = Text(" EN ATTENTE DE DONNÉES...", style=f"dim {colors['dim']}")
        else:
            content = Text("\n").join(list(self.lines)[:self.height])

        return Panel(
            content,
            title="[bold #00b8ff]⚡ FLUX TEMPS RÉEL ⚡[/]",
            border_style=colors["border_bright"],
            box=box.HEAVY_EDGE,
            padding=(0, 1),
        )


# ══════════════════════════════════════════════════════════════════════════════
# GLITCH EFFECT
# ══════════════════════════════════════════════════════════════════════════════

class GlitchText:
    """Crée un effet de glitch sur le texte."""

    def __init__(self, base_text: str, glitch_chars: str = "!@#$%&*+="):
        self.base_text = base_text
        self.glitch_chars = glitch_chars

    def render(self) -> Text:
        """Rend le texte avec effet glitch aléatoire."""
        result = Text()

        for i, char in enumerate(self.base_text):
            if random.random() < 0.02:
                result.append(random.choice(self.glitch_chars), style=f"bold {OPS_COLORS['glitch']}")
            elif random.random() < 0.01:
                result.append(char, style=f"reverse {OPS_COLORS['primary']}")
            else:
                result.append(char, style=f"bold {OPS_COLORS['header']}")

        return result


# ══════════════════════════════════════════════════════════════════════════════
# PANEL RENDERERS
# ══════════════════════════════════════════════════════════════════════════════

class PanelRenderer:
    """Convertit les données API en panneaux Rich."""

    def __init__(self, cfg: Dict):
        self.cfg = cfg
        self.cs = cfg["display"]["color_scheme"]
        self.max_items = cfg["display"].get("max_items_per_panel", 5)

    def _border_style(self, level: str = "normal") -> str:
        if level == "critical":
            return self.cs["alert_critical"]
        elif level == "warning":
            return self.cs["alert_warning"]
        return self.cs["border_bright"]

    def _make_panel(self, content, title: str, border_style: str = None,
                    subtitle: str = None) -> Panel:
        """Crée un panel avec style ops."""
        return Panel(
            content,
            title=f"[bold {self.cs['primary']}]◉ {title}[/]",
            subtitle=f"[{self.cs['dim']}]{subtitle}[/]" if subtitle else None,
            border_style=border_style or self.cs["border_bright"],
            padding=(0, 1),
            box=box.HEAVY_EDGE,
        )

    def error_panel(self, title: str, error: str) -> Panel:
        t = Text(f"⚠ {error}", style=f"bold {self.cs['alert_warning']}")
        return self._make_panel(Align.center(t), title, self.cs["alert_warning"])

    def render_weather(self, data: Dict, mod_cfg: Dict) -> Panel:
        """Render météo."""
        if not data or "error" in data:
            return self.error_panel(mod_cfg["label"], data.get("error", "NO DATA"))

        # Extraction des données
        current = data.get("current", {})
        location = data.get("location", {})
        
        temp = current.get("temperature_c") or current.get("temperature_2m") or "—"
        wind = current.get("wind_kmh") or current.get("wind_speed_10m") or "—"
        weathercode = current.get("weathercode")
        desc = current.get("description") or wmo_code_to_text(weathercode)

        # Détermination du niveau d'alerte
        wind_val = float(wind) if isinstance(wind, (int, float)) else 0
        border = ("critical" if wind_val >= 90 else
                  "warning" if wind_val >= 50 else "normal")

        t = Table.grid(padding=(0, 1))
        t.add_column(style=f"bold {self.cs['dim']}", width=10)
        t.add_column(style=f"bold {self.cs['highlight']}")

        t.add_row("📍 ZONE", f"{location.get('name', 'PARIS')}")
        t.add_row("🌡 TEMP", f"[{'red' if temp != '—' and float(temp) > 30 else 'cyan'}]{temp}°C[/]")
        t.add_row("💨 VENT", f"{wind} km/h")
        t.add_row("☁ ÉTAT", f"[italic]{desc}[/]")

        return self._make_panel(t, mod_cfg["label"], self._border_style(border),
                               subtitle=f"MAJ {data.get('updated', '')[:16]}")

    def render_seismic(self, data: Dict, mod_cfg: Dict) -> Panel:
        """Render activité sismique."""
        if "error" in data:
            return self.error_panel(mod_cfg["label"], data["error"])

        quakes = (data.get("significant_today", []) or []) + (data.get("recent_4.5plus", []) or [])
        
        # Déduplication
        seen = set()
        unique = []
        for q in quakes:
            key = (q.get("place"), q.get("magnitude"))
            if key not in seen:
                seen.add(key)
                unique.append(q)

        t = Table(show_header=True, box=box.SIMPLE, padding=(0, 1))
        t.add_column("MAG", style="bold red", width=5, justify="center")
        t.add_column("ZONE", style=self.cs["highlight"], no_wrap=False)
        t.add_column("PROF", style=self.cs["dim"], width=6, justify="right")

        max_mag = 0
        for q in unique[:self.max_items]:
            mag = q.get("magnitude", 0) or 0
            max_mag = max(max_mag, mag)
            mag_str = f"{mag:.1f}" if isinstance(mag, float) else str(mag)
            mag_color = "red" if mag >= 7 else "yellow" if mag >= 5 else "green"
            place = escape((q.get("place") or "INCONNU")[:30])
            depth = f"{q.get('depth_km','?')}km"
            t.add_row(f"[{mag_color}]{mag_str}[/]", place, depth)

        if not unique:
            t = Text("✅ AUCUNE ACTIVITÉ", style=self.cs["alert_normal"])

        border = ("critical" if max_mag >= 7 else
                  "warning" if max_mag >= 5 else "normal")
        return self._make_panel(t, mod_cfg["label"], self._border_style(border))

    def render_cyber(self, data: Dict, mod_cfg: Dict) -> Panel:
        """Render cybersécurité."""
        if "error" in data:
            return self.error_panel(mod_cfg["label"], data["error"])

        cisa = data.get("cisa_alerts", [])
        threat = data.get("threat_level", "Normal")
        threat_color = "red" if threat == "Elevated" else "green"

        t = Table(show_header=False, box=None, padding=(0, 1))
        t.add_column(style="bold green", width=3)
        t.add_column(no_wrap=False)

        t.add_row("🔐", f"NIVEAU: [{threat_color}]{threat.upper()}[/]")

        for a in cisa[:3]:
            title = escape((a.get("title") or "")[:45])
            sev = a.get("severity", "Medium")
            color = "red" if sev == "High" else "yellow"
            t.add_row("⚡", f"[{color}]{title}[/]")

        border = "critical" if threat == "Elevated" else "normal"
        return self._make_panel(t, mod_cfg["label"], self._border_style(border))

    def render_conflicts(self, data: Dict, mod_cfg: Dict) -> Panel:
        """Render conflits."""
        if "error" in data:
            return self.error_panel(mod_cfg["label"], data["error"])

        events = data.get("events", [])
        t = Table(show_header=False, box=None, padding=(0, 1))
        t.add_column(style="bold red", width=3)
        t.add_column(no_wrap=False)

        if not events:
            t.add_row("✓", Text("AUCUN ÉVÉNEMENT", style=self.cs["alert_normal"]))
        else:
            for e in events[:self.max_items]:
                title = escape((e.get("title") or "")[:55])
                severity = e.get("severity", "")
                color = "red" if severity.lower() in ("red","extreme") else "yellow"
                t.add_row("⚠", f"[{color}]{title}[/]")

        border = "warning" if events else "normal"
        return self._make_panel(t, mod_cfg["label"], self._border_style(border))

    def render_wildfires(self, data: Dict, mod_cfg: Dict) -> Panel:
        """Render incendies."""
        if "error" in data:
            return self.error_panel(mod_cfg["label"], data["error"])

        fires = data.get("active_wildfires", [])
        count = data.get("count", len(fires))

        t = Table(show_header=False, box=None, padding=(0, 1))
        t.add_column(style="bold red", width=3)
        t.add_column(no_wrap=False)

        t.add_row("🔥", f"[bold]{count} INCENDIE(S) ACTIF(S)[/]")
        for f in fires[:self.max_items-1]:
            title = escape((f.get("title") or "INCENDIE")[:40])
            t.add_row("", f"[yellow]{title}[/]")

        border = "critical" if count > 5 else "warning" if count > 0 else "normal"
        return self._make_panel(t, mod_cfg["label"], self._border_style(border))

    def render_space(self, data: Dict, mod_cfg: Dict) -> Panel:
        """Render espace."""
        if "error" in data:
            return self.error_panel(mod_cfg["label"], data["error"])

        t = Table.grid(padding=(0, 1))
        t.add_column(style=self.cs["dim"], width=14)
        t.add_column(style=f"bold {self.cs['primary']}")

        iss = data.get("iss_position", {})
        astros = data.get("astronauts_in_space", {})

        if iss:
            t.add_row("🛸 ISS LAT", f"{iss.get('lat', '—'):.2f}°" if iss.get('lat') else "—")
            t.add_row("🛸 ISS LON", f"{iss.get('lon', '—'):.2f}°" if iss.get('lon') else "—")

        if astros:
            count = astros.get('count', 0)
            t.add_row("👨‍🚀 ASTROS", f"{count} EN ORBITE")
            crafts = astros.get('crafts', [])
            if crafts:
                t.add_row("", f"[dim]{', '.join(crafts[:2])}[/]")
        else:
            # Fallback
            people = data.get("people", [])
            if people:
                t.add_row("👨‍🚀 ASTROS", f"{len(people)} EN ORBITE")
            else:
                t.add_row("📡 STATUT", "SYSTÈME SPATIAL OK")

        return self._make_panel(t, mod_cfg["label"])

    def render_crypto(self, data: Dict, mod_cfg: Dict) -> Panel:
        """Render crypto."""
        if "error" in data:
            return self.error_panel(mod_cfg["label"], data["error"])

        coins = data.get("cryptocurrencies", {})
        t = Table(show_header=True, box=box.SIMPLE, padding=(0, 1))
        t.add_column("ASSET", style=self.cs["primary"], width=8)
        t.add_column("USD", justify="right", style="bold white")
        t.add_column("24H", justify="right", width=7)

        symbols = {
            "bitcoin": "₿BTC", "ethereum": "ΞETH",
            "solana": "◎SOL", "cardano": "₳ADA"
        }

        for coin, vals in list(coins.items())[:4]:
            chg = vals.get("change_24h_percent")
            chg_str = f"{chg:+.1f}%" if isinstance(chg, (int, float)) else "—"
            chg_color = "green" if isinstance(chg, (int, float)) and chg >= 0 else "red"
            usd = vals.get("usd")
            usd_str = f"${usd:,.0f}" if isinstance(usd, (int, float)) else "—"
            t.add_row(symbols.get(coin, coin[:4]), usd_str, f"[{chg_color}]{chg_str}[/]")

        return self._make_panel(t, mod_cfg["label"],
                               subtitle=data.get("updated", "")[11:16])

    def render_flights(self, data: Dict, mod_cfg: Dict) -> Panel:
        """Render trafic aérien."""
        if "error" in data:
            return self.error_panel(mod_cfg["label"], data["error"])

        total = data.get("total_aircraft_worldwide", "—")
        
        t = Table.grid(padding=(0, 1))
        t.add_column(style=self.cs["dim"], width=12)
        t.add_column(style=f"bold {self.cs['primary']}")

        t.add_row("✈ TOTAL", f"{total:,}" if isinstance(total, int) else str(total))

        top_countries = data.get("top_countries", [])
        for c in top_countries[:3]:
            t.add_row(f"  {c.get('country','?')[:10]}", str(c.get("count", "—")))

        return self._make_panel(t, mod_cfg["label"])

    def render(self, module_name: str, result: Dict, mod_cfg: Dict) -> Panel:
        """Dispatch vers le bon renderer."""
        if not result.get("ok"):
            return self.error_panel(mod_cfg.get("label", module_name),
                                   result.get("error", "ERREUR"))

        data = result.get("data", {})

        renderers = {
            "weather": self.render_weather,
            "seismic": self.render_seismic,
            "cyber": self.render_cyber,
            "conflicts": self.render_conflicts,
            "wildfires": self.render_wildfires,
            "space": self.render_space,
            "crypto": self.render_crypto,
            "flights": self.render_flights,
        }

        fn = renderers.get(module_name)
        if fn:
            try:
                return fn(data, mod_cfg)
            except Exception as ex:
                return self.error_panel(mod_cfg.get("label", module_name), f"RENDER: {type(ex).__name__}")

        # Fallback
        return self._make_panel(
            Text(json.dumps(data, indent=2, ensure_ascii=False)[:200], style=self.cs["dim"]),
            mod_cfg.get("label", module_name)
        )


# ══════════════════════════════════════════════════════════════════════════════
# HEADER BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_header(cfg: Dict, start_time: float, online: bool, glitch: GlitchText) -> Panel:
    """Construit le header avec effet glitch."""
    cs = cfg["display"]["color_scheme"]
    client_cfg = cfg["client"]

    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    uptime_s = int(time.time() - start_time)
    h, rem = divmod(uptime_s, 3600)
    m, s = divmod(rem, 60)

    header_text = Text()
    header_text.append("╔" + "═" * 78 + "╗\n", style=cs["border"])
    header_text.append("║", style=cs["border"])
    header_text.append(glitch.render())
    header_text.append(" " * (78 - len(client_cfg.get("name", "")) - 2), style=cs["border"])
    header_text.append("║\n", style=cs["border"])

    subtitle = client_cfg.get("subtitle", "").upper()
    header_text.append("║", style=cs["border"])
    header_text.append(f" {subtitle} ", style=f"bold {cs['secondary']}")
    header_text.append(" " * (78 - len(subtitle) - 3), style=cs["border"])
    header_text.append("║\n", style=cs["border"])

    status = "● ONLINE" if online else "○ OFFLINE"
    status_color = cs["alert_normal"] if online else cs["alert_critical"]

    info = f"║ OP: {client_cfg.get('operator','?')}  |  NIVEAU: {client_cfg.get('classification','?')}  |  UTC: {now}  |  UPTIME: {h:02d}:{m:02d}:{s:02d}  |  {status}  ║"
    header_text.append(info, style=f"{cs['border']}")
    header_text.append(f"\n╚{'═' * 78}╝", style=cs["border"])

    return Panel(
        header_text,
        border_style=cs["border"],
        box=box.SQUARE,
        padding=(0, 0),
    )


def build_status_bar(cfg: Dict, modules: Dict, results: Dict,
                     last_refresh: float, refresh_interval: int,
                     packet_count: int) -> Panel:
    """Barre de statut."""
    cs = cfg["display"]["color_scheme"]
    next_refresh = int(refresh_interval - (time.time() - last_refresh))
    next_refresh = max(0, next_refresh)

    ok_count = sum(1 for r in results.values() if r.get("ok"))
    total_count = len(results)

    packets = "◉" * min(packet_count % 10, 10) + "○" * (10 - min(packet_count % 10, 10))

    content = Text()
    content.append("█ ", style=cs["border"])
    content.append(f"MODULES: {ok_count:02d}/{total_count:02d}", style=cs["primary"])
    content.append(" █ ", style=cs["border"])
    content.append(f"PAQUETS: {packets}", style=cs["secondary"])
    content.append(" █ ", style=cs["border"])
    content.append(f"REFRESH: -{next_refresh:02d}s", style=cs["dim"])
    content.append(" █", style=cs["border"])

    return Panel(
        Align.center(content),
        box=box.SQUARE,
        border_style=cs["border"],
        padding=(0, 0),
    )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN OPS CENTER
# ══════════════════════════════════════════════════════════════════════════════

class OpsCenter:
    def __init__(self, cfg: Dict, logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger
        self.fetcher = DataFetcher(cfg, logger)
        self.alert_mgr = AlertManager(cfg, logger)
        self.renderer = PanelRenderer(cfg)
        self.console = Console()
        self.start_time = time.time()
        self.last_refresh = 0.0
        self.results: Dict[str, Any] = {}
        self.running = True
        self.online = False
        self.packet_count = 0
        self.scrolling_feed = ScrollingFeed(height=5)
        self.glitch_header = GlitchText("   GLOBE OPS CENTER — NIVEAU 5   ")

    def _get_enabled_modules(self) -> Dict:
        """Récupère les modules activés."""
        modules = {}
        priority_order = ["seismic", "cyber", "conflicts", "wildfires", "weather", "space", "crypto", "flights"]
        
        for name in priority_order:
            if name in self.cfg["modules"] and self.cfg["modules"][name].get("enabled", True):
                modules[name] = self.cfg["modules"][name]
        
        return modules

    def _build_layout(self) -> Layout:
        """Construit le layout complet."""
        layout = Layout()
        layout.split(
            Layout(name="header", size=10),
            Layout(name="main"),
            Layout(name="feed", size=7),
            Layout(name="status", size=3),
        )

        # Header
        layout["header"].update(
            build_header(self.cfg, self.start_time, self.online, self.glitch_header)
        )

        # Panels principaux (2 colonnes)
        modules = self._get_enabled_modules()
        panels = []

        for name, mod_cfg in modules.items():
            result = self.results.get(name, {"ok": False, "error": "EN ATTENTE…"})
            panel = self.renderer.render(name, result, mod_cfg)
            panels.append(panel)

        # Distribution en 2 colonnes
        mid = len(panels) // 2 + (len(panels) % 2)
        left_panels = panels[:mid]
        right_panels = panels[mid:]

        from rich.console import Group
        left_group = Group(*left_panels)
        right_group = Group(*right_panels)

        main_layout = Layout()
        main_layout.split_row(
            Layout(left_group),
            Layout(right_group),
        )
        layout["main"].update(main_layout)

        # Feed scrolling
        feed_items = self.alert_mgr.get_feed_items(8)
        for item in feed_items:
            self.scrolling_feed.add_item(item, self.cfg["display"]["color_scheme"])
        layout["feed"].update(self.scrolling_feed.render(self.cfg["display"]["color_scheme"]))

        # Status bar
        refresh_int = self.cfg["refresh"].get("interval_seconds", 30)
        layout["status"].update(
            build_status_bar(self.cfg, modules, self.results,
                           self.last_refresh, refresh_int, self.packet_count)
        )

        return layout

    async def _refresh(self):
        """Lance un cycle de collecte."""
        modules = self._get_enabled_modules()
        self.online = await self.fetcher.check_health()

        if not self.online:
            self.logger.warning("Serveur inaccessible")
            self.alert_mgr.add_to_feed("SYSTEM", "WARNING", "SERVEUR INACCESSIBLE")
            return

        self.results = await self.fetcher.fetch_all(modules)
        self.last_refresh = time.time()
        self.packet_count += 1

        # Évaluation des alertes
        for name, result in self.results.items():
            if result.get("ok"):
                mod_cfg = modules.get(name, {})
                self.alert_mgr.evaluate(name, result.get("data", {}), mod_cfg)

        self.logger.info(f"Refresh #{self.packet_count} — {len(self.results)} modules")

    async def run(self):
        """Boucle principale."""
        interval = self.cfg["refresh"].get("interval_seconds", 30)
        auto = self.cfg["refresh"].get("auto_refresh", True)

        self.console.clear()
        self.console.show_cursor(False)

        with Live(
            self._build_layout(),
            console=self.console,
            refresh_per_second=10,
            screen=True,
        ) as live:
            # Premier refresh
            await self._refresh()

            while self.running:
                live.update(self._build_layout())

                if auto and (time.time() - self.last_refresh >= interval):
                    await self._refresh()

                await asyncio.sleep(0.1)

        self.console.show_cursor(True)
        await self.fetcher.close()


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(
        description="GLOBE OPS CENTER — Interface de surveillance mondiale",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", "-c", help="Fichier de configuration", default=None)
    parser.add_argument("--server", "-s", help="URL du serveur API", default=None)
    parser.add_argument("--interval", "-i", type=int, help="Intervalle de refresh (s)", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.server:
        cfg["server"]["base_url"] = args.server
    if args.interval:
        cfg["refresh"]["interval_seconds"] = args.interval

    logger = setup_logging(cfg)
    logger.info(f"Démarrage GLOBE OPS CENTER v{cfg['client'].get('version','?')}")

    ops = OpsCenter(cfg, logger)

    def _shutdown(signum, frame):
        ops.running = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        await ops.run()
    except KeyboardInterrupt:
        pass
    finally:
        await ops.fetcher.close()
        Console().print("\n[bold #00ff9d]GLOBE OPS CENTER — SESSION TERMINÉE[/]\n")


if __name__ == "__main__":
    asyncio.run(main())
