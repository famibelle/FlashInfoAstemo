#!/home/medhi/SourceCode/KreyolKeyb/.venv/bin/python3
"""
Flash info Guadeloupe — workflow complet
Collecte RSS → Script → Audio TTS (Voxtral) → Envoi Telegram
"""

import os
import re
import sys
import json
import time
import random
import base64
import argparse
import subprocess
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, date as Date, timedelta
from email.utils import parsedate
from pathlib import Path
from zoneinfo import ZoneInfo
import tempfile
from pathlib import Path

from datetime import datetime, date, time

from dateutil.parser import parse  # pip install python-dateutil si nécessaire



# ── Chargement du .env ────────────────────────────────────────────────────────

def _load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

_load_env(Path(__file__).parent / ".env")

# ── Config ────────────────────────────────────────────────────────────────────

from private.data.sources import RSS_FEEDS, RSS_SOURCES

_FEED_CATEGORY: dict[str, str] = {s.url: s.category for s in RSS_SOURCES}
MAX_ITEMS      = 7     # 7 sujets → ~2m-2m30 audio
DESC_MAX_CHARS = 400   # description tronquée pour donner assez de contexte
HASHTAG_COUNT  = 5     # nombre de hashtags générés par article

MISTRAL_API_KEY     = os.environ["MISTRAL_API_KEY"]
TTS_MODEL           = "voxtral-mini-tts-2603"
STT_MODEL           = "voxtral-mini-latest"
TTS_VOICE_DEFAULT   = "fr_marie_neutral"

# Mapping tonalité → voice_id Voxtral (voix Marie en français)
TTS_VOICES = {
    "neutral":  "fr_marie_neutral",
    "happy":    "fr_marie_happy",
    "excited":  "fr_marie_excited",
    "sad":      "fr_marie_sad",
    "angry":    "fr_marie_angry",
    "curious":  "fr_marie_curious",
}

TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID    = os.environ["TELEGRAM_CHAT_ID"]

BUZZSPROUT_API_TOKEN  = os.environ.get("BUZZSPROUT_API_TOKEN", "")
BUZZSPROUT_PODCAST_ID = os.environ.get("BUZZSPROUT_PODCAST_ID", "")

X_API_KEY            = os.environ.get("X_API_KEY", "")
X_API_SECRET         = os.environ.get("X_API_SECRET", "")
X_ACCESS_TOKEN       = os.environ.get("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET", "")

YOUTUBE_CLIENT_ID     = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

LINKEDIN_ACCESS_TOKEN  = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_REFRESH_TOKEN = os.environ.get("LINKEDIN_REFRESH_TOKEN", "")
LINKEDIN_CLIENT_ID     = os.environ.get("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_PERSON_ID     = os.environ.get("LINKEDIN_PERSON_ID", "")

INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_USER_ID      = os.environ.get("INSTAGRAM_USER_ID", "")

OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")

B2_KEY_ID          = os.environ.get("B2_KEY_ID", "")
B2_APPLICATION_KEY = os.environ.get("B2_APPLICATION_KEY", "")
B2_BUCKET_NAME     = os.environ.get("B2_BUCKET_NAME", "")
B2_ENDPOINT        = os.environ.get("B2_ENDPOINT", "")  # ex: https://s3.us-west-004.backblazeb2.com

ARCHIVE_ACCESS_KEY = os.environ.get("ARCHIVE_ACCESS_KEY", "")
ARCHIVE_SECRET_KEY = os.environ.get("ARCHIVE_SECRET_KEY", "")

GITHUB_TOKEN     = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO      = "famibelle/FlashInfoKarukera"

OUTPUT_DIR      = Path(tempfile.gettempdir()) / "flash_info_output"
STINGERS_DIR    = Path(__file__).parent / "Stingers"
PROMPTS_DIR     = Path(__file__).parent / "private" / "prompts"
MEDIA_DIR       = Path(__file__).parent / "Media"
DATA_DIR        = Path(__file__).parent / "data"
ARCHIVES_DIR    = Path(__file__).parent / "archives" / "flash-info"
DOCS_DIR        = Path(__file__).parent / "docs"
PODCAST_RSS_PATH = DOCS_DIR / "podcast.xml"
BOTIRAN_PROFILE = MEDIA_DIR / "botiran_profile.jpg"
GUADELOUPE_TZ   = ZoneInfo("America/Guadeloupe")

# ── Éditions ──────────────────────────────────────────────────────────────────

_EDITION_INTRO_INSTRUCTION = {
    "matin": (
        "ÉDITION DU MATIN — Intro : commence par 'Bèl bonjou' — ton chaleureux et "
        "énergique de début de matinée, comme on démarre ensemble la journée."
    ),
    "midi": (
        "ÉDITION DU MIDI — Intro : ton de mi-journée, direct et dynamique. "
        "Varie la formule (ex : 'On fait le point à midi', 'Voici vos infos de la mi-journée', "
        "'Pause actualité'...). Pas de 'Bèl bonjou' — réservé au matin."
    ),
    "soir": (
        "ÉDITION DU SOIR — Intro : bonsoir posé et chaleureux, comme un bulletin du soir "
        "qui clôture la journée et prépare le lendemain. Commence par 'Bonsoir' ou 'Bèl bonsoir'."
    ),
}

_EDITION_OUTRO = {
    "matin": ("Bonne journée",      "ce midi pour une nouvelle édition"),
    "midi":  ("Bonne après-midi",   "ce soir pour les prévisions et les dernières infos"),
    "soir":  ("Bonne soirée",       "demain matin pour démarrer la journée"),
}

today = datetime.now().date()  # Date du jour (ex: 2026-05-01)

def _now_paris_str(fmt: str) -> str:
    """Retourne l'heure actuelle à Paris au format spécifié."""
    paris_tz = ZoneInfo("Europe/Paris")
    now_paris = datetime.now(paris_tz)
    return now_paris.strftime(fmt)


def _detect_edition() -> str:
    """Détecte l'édition (matin/midi/soir) selon l'heure courante à Paris."""
    h = int(_now_paris_str("%H"))
    if h < 11:
        return "matin"
    if h < 18:
        return "midi"
    return "soir"


def _used_articles_path(target_date: Date) -> Path:
    return DATA_DIR / f"used_articles_{target_date}.json"


def load_used_titles(target_date: Date) -> set[str]:
    p = _used_articles_path(target_date)
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")).get("titles", []))
    except Exception:
        return set()


def save_used_titles(target_date: Date, new_titles: list[str]) -> None:
    p = _used_articles_path(target_date)
    all_titles = list(load_used_titles(target_date) | set(new_titles))
    p.write_text(json.dumps({"titles": all_titles}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾  Anti-répétition : {len(all_titles)} titres enregistrés ({p.name})")

WEATHER_LAT  = 16.17    # centre Guadeloupe (entre Basse-Terre et Grande-Terre)
WEATHER_LON  = -61.58
WEATHER_API         = "https://api.open-meteo.com/v1/forecast"
WEATHER_API_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_FORECAST_DAYS = 16  # fenêtre maximale de l'API forecast

from data.geography import (
    LIEUX_GUADELOUPE as _LIEUX_GUADELOUPE,
    LIEUX_MONDE as _LIEUX_MONDE,
    SOURCE_NAMES as _SOURCE_NAMES,
)
from data.fetes_patronales import COMMUNES_FETES_PATRONALES as _COMMUNES_FETES_PATRONALES
from data.marroniers import get_marroniers_du_jour as _get_marroniers_du_jour
from data.tts_normalize import (
    PRONONCIATIONS_LOCALES as _PRONONCIATIONS_LOCALES,
    SIGLES_MOT as _SIGLES_MOT,
    ABBREVS as _ABBREVS,
)
from data.weather_codes import WMO_CODES as _WMO

# ── Helpers ───────────────────────────────────────────────────────────────────

_FR_MONTHS = {
    "January": "janvier", "February": "février", "March": "mars",
    "April": "avril", "May": "mai", "June": "juin",
    "July": "juillet", "August": "août", "September": "septembre",
    "October": "octobre", "November": "novembre", "December": "décembre",
}
_FR_DAYS = {
    "Monday": "lundi", "Tuesday": "mardi", "Wednesday": "mercredi",
    "Thursday": "jeudi", "Friday": "vendredi", "Saturday": "samedi", "Sunday": "dimanche",
}

def _source_name(url: str) -> str:
    """Extrait un nom de média lisible depuis l'URL d'un flux RSS."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return "Botiran News"
    host = (parsed.hostname or "").removeprefix("www.")
    for key, name in _SOURCE_NAMES.items():
        if key in host:
            return name
    # fallback : premier segment du domaine, capitalisé
    return host.split(".")[0].capitalize()


# Fallback pour reconstruire category depuis le nom de source (items.json anciens)
_SOURCE_CATEGORY: dict[str, str] = {
    _source_name(s.url): s.category for s in RSS_SOURCES
}


_LIEUX_GUADELOUPE_LOWER = {l.lower(): l for l in _LIEUX_GUADELOUPE}
_LIEUX_MONDE_LOWER = {l.lower(): l for l in _LIEUX_MONDE}

def _extract_lieu(title: str, desc: str) -> str:
    """
    Cherche un lieu géographique dans title + desc.
    Priorité : commune guadeloupéenne → pays/ville mondiale → N/A.
    """
    import re
    haystack = f"{title} {desc}".lower()

    def _match(mapping: dict) -> str | None:
        for lieu_low, lieu_orig in mapping.items():
            pat = r"(?<![a-zàâéèêëîïôùûüç])" + re.escape(lieu_low) + r"(?![a-zàâéèêëîïôùûüç])"
            if re.search(pat, haystack):
                return lieu_orig
        return None

    return _match(_LIEUX_GUADELOUPE_LOWER) or _match(_LIEUX_MONDE_LOWER) or "N/A"


def _date_fr(d: Date) -> str:
    """Retourne ex: 'samedi 19 avril 2026'."""
    day = d.strftime("%d").lstrip("0") or "0"
    s = d.strftime(f"%A {day} %B %Y")    
    for en, fr in {**_FR_DAYS, **_FR_MONTHS}.items():
        s = s.replace(en, fr)
    return s


def _load_prompt(filename: str) -> str:
    """Charge un prompt système depuis le dossier prompts/ en retirant le trailing whitespace."""
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8").rstrip()


# ── Étape 1 : Collecte RSS ────────────────────────────────────────────────────

def _shorten_desc(text: str, max_chars: int) -> str:
    """Garde la première phrase ou tronque à max_chars caractères."""
    text = text.strip()
    for sep in (".", "!", "?"):
        idx = text.find(sep)
        if 20 < idx <= max_chars:
            return text[: idx + 1]
    return text[:max_chars].rsplit(" ", 1)[0] if len(text) > max_chars else text


def _parse_feed_items(root: ET.Element, cutoff: datetime) -> list[tuple]:
    results = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    today = datetime.now().date()  # Date du jour

    # RSS <item>
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        pub_date_str = (item.findtext("pubDate") or "").strip()
        desc = _shorten_desc((item.findtext("description") or "").strip(), DESC_MAX_CHARS)
        if not title or not desc:
            continue

        # Convertir pub_date_str en date
        try:
            pub_date = parse(pub_date_str).date()  # Convertit en objet date
        except (ValueError, TypeError):
            pub_date = None

        results.append((pub_date, title, pub_date_str, desc))

    # Atom <entry>
    for entry in root.findall(".//atom:entry", ns) or root.findall(".//entry"):
        title_el = entry.find("atom:title", ns) or entry.find("title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        updated_el = entry.find("atom:updated", ns) or entry.find("updated") or entry.find("atom:published", ns) or entry.find("published")
        pub_date_str = (updated_el.text or "").strip() if updated_el is not None else ""
        summary_el = entry.find("atom:summary", ns) or entry.find("summary") or entry.find("atom:content", ns) or entry.find("content")
        raw_desc = (summary_el.text or "").strip() if summary_el is not None else ""
        desc = _shorten_desc(raw_desc, DESC_MAX_CHARS)
        if not title or not desc:
            continue

        # Convertir pub_date_str en date
        try:
            pub_date = parse(pub_date_str).date()
        except (ValueError, TypeError):
            pub_date = None

        results.append((pub_date, title, pub_date_str, desc))

    return results

_LIEUX_GUADELOUPE_SET = {l.lower() for l in _LIEUX_GUADELOUPE} | {"guadeloupe", "karukera"}

def _lieu_priority(lieu: str) -> int:
    """0 = local Guadeloupe, 1 = lieu inconnu (N/A), 2 = international."""
    if lieu.lower() in _LIEUX_GUADELOUPE_SET:
        return 0
    if lieu == "N/A":
        return 1
    return 2


NEWS_WINDOW_HOURS = {
    "matin": 24,  # rattrape le décalage Guadeloupe UTC-4 vs Paris
    "midi":   8,  # nouvelles depuis le flash du matin
    "soir":   8,  # nouvelles depuis le flash du midi
}


def fetch_news(feeds: list[str], max_items: int, target_date: Date, edition: str = "matin", exclude_titles: "set[str] | None" = None) -> list[dict]:
    window = NEWS_WINDOW_HOURS.get(edition, 24)
    cutoff = datetime.utcnow() - timedelta(hours=window)
    print(f"📅 Fenêtre actualités : {window}h (depuis {cutoff.strftime('%Y-%m-%d %H:%M')} UTC)")
    all_items = []
    for url in feeds:
        print(f"📰 Collecte : {url}")
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                content = r.read()
            root = ET.fromstring(content)
            parsed = _parse_feed_items(root, cutoff)
            print(f"   {len(parsed)} actualités dans la fenêtre")
            all_items.extend((dt, t, d, desc, url) for dt, t, d, desc in parsed)
        except Exception as e:
            print(f"   ⚠️  Erreur sur {url} : {e}")

    # Tri par date décroissante (None en dernier)
    all_items.sort(key=lambda x: x[0] or datetime.min, reverse=True)

    candidates = [
        {
            "title": t, "date": d, "desc": desc,
            "source": _source_name(feed_url),
            "lieu": _extract_lieu(t, desc),
            "category": _FEED_CATEGORY.get(feed_url, "general"),
        }
        for _, t, d, desc, feed_url in all_items
    ]

    # Filtre anti-répétition : exclut les articles déjà diffusés dans une édition précédente
    if exclude_titles:
        _norm = str.lower
        excluded = {_norm(t) for t in exclude_titles}
        before = len(candidates)
        candidates = [c for c in candidates if _norm(c["title"]) not in excluded]
        if before != len(candidates):
            print(f"   🔁  Anti-répétition : {before - len(candidates)} article(s) déjà diffusé(s) exclus")

    # Les articles du fil custom sont toujours inclus s'il y en a pour le jour J.
    # Les autres slots sont remplis par priorité géographique (local → N/A → international).
    custom_items = [c for c in candidates if c["category"] == "custom"]
    other_items  = [c for c in candidates if c["category"] != "custom"]
    other_items.sort(key=lambda it: _lieu_priority(it["lieu"]))
    slots = max(0, max_items - len(custom_items))
    items = custom_items + other_items[:slots]

    local_count = sum(1 for it in items if _lieu_priority(it["lieu"]) == 0)
    intl_count  = sum(1 for it in items if _lieu_priority(it["lieu"]) == 2)
    print(f"   Total retenu : {len(items)} actualités "
          f"({local_count} locales, {len(items)-local_count-intl_count} N/A, {intl_count} internationales)")
    return items


# ── Étape 1b : Bulletin météo (Open-Meteo, sans clé) ─────────────────────────

def _rain_label(mm: float) -> str:
    if mm < 0.2:  return "pas de pluie"
    if mm < 2:    return "quelques gouttes"
    if mm < 8:    return "averses légères"
    if mm < 20:   return "averses modérées"
    if mm < 40:   return "fortes pluies"
    return "très fortes pluies"

def _wind_label(kmh: float) -> str:
    if kmh < 15:  return "vent faible"
    if kmh < 30:  return "brise"
    if kmh < 50:  return "vent modéré"
    if kmh < 70:  return "vent fort"
    return "vent très fort"


def generate_hashtags(items: list[dict]) -> list[list[str]]:
    """
    Génère HASHTAG_COUNT hashtags pertinents par article via un seul appel Mistral.
    Retourne une liste de listes de hashtags dans le même ordre que items.
    """
    if not items:
        return []
    articles_json = json.dumps(
        [{"titre": it["title"], "desc": it["desc"], "categorie": it.get("category", "")}
         for it in items],
        ensure_ascii=False,
    )
    prompt = (
        f"Tu es un expert en social media pour l'actualité du frein.\n"
        f"Pour chaque article ci-dessous, génère exactement {HASHTAG_COUNT} hashtags "
        f"Réponds UNIQUEMENT avec un tableau JSON de tableaux de strings, "
        f"dans le même ordre que les articles. Exemple : "
        f'[[\"#Haiti\",\"#Caraibes\"],[\"#Sport\",\"#Guadeloupe\"]].\n\n'
        f"Articles :\n{articles_json}"
    )
    raw = call_mistral(
        system="Tu es un assistant JSON strict. Réponds uniquement avec du JSON valide.",
        user=prompt,
        json_mode=True,
        max_tokens=500,
    )
    try:
        result = json.loads(raw)
        # Normalise : s'assure qu'on a bien une liste de listes
        return [
            [h if h.startswith("#") else f"#{h}" for h in row][:HASHTAG_COUNT]
            if isinstance(row, list) else []
            for row in result
        ]
    except (json.JSONDecodeError, ValueError):
        print("   ⚠️  Hashtags : réponse JSON invalide, hashtags ignorés")
        return [[] for _ in items]


def fetch_weather(target_date: Date) -> str:
    """Retourne un résumé météo pour Pointe-à-Pitre à la date donnée."""
    print("🌤️  Collecte météo (Open-Meteo)...")
    today = Date.today()
    delta = (target_date - today).days

    if delta > WEATHER_FORECAST_DAYS:
        print(f"   ⚠️  Date trop éloignée ({delta}j) — météo indisponible, message générique utilisé.")
        return "Météo indisponible pour cette date (prévision hors fenêtre)."

    date_iso = target_date.isoformat()
    api_url = WEATHER_API_ARCHIVE if delta < 0 else WEATHER_API
    params = urllib.parse.urlencode({
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode,windspeed_10m_max",
        "timezone": "America/Guadeloupe",
        "start_date": date_iso,
        "end_date": date_iso,
    })
    try:
        with urllib.request.urlopen(f"{api_url}?{params}", timeout=15) as r:
            data = json.loads(r.read())
    except Exception as exc:
        print(f"   ⚠️  Météo indisponible : {exc}")
        return "Météo indisponible pour cette date."

    daily  = data["daily"]
    code   = daily["weathercode"][0]
    t_max  = daily["temperature_2m_max"][0]
    t_min  = daily["temperature_2m_min"][0]
    rain   = daily["precipitation_sum"][0]
    wind   = daily["windspeed_10m_max"][0]

    cond      = _WMO.get(code, "temps variable")
    summary   = (
        f"{cond}, {t_min:.0f}°C / {t_max:.0f}°C, "
        f"{_wind_label(wind)}, {_rain_label(rain)}."
    )
    print(f"   {summary}")
    return summary


# ── Horoscope ────────────────────────────────────────────────────────────────

HOROSCOPE_API = "https://freehoroscopeapi.com/api/v1/get-horoscope/daily"

_SIGNS = [
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
]
_SIGN_FR = {
    "aries": "Bélier", "taurus": "Taureau", "gemini": "Gémeaux",
    "cancer": "Cancer", "leo": "Lion", "virgo": "Vierge",
    "libra": "Balance", "scorpio": "Scorpion", "sagittarius": "Sagittaire",
    "capricorn": "Capricorne", "aquarius": "Verseau", "pisces": "Poissons",
}
# Lookup inverse : nom français (minuscules) → clé anglaise
_SIGN_FR_TO_EN = {v.lower(): k for k, v in _SIGN_FR.items()}


def _resolve_sign(name: str) -> str | None:
    """Convertit un nom de signe (fr ou en, casse libre) en clé anglaise, ou None si inconnu."""
    key = name.strip().lower()
    if key in _SIGNS:
        return key
    return _SIGN_FR_TO_EN.get(key)


def _sign_for_date(d: Date) -> str:
    """Retourne la clé anglaise du signe zodiacal correspondant à la date."""
    m, day = d.month, d.day
    if (m == 3 and day >= 21) or (m == 4 and day <= 19): return "aries"
    if (m == 4 and day >= 20) or (m == 5 and day <= 20): return "taurus"
    if (m == 5 and day >= 21) or (m == 6 and day <= 20): return "gemini"
    if (m == 6 and day >= 21) or (m == 7 and day <= 22): return "cancer"
    if (m == 7 and day >= 23) or (m == 8 and day <= 22): return "leo"
    if (m == 8 and day >= 23) or (m == 9 and day <= 22): return "virgo"
    if (m == 9 and day >= 23) or (m == 10 and day <= 22): return "libra"
    if (m == 10 and day >= 23) or (m == 11 and day <= 21): return "scorpio"
    if (m == 11 and day >= 22) or (m == 12 and day <= 21): return "sagittarius"
    if (m == 12 and day >= 22) or (m == 1 and day <= 19): return "capricorn"
    if (m == 1 and day >= 20) or (m == 2 and day <= 18): return "aquarius"
    return "pisces"


def fetch_horoscope(n_signs: int = 2, include_signs: "list[str] | None" = None) -> "tuple[str, list[str]] | None":
    """Retourne (texte, signes_fr) pour n_signs signes aléatoires, ou None si l'API est indisponible.

    include_signs : liste de clés anglaises à inclure de force ; les slots restants sont tirés au hasard.
    """
    forced = list(dict.fromkeys(include_signs or []))  # dédoublonnage, ordre conservé
    pool = [s for s in _SIGNS if s not in forced]
    n_random = max(0, n_signs - len(forced))
    signs = forced + random.sample(pool, min(n_random, len(pool)))
    print(f"🔮  Collecte horoscope ({len(signs)} signe{'s' if len(signs) > 1 else ''}" +
          (f", dont {', '.join(_SIGN_FR[s] for s in forced)} imposé{'s' if len(forced) > 1 else ''}" if forced else "") + ")...")
    entries, signs_fr = [], []
    for sign in signs:
        try:
            qs = urllib.parse.urlencode({"sign": sign})
            req = urllib.request.Request(
                f"{HOROSCOPE_API}?{qs}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; FlashInfoKarukera/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            text = (
                data.get("horoscope")
                or data.get("data", {}).get("horoscope", "")
                or data.get("description", "")
            )
            if text:
                entries.append(f"{_SIGN_FR[sign]} ({sign.capitalize()}) : {text}")
                signs_fr.append(_SIGN_FR[sign])
                print(f"   {_SIGN_FR[sign]} ✅")
        except Exception as e:
            print(f"   ⚠️  Horoscope {sign} : {e}")
    if not entries:
        print("   ⚠️  Horoscope indisponible — rubrique omise.")
        return None
    return "\n".join(entries), signs_fr


# ── Étape 2 : Segments rédigés par Maryse via Mistral ────────────────────────

MISTRAL_CHAT_MODEL = "mistral-large-latest"
MISTRAL_CHAT_URL   = "https://api.mistral.ai/v1/chat/completions"
SEG_SEPARATOR      = "<<<SEG>>>"


def call_mistral(
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 1500,
    json_mode: bool = False,
    timeout: int = 60,
    _retries: int = 4,
) -> str:
    """Appelle Mistral chat completions avec retry exponentiel sur 429."""
    import time
    payload: dict = {
        "model": MISTRAL_CHAT_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        MISTRAL_CHAT_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    for attempt in range(_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                result = json.loads(r.read())
            return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < _retries:
                wait = 15 * 2 ** attempt
                print(f"   ⏳ Mistral {e.code} — attente {wait}s (tentative {attempt + 1}/{_retries})…")
                time.sleep(wait)
            else:
                raise
        except (TimeoutError, OSError) as e:
            if attempt < _retries:
                wait = 15 * 2 ** attempt
                print(f"   ⏳ Mistral timeout réseau — attente {wait}s (tentative {attempt + 1}/{_retries})…")
                time.sleep(wait)
            else:
                raise


MARYSE_SYSTEM        = _load_prompt("maryse_ame.md") + "\n\n" + _load_prompt("maryse.md")
PRENOM_TEMPLATE      = _load_prompt("prenom.md")
HOROSCOPE_TEMPLATE   = _load_prompt("horoscope.md")
LIEUX_SPIRITUELS     = (
    "\n\n" + _load_prompt("lieux_spirituels.md") +
    "\n\n" + _load_prompt("flore_guadeloupe.md") +
    "\n\n" + _load_prompt("faune_guadeloupe.md")
)


def _strip_markdown(text: str) -> str:
    import re
    text = re.sub(r"\*+([^*]+)\*+", r"\1", text)
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"^\s*[-#>]+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Prénom du jour ────────────────────────────────────────────────────────────

NOMINIS_API = "https://nominis.cef.fr/json/nominis.php"

def get_communes_du_jour(target_date: "Date") -> list[str]:
    """Retourne les communes de Guadeloupe fêtant leur fête patronale à la date donnée."""
    key = target_date.strftime("%m-%d")
    return _COMMUNES_FETES_PATRONALES.get(key, [])


def fetch_prenom_du_jour(target_date: "datetime.date") -> "list[str] | None":
    """Retourne la liste des prénoms fêtés à la date donnée, ou None si l'API est indisponible."""
    date_label = _date_fr(target_date)
    print(f"🎂  Collecte prénoms du {date_label} (nominis.cef.fr)...")
    try:
        qs = urllib.parse.urlencode({
            "jour":   target_date.day,
            "mois":   target_date.month,
            "année":  target_date.year,
        })
        req = urllib.request.Request(
            f"{NOMINIS_API}?{qs}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; FlashInfoKarukera/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        prenoms = list(data.get("response", {}).get("prenoms", {}).get("majeurs", {}).keys())
        if prenoms:
            print(f"   Prénoms du {date_label} : {', '.join(prenoms)}")
            return prenoms
        print(f"   ⚠️  Aucun prénom trouvé pour le {date_label}")
        return None
    except Exception as exc:
        print(f"   ⚠️  Impossible de récupérer les prénoms du {date_label} : {exc}")
        return None


def build_segments(
    items: list[dict], date_str: str, weather: "str | None", sources: list[str],
    horoscope: str | None = None,
    horoscope_signs: "list[str] | None" = None,
    prenoms_du_jour: "list[str] | None" = None,
    communes_du_jour: "list[str] | None" = None,
    marroniers_du_jour: "list | None" = None,
    edition: str = "matin",
    weather_label: str = "MÉTÉO DU JOUR",
    tomorrow_str: "str | None" = None,
    heure_paris: "str | None" = None,
    verbose: bool = False,
) -> list[str]:
    print(f"✍️  Rédaction des segments par Maryse — édition {edition.upper()} (Mistral Large)...")
    articles = "\n\n".join(
        f"[{i+1}] {item['title']}\n{item['desc']}" for i, item in enumerate(items)
    )
    has_meteo     = weather is not None
    has_horoscope = horoscope is not None
    has_prenom    = bool(prenoms_du_jour)

    # Calcul dynamique des indices (1-based dans le prompt LLM)
    _idx = 1  # INTRO = segment 1
    prenom_seg = horoscope_seg = meteo_seg = None
    if has_prenom:
        _idx += 1; prenom_seg = _idx
    if has_meteo:
        _idx += 1; meteo_seg = _idx
    if has_horoscope:
        _idx += 1; horoscope_seg = _idx
    news_offset = _idx + 1  # premier segment d'actu (1-based)

    sources_str = " et ".join(sources) if sources else "les médias locaux"
    base_segs = 2 + (1 if has_prenom else 0) + (1 if has_meteo else 0) + (1 if has_horoscope else 0)

    salut, rdv = _EDITION_OUTRO[edition]
    if items:
        n_segs = len(items) + base_segs
        news_block = f"Voici les {len(items)} actualités du jour :\n\n{articles}\n\n"
        outro_template = (
            f"Voilà pour ce Flash Info Guadeloupe du {date_str}. "
            f"Sources : {sources_str}. "
            f"On se retrouve {rdv}. "
            f"{salut} à toutes et à tous."
        )
        news_instructions = (
            f"- Segments {news_offset} à {len(items) + news_offset - 1} : "
            f"un seul sujet par segment, 60 à 90 mots chacun.\n"
            f"- Segment {n_segs} : outro. Recopie ce modèle en remplaçant uniquement "
            f"[prochain rendez-vous] :\n  \"{outro_template}\""
        )
    else:
        n_segs = base_segs
        news_block = ""
        outro_template = (
            f"Voilà pour ce Flash Info Guadeloupe du {date_str}. "
            f"Sources : {sources_str}. "
            f"On se retrouve {rdv}. "
            f"{salut} à toutes et à tous."
        )
        news_instructions = (
            f"- Segment {n_segs} : outro. Recopie ce modèle en remplaçant uniquement "
            f"[prochain rendez-vous] :\n  \"{outro_template}\""
        )

    prenom_instruction = ""
    if has_prenom:
        prenoms_str = " et ".join(prenoms_du_jour)
        is_demain = edition == "soir"
        communes_mention = (
            f" Mentionne aussi la fête patronale de {' et '.join(communes_du_jour)}."
            if communes_du_jour else ""
        )
        prenom_instruction = PRENOM_TEMPLATE.format(
            segment=prenom_seg,
            prenoms=prenoms_str,
            communes_mention=communes_mention,
            demain_context=" de demain" if is_demain else "",
        )

    horoscope_block = ""
    horoscope_instruction = ""
    if has_horoscope:
        n_signs = len(horoscope_signs) if horoscope_signs else 2
        horoscope_block = f"HOROSCOPE DU JOUR ({n_signs} signe{'s' if n_signs > 1 else ''} tiré{'s' if n_signs > 1 else ''} au hasard) :\n{horoscope}\n\n"
        horoscope_instruction = HOROSCOPE_TEMPLATE.format(
            segment=horoscope_seg,
            n_signs=n_signs,
            s="s" if n_signs > 1 else "",
            lieux_spirituels=LIEUX_SPIRITUELS,
            contexte_local="",
        )

    prenoms_block = ""
    if has_prenom:
        label_prenom = "PRÉNOM DE DEMAIN" if edition == "soir" else "PRÉNOM DU JOUR"
        prenoms_block = f"{label_prenom} : {' et '.join(prenoms_du_jour)}\n\n"

    communes_block = ""
    if communes_du_jour:
        communes_block = f"FÊTE PATRONALE DU JOUR : {' et '.join(communes_du_jour)}\n\n"

    marroniers_block = ""
    if marroniers_du_jour:
        lignes = "\n".join(
            f"- {m.evenement} ({m.lieu})" for m in marroniers_du_jour
        )
        marroniers_block = f"ÉVÉNEMENTS RÉCURRENTS DU JOUR (marroniers) :\n{lignes}\n\nTu peux mentionner ces événements dans l'intro ou dans un segment d'actualité si cela enrichit le flash, mais sans les inventer ni les développer au-delà de ce qui est indiqué.\n\n"

    meteo_block = ""
    meteo_instruction = ""
    if has_meteo:
        label_detail = f"prévisions pour demain {tomorrow_str}" if tomorrow_str else "toute la Guadeloupe"
        meteo_block = f"{weather_label} ({label_detail}) :\n{weather}\n\n"
        meteo_instr_text = (
            "prévisions météo de demain en style oral — prépare les auditeurs pour la journée de demain"
            if edition == "soir" else "météo du jour en style oral"
        )
        meteo_instruction = f"- Segment {meteo_seg} : {meteo_instr_text}\n"

    edition_instruction = _EDITION_INTRO_INSTRUCTION[edition]

    heure_ctx = f" — il est {heure_paris} à Paris" if heure_paris else ""
    user_prompt = (
        f"Flash info Guadeloupe du {date_str}{heure_ctx} — {edition_instruction}\n\n"
        f"{meteo_block}"
        f"{prenoms_block}"
        f"{communes_block}"
        f"{marroniers_block}"
        f"{horoscope_block}"
        f"{news_block}"
        f"Rédige exactement {n_segs} segments séparés par \"{SEG_SEPARATOR}\" :\n"
        f"- Segment 1 : intro (jour + date + accroche)\n"
        f"{prenom_instruction}"
        f"{meteo_instruction}"
        f"{horoscope_instruction}"
        f"{news_instructions}"
    )
    if verbose:
        print("\n══════════════════════════════════════════════════════════")
        print("  VERBOSE — PROMPT MARYSE (system)")
        print("══════════════════════════════════════════════════════════")
        print(MARYSE_SYSTEM)
        print("\n  ── user_prompt ──")
        print(user_prompt)
        print("══════════════════════════════════════════════════════════\n")
    _horoscope_tokens = 150 * (len(horoscope_signs) if horoscope_signs else 2) if has_horoscope else 0
    _base_tokens = 1400 if (has_prenom or has_meteo) else 1200
    raw = call_mistral(MARYSE_SYSTEM, user_prompt, temperature=0.75, max_tokens=_base_tokens + _horoscope_tokens)

    import re as _re
    segments = [_strip_markdown(s) for s in raw.split(SEG_SEPARATOR) if s.strip()]

    # Fallback : Mistral a utilisé "---" (markdown) à la place du séparateur imposé
    if len(segments) < 2:
        print("   ⚠️  Séparateur <<<SEG>>> non trouvé — tentative de fallback sur '---'")
        segments = [_strip_markdown(s) for s in _re.split(r"\n\s*---+\s*\n", raw) if s.strip()]

    if len(segments) < 2:
        print("   ⚠️  Fallback échoué — réponse brute Mistral :")
        print(raw[:500])

    print(f"   {len(segments)} segments générés")
    return segments


# ── Étape 2b : Réviseur stylistique ──────────────────────────────────────────

STYLIST_SYSTEM = _load_prompt("styliste.md")


ANCHOR_SYSTEM = _load_prompt("ancrage.md")


def anchor_local(segments: list[str], items: list[dict], verbose: bool = False) -> list[str]:
    print("📍 Ancrage local (Mistral Large)...")
    full_script = f"\n{SEG_SEPARATOR}\n".join(segments)
    json_context = json.dumps(
        [
            {
                "titre": it["title"],
                "lieu": it.get("lieu", "N/A"),
                "source": it["source"],
                "description": it["desc"],
            }
            for it in items
        ],
        ensure_ascii=False, indent=2
    )
    user_prompt = (
        f"SCRIPT_INITIAL :\n{full_script}\n\n"
        f"JSON_EXTRACTION :\n{json_context}"
    )
    if verbose:
        print("\n══════════════════════════════════════════════════════════")
        print("  VERBOSE — PROMPT ANCRAGE LOCAL (system)")
        print("══════════════════════════════════════════════════════════")
        print(ANCHOR_SYSTEM)
        print("\n  ── user_prompt ──")
        print(user_prompt)
        print("══════════════════════════════════════════════════════════\n")
    raw = call_mistral(ANCHOR_SYSTEM, user_prompt)
    # Supprime tout préambule que le LLM ajoute avant le script (ex. "SCRIPT_ENRICHI :", "Voici le script...")
    raw = re.sub(r'(?im)^(?:script_\w+\s*:|voici\s+le\s+script\b)[^\n]*\n', '', raw.lstrip())
    anchored = [_strip_markdown(s) for s in raw.split(SEG_SEPARATOR) if s.strip()]

    if len(anchored) != len(segments):
        print(f"   ⚠️  Ancrage retourné {len(anchored)} segments au lieu de {len(segments)} — fallback sur l'original")
        return segments

    print(f"   Ancrage appliqué ({len(anchored)} segments)")
    return anchored


def _enforce_prononciations(segments: list[str]) -> list[str]:
    """Applique _PRONONCIATIONS_LOCALES sur chaque segment.
    - Insensible à la casse (Unar, unar, UNAR → même résultat)
    - Normalise les apostrophes typographiques avant matching
    - Word-boundary pour éviter les remplacements partiels
    """
    import re
    result = []
    for seg in segments:
        # Normalise apostrophes typographiques pour que \b fonctionne correctement
        seg = seg.replace("\u2019", "'").replace("\u2018", "'")
        for ecrit, oral in _PRONONCIATIONS_LOCALES.items():
            seg = re.sub(r"\b" + re.escape(ecrit) + r"\b", oral, seg, flags=re.IGNORECASE)
        result.append(seg)
    return result


def _ensure_sources_in_outro(segments: list[str], sources: list[str]) -> list[str]:
    """Injecte 'Sources : X et Y.' dans l'outro si le modèle l'a omis."""
    if not segments:
        return segments
    outro = segments[-1]
    if "Sources :" not in outro and sources:
        import re
        sources_str = " et ".join(sources)
        outro = re.sub(
            r"(Voilà pour ce Flash Info Guadeloupe[^.]*\.)",
            rf"\1 Sources : {sources_str}.",
            outro,
            count=1,
        )
        segments = segments[:-1] + [outro]
    return segments


def revise_style(segments: list[str], verbose: bool = False) -> list[str]:
    print("✏️  Révision stylistique (Mistral Large)...")
    full_script = f"\n{SEG_SEPARATOR}\n".join(segments)
    if verbose:
        print("\n══════════════════════════════════════════════════════════")
        print("  VERBOSE — PROMPT RÉVISEUR STYLISTIQUE (system)")
        print("══════════════════════════════════════════════════════════")
        print(STYLIST_SYSTEM)
        print("\n  ── user_prompt (script) ──")
        print(full_script)
        print("══════════════════════════════════════════════════════════\n")
    raw = call_mistral(STYLIST_SYSTEM, full_script)
    raw = re.sub(r'(?im)^(?:script_\w+\s*:|voici\s+le\s+script\b)[^\n]*\n', '', raw.lstrip())
    revised = [_strip_markdown(s) for s in raw.split(SEG_SEPARATOR) if s.strip()]

    if len(revised) != len(segments):
        print(f"   ⚠️  Réviseur a retourné {len(revised)} segments au lieu de {len(segments)} — fallback sur l'original")
        return segments

    print(f"   Révision appliquée ({len(revised)} segments)")
    return revised


# ── Étape 2d : Classification émotionnelle par segment ───────────────────────

TONE_SYSTEM = _load_prompt("tones.md")


def classify_tones(segments: list[str]) -> list[str]:
    """Retourne une liste de tags émotionnels, un par segment."""
    print("🎭 Classification tonale (Mistral Large)...")
    numbered = [{"idx": i, "text": s} for i, s in enumerate(segments)]
    user_payload = json.dumps({"segments": numbered}, ensure_ascii=False)
    try:
        raw = call_mistral(
            TONE_SYSTEM, user_payload,
            temperature=0.1, max_tokens=300, json_mode=True,
        )
        parsed = json.loads(raw)
        tones = parsed if isinstance(parsed, list) else parsed.get("tones") or parsed.get("tags") or next(iter(parsed.values()))
        tones = [t if t in TTS_VOICES else "neutral" for t in tones]
        if len(tones) != len(segments):
            raise ValueError(f"length mismatch: got {len(tones)} for {len(segments)} segments")
    except Exception as e:
        print(f"   ⚠️  Classification échouée ({e}) — fallback sur 'neutral' partout")
        tones = ["neutral"] * len(segments)

    for i, (tag, seg) in enumerate(zip(tones, segments)):
        preview = seg[:60].replace("\n", " ")
        print(f"   [{i+1}/{len(segments)}] {tag:8s} → {preview}…")
    return tones


# ── Étape 3 : Génération audio TTS par segment + assemblage FFmpeg ────────────

import re as _re

try:
    from num2words import num2words as _n2w

    def _num_fr(n: str) -> str:
        s = n.replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            return _n2w(float(s) if "." in s else int(s), lang="fr")
        except Exception:
            return n

    def _ordinal_fr(n: str) -> str:
        try:
            return _n2w(int(n), lang="fr", to="ordinal")
        except Exception:
            return n
except ImportError:
    print("   ⚠️  num2words manquant — pip install num2words")
    def _num_fr(n: str) -> str: return n
    def _ordinal_fr(n: str) -> str: return n


_DOM_CODES = {
    "971": "quatre-vingt-dix-sept-un",
    "972": "quatre-vingt-dix-sept-deux",
    "973": "quatre-vingt-dix-sept-trois",
    "974": "quatre-vingt-dix-sept-quatre",
    "976": "quatre-vingt-dix-sept-six",
}

_UNIT_PATTERNS = [
    (r"(\d+(?:[,\.]\d+)?)\s*°C",   lambda m: f"{_num_fr(m.group(1))} degrés"),
    (r"(\d+(?:[,\.]\d+)?)\s*km/h", lambda m: f"{_num_fr(m.group(1))} kilomètres par heure"),
    (r"(\d+(?:[,\.]\d+)?)\s*km\b", lambda m: f"{_num_fr(m.group(1))} kilomètres"),
    (r"(\d+(?:[,\.]\d+)?)\s*mm\b", lambda m: f"{_num_fr(m.group(1))} millimètres"),
    (r"(\d+(?:[,\.]\d+)?)\s*%",    lambda m: f"{_num_fr(m.group(1))} pour cent"),
    (r"(\d+(?:[,\.]\d+)?)\s*m²",   lambda m: f"{_num_fr(m.group(1))} mètres carrés"),
]


def _norm_pronunciations(text: str) -> str:
    """Applique les prononciations locales guadeloupéennes (Lyannaj → Lyan naje, etc.)."""
    for ecrit, oral in _PRONONCIATIONS_LOCALES.items():
        text = _re.sub(r"\b" + _re.escape(ecrit) + r"\b", oral, text)
    return text


def _norm_typography(text: str) -> str:
    """Normalise apostrophes/guillemets typographiques et supprime les emojis."""
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", " ")
    return _re.sub(r"[^\x00-\x7F\u00C0-\u024F\u1E00-\u1EFF\n]", " ", text)


def _norm_numero(text: str) -> str:
    """n° / N° → numéro / Numéro."""
    text = _re.sub(r"\bn°\s*", "numéro ", text, flags=_re.IGNORECASE)
    text = _re.sub(r"\bN°\s*", "Numéro ", text)
    return text


def _norm_ordinals(text: str) -> str:
    """1er/1re → premier/première, 2e/2ème → deuxième…"""
    text = _re.sub(r"\b1er\b", "premier", text)
    text = _re.sub(r"\b1re\b", "première", text)
    return _re.sub(r"\b(\d+)(?:e|ème|eme)\b",
                   lambda m: _ordinal_fr(m.group(1)), text)


def _norm_currencies(text: str) -> str:
    """3,5M€ → millions d'euros ; 15€ → euros ; 20$ → dollars."""
    text = _re.sub(r"(\d+(?:[,\.]\d+)?)\s*[Mm](?:illions?)?\s*€",
                   lambda m: f"{_num_fr(m.group(1))} millions d'euros", text)
    text = _re.sub(r"(\d+(?:[,\.]\d+)?)\s*€",
                   lambda m: f"{_num_fr(m.group(1))} euros", text)
    text = _re.sub(r"(\d+(?:[,\.]\d+)?)\s*\$",
                   lambda m: f"{_num_fr(m.group(1))} dollars", text)
    return text


def _norm_scores(text: str) -> str:
    """Scores sportifs : 3-1 → trois à un."""
    return _re.sub(r"\b(\d+)-(\d+)\b",
                   lambda m: f"{_num_fr(m.group(1))} à {_num_fr(m.group(2))}", text)


def _norm_dom_codes(text: str) -> str:
    """Codes DOM 971-976 → lecture spécifique."""
    for code, spoken in _DOM_CODES.items():
        text = _re.sub(r"\b" + code + r"\b", spoken, text)
    return text


def _norm_hours(text: str) -> str:
    """07h30 → sept heures trente."""
    return _re.sub(
        r"\b(\d{1,2})h(\d{2})\b",
        lambda m: f"{_num_fr(m.group(1))} heures {_num_fr(m.group(2))}",
        text,
    )


def _norm_units(text: str) -> str:
    """Nombres avec unités : 25°C, 80km/h, 10mm, 50%, m²…"""
    for pattern, repl in _UNIT_PATTERNS:
        text = _re.sub(pattern, repl, text, flags=_re.IGNORECASE)
    return text


def _norm_plain_numbers(text: str) -> str:
    """Nombres isolés restants → texte."""
    return _re.sub(r"\b(\d[\d ]*(?:[,\.]\d+)?)\b",
                   lambda m: _num_fr(m.group(1)), text)


def _norm_acronyms(text: str) -> str:
    """Sigles : R.C.I → RCI ; S.D.I.S → S. D. I. S. ; CHU → C. H. U. (sauf _SIGLES_MOT)."""
    # 9a. Sigles prononcés comme des mots (R.C.I → RCI) avant épellation
    for sm in _SIGLES_MOT:
        dotted = ".".join(sm)
        text = text.replace(dotted + ".", sm).replace(dotted, sm)
    # 9b. Sigles avec points collés
    text = _re.sub(
        r"\b([A-Z](?:\.[A-Z]){1,4})\.?\b",
        lambda m: m.group(1).replace(".", ". ") + ".",
        text,
    )
    # 9c. Sigles tout-majuscules sans points (2-5 lettres)
    return _re.sub(
        r"\b([A-Z]{2,5})\b",
        lambda m: m.group(1) if m.group(1) in _SIGLES_MOT else ". ".join(m.group(1)) + ".",
        text,
    )


def _norm_abbreviations(text: str) -> str:
    """Abréviations textuelles (M. → Monsieur, etc.)."""
    for abbr, full in _ABBREVS.items():
        if abbr[0].isalpha():
            escaped = _re.escape(abbr)
            # trailing \b seulement si l'abréviation finit par un caractère de mot
            pattern = r"\b" + escaped + (r"\b" if abbr[-1].isalnum() else "")
            text = _re.sub(pattern, full, text)
        else:
            text = text.replace(abbr, full)
    return text


def _norm_honorifics(text: str) -> str:
    """Me devant un nom propre → Maître."""
    return _re.sub(r"\bMe\b(?=\s+[A-ZÀÂÉÈÊËÎÏÔÙÛÜ])", "Maître", text)


def _norm_residual(text: str) -> str:
    """Caractères spéciaux résiduels et whitespace."""
    text = _re.sub(r"[#*\[\]_~`|\\^@]", " ", text)
    text = _re.sub(r"/", " sur ", text)
    text = _re.sub(r" {2,}", " ", text)
    text = _re.sub(r"\n{2,}", "\n", text)
    return text


_NORMALIZATION_PIPELINE = (
    _norm_pronunciations,
    _norm_typography,
    _norm_numero,
    _norm_ordinals,
    _norm_currencies,
    _norm_scores,
    _norm_dom_codes,
    _norm_hours,
    _norm_units,
    _norm_plain_numbers,
    _norm_acronyms,
    _norm_abbreviations,
    _norm_honorifics,
    _norm_residual,
)


def _normalize_for_tts(text: str) -> str:
    for step in _NORMALIZATION_PIPELINE:
        text = step(text)
    return text.strip()


def _tts_call(text: str, output_path: Path, voice_id: str = TTS_VOICE_DEFAULT) -> None:

    payload = json.dumps({
        "input": text,
        "model": TTS_MODEL,
        "response_format": "mp3",
        "voice_id": voice_id,
    }).encode()
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/audio/speech",
        data=payload,
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        response = json.loads(r.read())
    if "audio_data" not in response:
        raise RuntimeError(f"TTS error: {response}")
    
    # Assurez-vous que output_path est un Path
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)  # Crée le répertoire parent s'il n'existe pas
    output_path.write_bytes(base64.b64decode(response["audio_data"]))

    output_path.write_bytes(base64.b64decode(response["audio_data"]))


def resolve_stinger(name: str | None) -> Path:
    """Résout le stinger à utiliser : depuis STINGERS_DIR ou génère un synthétique."""
    STINGERS_DIR.mkdir(exist_ok=True)
    available = sorted(STINGERS_DIR.glob("*.mp3")) + sorted(STINGERS_DIR.glob("*.wav"))

    if name:
        candidate = STINGERS_DIR / name
        if not candidate.exists():
            # Essayer comme chemin absolu
            candidate = Path(name)
        if not candidate.exists():
            avail_names = [f.name for f in available]
            raise FileNotFoundError(
                f"Stinger '{name}' introuvable dans {STINGERS_DIR}.\n"
                f"Disponibles : {', '.join(avail_names) or '(aucun)'}"
            )
        return candidate

    if available:
        chosen = available[0]
        print(f"🎵 Stinger : {chosen.name}  (utilisez --stinger pour choisir parmi : {', '.join(f.name for f in available)})")
        return chosen

    # Aucun fichier → génération synthétique
    synthetic = STINGERS_DIR / "stinger_synthetique.mp3"
    print("🎵 Génération du stinger goutte d'eau (synthétique)...")
    expr = "0.55*sin(2*PI*(900-700*t)*t)*exp(-t*14)+0.3*sin(2*PI*(450-350*t)*t)*exp(-t*10)"
    proc = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"aevalsrc={expr}:s=44100:d=0.5",
        "-af", "afade=t=out:st=0.3:d=0.2",
        "-c:a", "libmp3lame", "-q:a", "4",
        str(synthetic),
    ], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg stinger error: {proc.stderr.decode()}")
    return synthetic


def generate_audio(
    segments: list[str],
    output_path: Path,
    stinger: Path,
    tones: list[str] | None = None,
    keep_segments: bool = False,
) -> tuple[Path, list[Path]]:
    """Génère un MP3 par segment, insère le stinger entre chaque, concatène."""
    print(f"🔊 Génération TTS : {len(segments)} segments...")
    tmp_dir = output_path.parent
    seg_paths: list[Path] = []

    if tones is None or len(tones) != len(segments):
        tones = ["neutral"] * len(segments)

    for i, (text, tone) in enumerate(zip(segments, tones)):
        seg_path = tmp_dir / f"_seg_{i:02d}.mp3"
        voice_id = TTS_VOICES.get(tone, TTS_VOICE_DEFAULT)
        word_count = len(text.split())
        if word_count > 300:
            print(f"   ⚠️  Segment {i+1} : {word_count} mots > 300 (Voxtral recommande < 300 mots par appel)")
        print(f"   [{i+1}/{len(segments)}] TTS segment ({tone} → {voice_id}, {word_count} mots)…")
        _tts_call(_normalize_for_tts(text), seg_path, voice_id=voice_id)
        # Léger padding pour éviter la troncature TTS en fin de segment
        padded = tmp_dir / f"_seg_{i:02d}_p.mp3"
        proc = subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(seg_path),
            "-af", "apad=pad_dur=0.15",
            "-c:a", "libmp3lame", "-q:a", "2",
            str(padded),
        ], capture_output=True)
        if proc.returncode == 0:
            seg_path.unlink()
            seg_path = padded
        seg_paths.append(seg_path)

    # Assemblage via filter_complex concat — gère les différences de format
    # (fréquence, mono/stéréo) entre segments TTS et stinger
    all_files: list[Path] = []
    for i, sp in enumerate(seg_paths):
        all_files.append(sp)
        if i < len(seg_paths) - 1:
            all_files.append(stinger)

    inputs = []
    for f in all_files:
        inputs += ["-i", str(f)]

    n = len(all_files)
    filter_str = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"

    print("   🔗 Assemblage FFmpeg…")
    proc = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        *inputs,
        "-filter_complex", filter_str,
        "-map", "[out]",
        "-c:a", "libmp3lame", "-q:a", "2",
        str(output_path),
    ], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat error: {proc.stderr.decode()}")

    if not keep_segments:
        for sp in seg_paths:
            sp.unlink(missing_ok=True)

    print(f"   Fichier final : {output_path} ({output_path.stat().st_size:,} bytes)")
    return output_path, seg_paths if keep_segments else []


# ── Étape 3b : Transcription STT (optionnelle) ───────────────────────────────

def _mistral_stt(audio_path: Path, word_timestamps: bool = False) -> dict:
    """Appelle l'API STT Mistral et retourne le JSON brut."""
    boundary = "----TranscriptBoundary"
    audio_data = audio_path.read_bytes()

    fields = [("model", STT_MODEL)]
    if word_timestamps:
        fields.append(("timestamp_granularities", "word"))

    body = b""
    for name, value in fields:
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\n'
        f"Content-Type: audio/mpeg\r\n\r\n"
    ).encode() + audio_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        "https://api.mistral.ai/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    import time as _time
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                wait = 10 * 2 ** attempt
                print(f"   ⏳ STT 429 — attente {wait}s (tentative {attempt + 1}/5)…")
                _time.sleep(wait)
            else:
                body_err = e.read().decode(errors="replace")
                raise RuntimeError(f"STT HTTP {e.code}: {body_err}") from None


def transcribe_audio(audio_path: Path) -> str:
    return _mistral_stt(audio_path)["text"]


def transcribe_with_words(audio_path: Path) -> list[dict]:
    """Retourne [{word, start, end}, …] depuis les segments STT Voxtral."""
    segments = _mistral_stt(audio_path, word_timestamps=True).get("segments", [])
    return [
        {"word": s["text"].strip(), "start": s["start"], "end": s["end"]}
        for s in segments
        if s.get("text", "").strip()
    ]


# ── Étape 3c : Vidéos TikTok par segment ─────────────────────────────────────

TIKTOK_COLORS = {
    "neutral":  "#FFFFFF",
    "happy":    "#FFD700",
    "excited":  "#FF4500",
    "sad":      "#6495ED",
    "angry":    "#FF0000",
    "curious":  "#00CED1",
}

INTERSTITIAL_DURATION     = 2.5   # secondes
INTERSTITIAL_HT_FONTSIZE  = 110   # taille des hashtags dans l'interstitiel
INTERSTITIAL_CAT_FONTSIZE = 170   # taille du texte catégorie dans l'interstitiel

SUBTITLE_FONTSIZE  = 130    # taille du mot courant dans les sous-titres karaoke
TRIM_SILENCE       = False  # coupe le silence de fin TTS (deux passes FFmpeg, plus lent)

INTERSTITIAL_CTA          = "Si j'ai mal prononcé certains mots, dites-le moi en commentaire"
INTERSTITIAL_CTA_DURATION = 5.0  # secondes (texte long à lire)

# Mapping catégorie → (label affiché, couleur hex)
INTERSTITIAL_STYLES: dict[str, tuple[str, str]] = {
    "météo":        ("🌤  MÉTÉO",         "#4A90D9"),
    "prenom":       ("🎂 BONNE FÊTE",     "#E91E8C"),
    "horoscope":    ("HOROSCOPE",         "#6C3483"),
    "vie locale":   ("🏘  VIE LOCALE",    "#2ECC71"),
    "sports":       ("⚽ SPORTS",        "#FF6B00"),
    "social":       ("🤝 SOCIAL",        "#9B59B6"),
    "politique":    ("🏛  POLITIQUE",     "#E74C3C"),
    "economie":     ("💼 ÉCONOMIE",      "#F39C12"),
    "environement": ("🌿 ENVIRONNEMENT", "#27AE60"),
    "en bref":      ("📰 EN BREF",       "#1ABC9C"),
    "general":      ("📡 ACTUALITÉS",    "#95A5A6"),
    "custom":       ("🎙  FLASH INFO",    "#FFFFFF"),
}


def _ass_time(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h}:{m:02d}:{sec:05.2f}"


def _ass_color(hex_color: str) -> str:
    """#RRGGBB → &H00BBGGRR& (ordre canaux ASS)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"&H00{b:02X}{g:02X}{r:02X}&"


_FONT_BOLD    = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _make_interstitial(
    category: str, output_path: Path, stinger: Path,
    hashtags: list[str] | None = None,
    subtitle: str | None = None,
) -> Path:
    """Génère un MP4 interstitiel 1080×1920, durée et audio calés sur le stinger."""
    label, color = INTERSTITIAL_STYLES.get(category, INTERSTITIAL_STYLES["general"])
    color_hex = color.lstrip("#")
    duration = _stinger_duration(stinger)
    parts = label.split(" ", 1)
    text = parts[1] if len(parts) == 2 else parts[0]
    tmp = output_path.parent

    # ── Tailles de police adaptatives ──
    _MAX_PX          = 920   # largeur max utilisable (marges de 80px de chaque côté)
    _CHAR_RATIO_UPPER = 0.72  # majuscules DejaVu Bold (plus larges qu'estimé à 0.65)
    _CHAR_RATIO_MIXED = 0.60  # casse mixte (hashtags)

    # Catégorie : réduction si le texte est trop long
    cat_fontsize = min(INTERSTITIAL_CAT_FONTSIZE, int(_MAX_PX / (max(len(text), 1) * _CHAR_RATIO_UPPER)))
    cat_line_h   = round(cat_fontsize * 1.1)

    # Hashtags : réduction si le hashtag le plus long dépasse la largeur
    max_ht_len  = max((len(h) for h in (hashtags or [])), default=10)
    ht_fontsize = min(INTERSTITIAL_HT_FONTSIZE, int(_MAX_PX / (max_ht_len * _CHAR_RATIO_MIXED)))
    ht_line_h   = round(ht_fontsize * 1.3)
    ht_wrap     = max(6, int(_MAX_PX / (ht_fontsize * _CHAR_RATIO_MIXED)))

    ht_files: list[Path] = []
    if hashtags:
        words, lines, current = hashtags[:], [], ""
        for w in words:
            candidate = f"{current} {w}".strip()
            if len(candidate) <= ht_wrap:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        for i, line in enumerate(lines):
            f = tmp / f"inter_ht_{output_path.stem}_{i}.txt"
            f.write_text(line, encoding="utf-8")
            ht_files.append(f)

    # ── Layout vertical centré ──
    n_ht = len(ht_files)
    gap  = 70 if n_ht > 0 else 0
    block_h   = n_ht * ht_line_h + gap + cat_line_h
    ht_y_start = (1920 - block_h) // 2
    cat_y      = ht_y_start + n_ht * ht_line_h + gap
    wm_y       = cat_y + cat_line_h + 50

    filter_parts = [f"color=c=black:s=1080x1920:r=24:d={duration}"]
    for i, f in enumerate(ht_files):
        y = ht_y_start + i * ht_line_h
        filter_parts.append(
            f"drawtext=textfile={f}:fontsize={ht_fontsize}:fontcolor=0x{color_hex}:"
            f"fontfile={_FONT_BOLD}:x=(w-tw)/2:y={y}:"
            f"shadowcolor=black@0.6:shadowx=2:shadowy=2"
        )
    filter_parts.append(
        f"drawtext=text='{text}':"
        f"fontsize={cat_fontsize}:fontcolor=0x{color_hex}:fontfile={_FONT_BOLD}:"
        f"x=(w-tw)/2:y={cat_y}:"
        f"shadowcolor=black@0.6:shadowx=3:shadowy=3"
    )
    if subtitle:
        sub_fontsize = min(72, int(_MAX_PX / (max(len(subtitle), 1) * _CHAR_RATIO_MIXED)))
        sub_y = cat_y + cat_line_h + 30
        sub_file = tmp / f"inter_sub_{output_path.stem}.txt"
        sub_file.write_text(subtitle, encoding="utf-8")
        filter_parts.append(
            f"drawtext=textfile={sub_file}:"
            f"fontsize={sub_fontsize}:fontcolor=white:fontfile={_FONT_REGULAR}:"
            f"x=(w-tw)/2:y={sub_y}:"
            f"shadowcolor=black@0.5:shadowx=2:shadowy=2"
        )
        wm_y = sub_y + round(sub_fontsize * 1.2) + 30
    filter_parts.append(
        f"drawtext=text='Flash Info Karukera par @Botiran':"
        f"fontsize=38:fontcolor=white@0.5:fontfile={_FONT_REGULAR}:"
        f"x=(w-tw)/2:y={wm_y}"
    )
    filter_v = ",".join(filter_parts)

    proc = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", filter_v,
        "-i", str(stinger),
        "-c:v", "libx264", "-preset", "medium", "-crf", "28",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ], capture_output=True)
    for f in ht_files:
        f.unlink(missing_ok=True)
    if subtitle:
        sub_file.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg interstitiel error: {proc.stderr.decode()}")
    return output_path


def _make_cta_interstitial(output_path: Path, stinger: Path) -> Path:
    """Génère un MP4 de clôture avec le call-to-action INTERSTITIAL_CTA."""
    cta_text = INTERSTITIAL_CTA.rstrip().rstrip("👇").rstrip()
    duration = _stinger_duration(stinger)

    # Word-wrap : max ~20 caractères par ligne pour tenir dans 1080px à fontsize=62
    words = cta_text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= 20:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    # Écrit chaque ligne + le watermark dans des fichiers temporaires
    tmp = output_path.parent
    line_files = []
    for i, line in enumerate(lines):
        f = tmp / f"cta_line{i}.txt"
        f.write_text(line, encoding="utf-8")
        line_files.append(f)
    wm_file = tmp / "cta_watermark.txt"
    wm_file.write_text("Flash Info Karukera par Botiran", encoding="utf-8")

    # Centre le bloc de texte verticalement (ligne_height=80px)
    fontsize   = 62
    line_h     = 80
    block_h    = len(lines) * line_h
    y_start    = (1920 - block_h) // 2 - 40  # légèrement au-dessus du centre

    filter_parts = [
        f"color=c=black:s=1080x1920:r=24:d={duration}",
        f"drawbox=x=0:y=0:w=1080:h=1920:color=0x1A1A2E@1:t=fill",
    ]
    for i, f in enumerate(line_files):
        y = y_start + i * line_h
        filter_parts.append(
            f"drawtext=textfile={f}:fontsize={fontsize}:fontcolor=white:"
            f"fontfile={_FONT_BOLD}:x=(w-tw)/2:y={y}:"
            f"shadowcolor=black@0.6:shadowx=2:shadowy=2"
        )
    y_wm = y_start + len(lines) * line_h + 40
    filter_parts.append(
        f"drawtext=textfile={wm_file}:fontsize=36:fontcolor=white@0.4:"
        f"fontfile={_FONT_REGULAR}:x=(w-tw)/2:y={y_wm}"
    )
    filter_v = ",".join(filter_parts)

    proc = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", filter_v,
        "-i", str(stinger),
        "-c:v", "libx264", "-preset", "medium", "-crf", "28",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ], capture_output=True)
    for f in line_files:
        f.unlink(missing_ok=True)
    wm_file.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg CTA error: {proc.stderr.decode()}")
    return output_path


def _make_ass(words: list[dict], tone: str) -> str:
    """Génère un fichier ASS karaoke : mot courant coloré, précédent/suivant atténués."""
    tone_col = _ass_color(TIKTOK_COLORS.get(tone, "#FFFFFF"))
    dim_col  = "&H80FFFFFF&"

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 1\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial,{round(SUBTITLE_FONTSIZE * 0.74)},&H00FFFFFF,&H00FFFFFF,&H00000000,"
        "&HA0000000,0,0,0,0,100,100,0,0,1,5,2,5,80,80,0,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events = []
    for i, word in enumerate(words):
        start = word["start"]
        end   = max(word["end"], start + 0.05)
        parts = []
        fs_curr = SUBTITLE_FONTSIZE
        fs_adj  = round(SUBTITLE_FONTSIZE * 0.74)
        if i > 0:
            parts.append(f"{{\\c{dim_col}\\fs{fs_adj}}}{words[i - 1]['word']}")
        parts.append(f"{{\\c{tone_col}\\fs{fs_curr}\\b1}}{word['word']}{{\\b0}}")
        if i < len(words) - 1:
            parts.append(f"{{\\c{dim_col}\\fs{fs_adj}}}{words[i + 1]['word']}")
        # \an5 = centré horizontalement et verticalement dans la zone texte
        # \pos(540,1210) = centre horizontal, milieu de la zone sous le spectre (500px + 710px restants / 2)
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},"
            f"Default,,0,0,0,,{{\\an5\\pos(540,1210)}}{' '.join(parts)}"
        )

    return header + "\n".join(events) + "\n"


def _trim_silence(seg_path: Path) -> Path:
    """Passe 1 : supprime le silence de fin TTS, retourne un fichier MP3 temporaire."""
    trimmed = seg_path.with_suffix(".trimmed.mp3")
    proc = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(seg_path),
        "-af", "silenceremove=stop_periods=-1:stop_duration=0.2:stop_threshold=-45dB",
        "-c:a", "libmp3lame", "-q:a", "2",
        str(trimmed),
    ], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg trim error: {proc.stderr.decode()}")
    return trimmed


def _tiktok_segment_video(seg_path: Path, ass_path: Path, tone: str, output_path: Path) -> None:
    color_hex = TIKTOK_COLORS.get(tone, "#FFFFFF").lstrip("#")
    audio_path = _trim_silence(seg_path) if TRIM_SILENCE else seg_path
    filter_complex = (
        f"color=c=black:s=1080x1920:r=24[bg];"
        f"[0:a]showwaves=s=1080x500:mode=cline:colors=0x{color_hex}:scale=sqrt:rate=24[waves];"
        f"[bg][waves]overlay=0:0[v];"
        f"[v]ass={ass_path}[vout]"
    )
    proc = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(audio_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "28",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ], capture_output=True)
    if TRIM_SILENCE:
        audio_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg tiktok error: {proc.stderr.decode()}")


def generate_tiktok(
    seg_paths: list[Path],
    segments: list[str],
    tones: list[str],
    output_dir: Path,
    has_prenom: bool = False,
    has_horoscope: bool = False,
    has_meteo: bool = True,
) -> list[tuple[int, Path]]:
    """Retourne [(index_segment, chemin_mp4), …]."""
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"🎬 Génération vidéos : {len(seg_paths)} segments → {output_dir}")

    videos: list[tuple[int, Path]] = []
    for i, (seg_path, _text, tone) in enumerate(zip(seg_paths, segments, tones)):
        label = _seg_label(i, len(seg_paths), has_prenom=has_prenom, has_horoscope=has_horoscope, has_meteo=has_meteo)
        print(f"   [{i + 1}/{len(seg_paths)}] {label} ({tone}) — STT timestamps…")

        words = transcribe_with_words(seg_path)
        if not words:
            print(f"   ⚠️  STT sans mots pour le segment {i + 1} — ignoré")
            continue

        ass_path = output_dir / f"seg_{i:02d}.ass"
        ass_path.write_text(_make_ass(words, tone), encoding="utf-8")

        video_path = output_dir / f"seg_{i:02d}.mp4"
        print(f"   [{i + 1}/{len(seg_paths)}] FFmpeg → {video_path.name}…")
        _tiktok_segment_video(seg_path, ass_path, tone, video_path)
        videos.append((i, video_path))
        print(f"   ✅ {video_path.name} ({video_path.stat().st_size:,} bytes)")

    return videos


# ── Backblaze B2 ──────────────────────────────────────────────────────────────

def _upload_to_b2(local_path: Path, remote_key: str) -> str | None:
    """Upload un fichier vers Backblaze B2 (S3-compatible). Non bloquant si non configuré."""
    if not all([B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME, B2_ENDPOINT]):
        return None
    try:
        import boto3
        from botocore.config import Config
        client = boto3.client(
            "s3",
            endpoint_url=B2_ENDPOINT,
            aws_access_key_id=B2_KEY_ID,
            aws_secret_access_key=B2_APPLICATION_KEY,
            config=Config(signature_version="s3v4"),
        )
        content_type = "audio/mpeg" if local_path.suffix == ".mp3" else "video/mp4"
        client.upload_file(
            str(local_path),
            B2_BUCKET_NAME,
            remote_key,
            ExtraArgs={"ContentType": content_type},
        )
        print(f"   ☁️  B2 → {remote_key}")
        return f"{B2_ENDPOINT}/{B2_BUCKET_NAME}/{remote_key}"
    except Exception as e:
        print(f"   ⚠️  B2 upload échoué (non bloquant) : {e}")
        return None


# ── GitHub Releases ───────────────────────────────────────────────────────────

def _upload_to_github_release(local_path: Path, tag: str, release_name: str) -> str | None:
    """Upload un MP3 vers une GitHub Release (publique). Crée la release si nécessaire."""
    if not GITHUB_TOKEN:
        return None
    try:
        import requests as _req
        api = "https://api.github.com"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # Récupérer ou créer la release
        r = _req.get(f"{api}/repos/{GITHUB_REPO}/releases/tags/{tag}", headers=headers, timeout=15)
        if r.status_code == 200:
            release = r.json()
        else:
            r = _req.post(f"{api}/repos/{GITHUB_REPO}/releases", headers=headers, timeout=15, json={
                "tag_name": tag,
                "name": release_name,
                "body": f"Épisodes audio — {release_name}",
                "prerelease": False,
                "draft": False,
            })
            r.raise_for_status()
            release = r.json()

        upload_url = release["upload_url"].split("{")[0]
        filename = local_path.name

        # Vérifier si l'asset existe déjà
        for asset in release.get("assets", []):
            if asset["name"] == filename:
                print(f"   📦 GitHub Release → déjà présent : {asset['browser_download_url']}")
                return asset["browser_download_url"]

        # Uploader l'asset
        print(f"   📦 GitHub Release upload → {tag}/{filename}…")
        with open(local_path, "rb") as f:
            r = _req.post(
                f"{upload_url}?name={filename}",
                headers={**headers, "Content-Type": "audio/mpeg"},
                data=f,
                timeout=300,
            )
        r.raise_for_status()
        url = r.json()["browser_download_url"]
        print(f"   📦 GitHub Release → {url}")
        return url
    except Exception as e:
        print(f"   ⚠️  GitHub Release upload échoué (non bloquant) : {e}")
        return None


# ── Internet Archive (archive.org) ────────────────────────────────────────────

def _upload_to_archive_org(
    local_path: Path,
    identifier: str,
    title: str,
    description: str = "",
    subject: str = "guadeloupe;podcast;karukera",
) -> str | None:
    """Upload vers archive.org via l'API S3. Non bloquant si non configuré."""
    if not all([ARCHIVE_ACCESS_KEY, ARCHIVE_SECRET_KEY]):
        return None
    try:
        import requests as _req
        # Les headers HTTP : pas de newlines, encodage UTF-8 en bytes
        def _h(s: str) -> bytes:
            return s.replace("\n", " ").replace("\r", "").strip().encode("utf-8")
        filename = local_path.name
        url = f"https://s3.us.archive.org/{identifier}/{filename}"
        mediatype = "audio" if local_path.suffix == ".mp3" else "movies"
        headers = {
            "Authorization": f"LOW {ARCHIVE_ACCESS_KEY}:{ARCHIVE_SECRET_KEY}",
            "x-amz-auto-make-bucket": "1",
            "x-archive-ignore-preexisting-bucket": "1",
            "x-archive-meta-mediatype": mediatype,
            "x-archive-meta-title": _h(title),
            "x-archive-meta-language": "fre",
            "x-archive-meta-creator": "Botiran",
            "x-archive-meta-subject": subject,
            "Content-Type": "audio/mpeg" if local_path.suffix == ".mp3" else "video/mp4",
            "Content-Length": str(local_path.stat().st_size),
        }
        if description:
            headers["x-archive-meta-description"] = _h(description[:500])
        print(f"   🏛️  archive.org upload → {identifier}/{filename}…")
        resp = None
        for attempt in range(2):
            with open(local_path, "rb") as f:
                resp = _req.put(url, data=f, headers=headers, timeout=300)
            if resp.status_code < 500:
                break
            wait = 20 * (attempt + 1)
            print(f"   ⏳ archive.org 5xx — attente {wait}s (tentative {attempt + 1}/2)…")
            import time as _time; _time.sleep(wait)
        resp.raise_for_status()
        public_url = f"https://archive.org/download/{identifier}/{filename}"
        print(f"   🏛️  archive.org → {public_url}")
        return public_url
    except Exception as e:
        body = ""
        try:
            body = f" — {resp.text[:300]}"
        except Exception:
            pass
        print(f"   ⚠️  archive.org upload échoué (non bloquant) : {e}{body}")
        return None


def _rfc2822(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def _update_podcast_rss(
    rss_path: Path,
    channel_title: str,
    channel_desc: str,
    episode_title: str,
    episode_desc: str,
    audio_url: str,
    audio_size: int,
    duration_s: float,
    guid: str,
    pub_date: datetime,
) -> None:
    """Insère un épisode en tête du flux RSS podcast (iTunes-compatible)."""
    import re as _re_rss
    existing: list[str] = []
    if rss_path.exists():
        existing = _re_rss.findall(r"<item>.*?</item>", rss_path.read_text(encoding="utf-8"), _re_rss.DOTALL)

    mins, secs = divmod(int(duration_s), 60)
    new_item = (
        f"    <item>\n"
        f"      <title>{episode_title}</title>\n"
        f"      <description><![CDATA[{episode_desc}]]></description>\n"
        f"      <pubDate>{_rfc2822(pub_date)}</pubDate>\n"
        f"      <enclosure url=\"{audio_url}\" length=\"{audio_size}\" type=\"audio/mpeg\"/>\n"
        f"      <guid isPermaLink=\"false\">{guid}</guid>\n"
        f"      <itunes:duration>{mins:02d}:{secs:02d}</itunes:duration>\n"
        f"    </item>"
    )
    artwork = "https://famibelle.github.io/FlashInfoKarukera/artwork.jpg"
    items_block = "\n\n".join([new_item] + existing[:199])
    rss_path.parent.mkdir(parents=True, exist_ok=True)
    rss_path.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">\n'
        f'  <channel>\n'
        f'    <title>{channel_title}</title>\n'
        f'    <link>https://famibelle.github.io/FlashInfoKarukera/</link>\n'
        f'    <description>{channel_desc}</description>\n'
        f'    <language>fr</language>\n'
        f'    <copyright>© Botiran</copyright>\n'
        f'    <itunes:author>Botiran</itunes:author>\n'
        f'    <itunes:owner><itunes:name>Botiran</itunes:name><itunes:email>medhi.famibelle@outlook.fr</itunes:email></itunes:owner>\n'
        f'    <itunes:image href="{artwork}"/>\n'
        f'    <image><url>{artwork}</url><title>{channel_title}</title><link>https://famibelle.github.io/FlashInfoKarukera/</link></image>\n'
        f'    <itunes:category text="News"><itunes:category text="Daily News"/></itunes:category>\n'
        f'    <itunes:explicit>no</itunes:explicit>\n\n'
        f'{items_block}\n\n'
        f'  </channel>\n'
        f'</rss>\n',
        encoding="utf-8",
    )
    print(f"   📻 RSS mis à jour → {rss_path.name} ({len(existing) + 1} épisodes)")


# ── Étape 4 : Envoi Telegram ──────────────────────────────────────────────────

def send_telegram(audio_path: Path, caption: str, reply_to_message_id: int | None = None) -> int | None:
    print(f"📤 Envoi Telegram audio (chat_id={TELEGRAM_CHAT_ID})...")
    boundary = "----FlashInfoBoundary"

    def field(name, value):
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    body = b""
    body += field("chat_id", TELEGRAM_CHAT_ID)
    body += field("caption", caption)
    body += field("title", "Flash info Guadeloupe")
    body += field("performer", "Botiran")
    if reply_to_message_id:
        body += field("reply_to_message_id", str(reply_to_message_id))

    audio_data = audio_path.read_bytes()
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="audio"; filename="{audio_path.name}"\r\n'
        f"Content-Type: audio/mpeg\r\n\r\n"
    ).encode() + audio_data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendAudio",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())

    if not result.get("ok"):
        raise RuntimeError(f"Telegram error: {result}")
    print("   Envoyé ✅")
    return result.get("result", {}).get("message_id")


def send_telegram_photo(photo_path: Path, caption: str = "") -> None:
    """Envoie une image sur Telegram via sendPhoto."""
    boundary = "----FlashInfoBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        f"{TELEGRAM_CHAT_ID}\r\n"
    ).encode()
    if caption:
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n'
            f"{caption}\r\n"
        ).encode()
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="photo"; filename="{photo_path.name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + photo_path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        result = json.loads(r.read())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram photo error: {result}")
    print(f"   {photo_path.name} envoyé ✅")


TELEGRAM_VIDEO_MAX_MB = 49  # limite Telegram bot API


def send_telegram_video(
    video_path: Path,
    caption: str,
    timeout: int = 180,
    thumbnail_path: "Path | None" = None,
    reply_to_message_id: int | None = None,
) -> int | None:
    size_mb = video_path.stat().st_size / 1_048_576
    print(f"   Upload Telegram : {video_path.name} ({size_mb:.1f} Mo)…")
    if size_mb > TELEGRAM_VIDEO_MAX_MB:
        print(f"   ⚠️  Vidéo trop volumineuse ({size_mb:.1f} Mo > {TELEGRAM_VIDEO_MAX_MB} Mo) — upload ignoré.")
        return None

    boundary = "----FlashInfoBoundary"

    def field(name, value):
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    def file_field(name, filename, content_type, data):
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + data + b"\r\n"

    body = field("chat_id", TELEGRAM_CHAT_ID) + field("caption", caption)
    if reply_to_message_id:
        body += field("reply_to_message_id", str(reply_to_message_id))
    body += file_field("video", video_path.name, "video/mp4", video_path.read_bytes())
    if thumbnail_path and thumbnail_path.exists():
        body += file_field("thumbnail", thumbnail_path.name, "image/png", thumbnail_path.read_bytes())
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )

    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                result = json.loads(r.read())
            if not result.get("ok"):
                raise RuntimeError(f"Telegram video error: {result}")
            print(f"   {video_path.name} envoyé ✅")
            return result.get("result", {}).get("message_id")
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as exc:
            if attempt < 3:
                wait = 10 * attempt
                print(f"   ⚠️  Tentative {attempt}/3 échouée ({exc}) — nouvel essai dans {wait}s…")
                time.sleep(wait)
            else:
                raise
    return None


# ── Étape 5 : Publication Buzzsprout → Spotify ───────────────────────────────

BUZZSPROUT_TAGS = "Guadeloupe, actualité, flash info, Antilles, Caraïbes, France-Antilles, info locale"

def publish_buzzsprout(audio_path: Path, title: str, description: str, tags: str) -> tuple[str, str]:
    print(f"🎙️  Publication Buzzsprout (podcast {BUZZSPROUT_PODCAST_ID})...")
    cmd = [
        "curl", "-s",
        "-H", f"Authorization: Token token={BUZZSPROUT_API_TOKEN}",
        "-F", f"title={title}",
        "-F", f"description={description}",
        "-F", f"tags={tags}",
        "-F", "explicit=false",
        "-F", "private=false",
        "-F", f"audio_file=@{audio_path};type=audio/mpeg",
        f"https://www.buzzsprout.com/api/{BUZZSPROUT_PODCAST_ID}/episodes.json",
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"curl error: {proc.stderr.decode()}")
    result = json.loads(proc.stdout)

    episode_url = result.get("url", "")
    audio_url = result.get("audio_url", "") or ""
    episode_id = result.get("id", "")
    print(f"   Épisode publié ✅  id={episode_id}  url={episode_url}")

    # Buzzsprout traite l'audio de façon asynchrone — on attend l'audio_url
    if not audio_url and episode_id and BUZZSPROUT_API_TOKEN and BUZZSPROUT_PODCAST_ID:
        import time as _time
        for _ in range(8):
            _time.sleep(15)
            r = subprocess.run([
                "curl", "-s",
                "-H", f"Authorization: Token token={BUZZSPROUT_API_TOKEN}",
                f"https://www.buzzsprout.com/api/{BUZZSPROUT_PODCAST_ID}/episodes/{episode_id}.json",
            ], capture_output=True, timeout=30)
            if r.returncode == 0:
                ep = json.loads(r.stdout)
                audio_url = ep.get("audio_url", "") or ""
                if audio_url:
                    print(f"   🔗 audio_url Buzzsprout : {audio_url}")
                    break
            _time.sleep(5)

    return episode_url, audio_url


# ── Étape 6 : Post X/Twitter ─────────────────────────────────────────────────

def post_x(text: str, video_path: "Path | None" = None) -> None:
    import tweepy

    print("🐦 Post X/Twitter...")

    auth = tweepy.OAuth1UserHandler(
        X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
    )
    api = tweepy.API(auth, wait_on_rate_limit=True)
    client = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_TOKEN_SECRET,
    )

    media_ids = None
    if video_path:
        size_mb = video_path.stat().st_size / 1_048_576
        print(f"   Upload vidéo : {video_path.name} ({size_mb:.1f} Mo)…")
        media = api.media_upload(
            filename=str(video_path),
            media_category="tweet_video",
            chunked=True,
        )
        # Attendre la fin du processing
        for _ in range(30):
            status = api.get_media_upload_status(media.media_id)
            state = status.processing_info.get("state") if hasattr(status, "processing_info") and status.processing_info else "succeeded"
            if state in ("succeeded", "failed"):
                break
            wait = status.processing_info.get("check_after_secs", 5) if status.processing_info else 5
            print(f"   Processing vidéo ({state})… attente {wait}s")
            time.sleep(wait)
        if state == "failed":
            raise RuntimeError(f"Twitter media processing failed: {status.processing_info}")
        media_ids = [media.media_id_string]
        print(f"   Vidéo uploadée ✅  media_id={media.media_id_string}")

    # Tronquer le texte à 280 caractères (Twitter limite)
    tweet_text = text[:277] + "…" if len(text) > 280 else text
    response = client.create_tweet(text=tweet_text, media_ids=media_ids)
    tweet_id = response.data["id"]
    print(f"   Tweet publié ✅  id={tweet_id}")


# ── Descriptions et hashtags par plateforme ──────────────────────────────────

_HASHTAGS_BASE    = "#Guadeloupe #FlashInfo #Karukera #Antilles #Caraïbes"
_HASHTAGS_METEO   = "#Météo #MétéoGuadeloupe #MétéoAntilles"
_HASHTAGS_NEWS    = "#Actualités #InfosGuadeloupe #ActuGuadeloupe"
_HASHTAGS_TIKTOK  = "#GuadeloupeTikTok #InfoTikTok"
_HASHTAGS_YOUTUBE = "#Shorts #YouTubeShorts"


_HASHTAGS_HOROSCOPE = "#Horoscope #AstroGuadeloupe #Zodiaque"


def _seg_label(i: int, n: int, has_prenom: bool = False, has_horoscope: bool = False, has_meteo: bool = True) -> str:
    """Retourne le label lisible d'un segment selon son index (0-based)."""
    if i == 0:
        return "INTRO"
    _k = 0
    prenom_idx = horoscope_idx = meteo_idx = None
    if has_prenom:
        _k += 1; prenom_idx = _k
    if has_meteo:
        _k += 1; meteo_idx = _k
    if has_horoscope:
        _k += 1; horoscope_idx = _k
    news_start = _k + 1
    if prenom_idx is not None and i == prenom_idx:
        return "BONNE FÊTE"
    if meteo_idx is not None and i == meteo_idx:
        return "MÉTÉO"
    if horoscope_idx is not None and i == horoscope_idx:
        return "HOROSCOPE"
    if i == n - 1:
        return "OUTRO"
    return f"SUJET {i - news_start + 1}"


def _video_label(idx: int, n_segments: int) -> str:
    if idx == 1:
        return "météo"
    if idx == 2:
        return "horoscope"
    return f"sujet {idx - 2}"


def _tiktok_caption(text: str, idx: int, n_segments: int, date_str: str) -> str:
    """Caption courte pour TikTok : accroche + hashtags (~300 car.)."""
    is_meteo     = idx == 1
    is_horoscope = idx == 2
    first_sentence = text.split(".")[0].strip()
    if len(first_sentence) > 120:
        first_sentence = first_sentence[:117] + "…"
    if is_meteo:
        topic_tags = _HASHTAGS_METEO
        label = "Météo Guadeloupe"
    elif is_horoscope:
        topic_tags = _HASHTAGS_HOROSCOPE
        label = "Horoscope du jour"
    else:
        topic_tags = _HASHTAGS_NEWS
        label = f"Flash Info — {date_str}"
    return (
        f"🇬🇵 {label}\n"
        f"{first_sentence}.\n\n"
        f"{_HASHTAGS_BASE} {topic_tags} {_HASHTAGS_TIKTOK}"
    )


def _youtube_description(text: str, idx: int, n_segments: int, date_str: str) -> str:
    """Description YouTube Shorts : extrait + hashtags."""
    is_meteo     = idx == 1
    is_horoscope = idx == 2
    excerpt = text[:400].rsplit(" ", 1)[0] + "…" if len(text) > 400 else text
    if is_meteo:
        topic_tags = _HASHTAGS_METEO
        label = "Météo"
    elif is_horoscope:
        topic_tags = _HASHTAGS_HOROSCOPE
        label = "Horoscope"
    else:
        topic_tags = _HASHTAGS_NEWS
        label = f"Sujet {idx - 2}"
    return (
        f"Flash Info Guadeloupe — {date_str} — {label}\n\n"
        f"{excerpt}\n\n"
        f"{_HASHTAGS_BASE} {topic_tags} {_HASHTAGS_YOUTUBE}"
    )


# ── Étape 7 : Publication YouTube Shorts ─────────────────────────────────────

YOUTUBE_SCOPES       = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_TAGS         = ["Guadeloupe", "flash info", "actualité", "Antilles", "Caraïbes", "Karukera", "météo", "Shorts"]
YOUTUBE_CATEGORY_ID  = "25"  # News & Politics


def _save_refresh_token(token: str) -> None:
    env_path = Path(__file__).parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    for i, line in enumerate(lines):
        if line.startswith("YOUTUBE_REFRESH_TOKEN="):
            lines[i] = f"YOUTUBE_REFRESH_TOKEN={token}"
            break
    else:
        lines.append(f"YOUTUBE_REFRESH_TOKEN={token}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("   Refresh token sauvegardé dans .env")


def _youtube_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleRequest
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": YOUTUBE_CLIENT_ID,
            "client_secret": YOUTUBE_CLIENT_SECRET,
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    if YOUTUBE_REFRESH_TOKEN:
        creds = Credentials(
            token=None,
            refresh_token=YOUTUBE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=YOUTUBE_CLIENT_ID,
            client_secret=YOUTUBE_CLIENT_SECRET,
            scopes=YOUTUBE_SCOPES,
        )
        creds.refresh(GoogleRequest())
        return creds

    flow = InstalledAppFlow.from_client_config(client_config, YOUTUBE_SCOPES)
    creds = flow.run_local_server(port=0)
    _save_refresh_token(creds.refresh_token)
    return creds


def upload_youtube_short(video_path: Path, title: str, description: str) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    print(f"   ▶️  Upload : {video_path.name}…")
    creds = _youtube_credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "title": f"{title} #Shorts",
            "description": description,
            "tags": YOUTUBE_TAGS,
            "categoryId": YOUTUBE_CATEGORY_ID,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    from googleapiclient.errors import ResumableUploadError
    try:
        response = None
        while response is None:
            _, response = request.next_chunk()
    except ResumableUploadError as e:
        if "uploadLimitExceeded" in str(e):
            print(f"   ⚠️  Quota YouTube dépassé : limite journalière d'uploads atteinte — vidéo ignorée.")
            return ""
        raise

    url = f"https://youtube.com/shorts/{response['id']}"
    print(f"   ✅ {url}")
    return url


def _stinger_duration(stinger: Path) -> float:
    """Retourne la durée du stinger en secondes via ffprobe."""
    proc = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(stinger),
    ], capture_output=True, text=True)
    return float(proc.stdout.strip())


def _build_srt(pairs: "list[tuple[str | None, float]]", words_per_line: int = 12) -> str:
    """Génère un fichier SRT depuis (texte_ou_None, durée_s). Découpe en chunks lisibles."""
    def _ts(s: float) -> str:
        h, rem = divmod(s, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")
    lines, t, n = [], 0.0, 1
    for text, dur in pairs:
        if text and text.strip():
            words = text.strip().split()
            chunks = [words[i:i + words_per_line] for i in range(0, len(words), words_per_line)]
            chunk_dur = dur / len(chunks)
            for j, chunk in enumerate(chunks):
                cs = t + j * chunk_dur
                ce = cs + chunk_dur
                lines += [str(n), f"{_ts(cs)} --> {_ts(ce)}", " ".join(chunk), ""]
                n += 1
        t += dur
    return "\n".join(lines)


def _interleave_interstitials(
    videos: list[tuple[int, Path]],
    items: list[dict],
    output_dir: Path,
    stinger: Path,
    has_prenom: bool = False,
    has_horoscope: bool = False,
    has_meteo: bool = True,
    horoscope_signs: list[str] | None = None,
    prenoms_du_jour: list[str] | None = None,
) -> list[Path]:
    """Intercale un interstitiel avant chaque segment de contenu."""
    _k = 0
    prenom_idx = horoscope_idx = meteo_idx = None
    if has_prenom:
        _k += 1; prenom_idx = _k
    if has_meteo:
        _k += 1; meteo_idx = _k
    if has_horoscope:
        _k += 1; horoscope_idx = _k
    news_start = _k + 1

    result: list[Path] = []
    for idx, video_path in videos:
        if idx == 0:
            result.append(video_path)
            continue

        if prenom_idx is not None and idx == prenom_idx:
            category = "prenom"
        elif meteo_idx is not None and idx == meteo_idx:
            category = "météo"
        elif horoscope_idx is not None and idx == horoscope_idx:
            category = "horoscope"
        elif idx - news_start < len(items):
            category = items[idx - news_start].get("category", "general")
        else:
            category = "general"

        inter_path = output_dir / f"inter_{idx:02d}_{category.replace(' ', '_')}.mp4"
        if horoscope_idx is not None and idx == horoscope_idx:
            sign_tags = [f"#{s}" for s in (horoscope_signs or [])]
            hashtags = ["#Horoscope", "#Zodiaque", "#AstroGuadeloupe"] + sign_tags
        elif idx >= news_start and idx - news_start < len(items):
            hashtags = items[idx - news_start].get("hashtags", [])
        else:
            hashtags = []
        subtitle = " & ".join(prenoms_du_jour) if (category == "prenom" and prenoms_du_jour) else None
        print(f"   Interstitiel [{idx}] — {category} {hashtags[:2]}")
        _make_interstitial(category, inter_path, stinger, hashtags, subtitle=subtitle)
        result.append(inter_path)
        result.append(video_path)

    cta_path = output_dir / "inter_cta.mp4"
    print("   Interstitiel CTA — clôture")
    _make_cta_interstitial(cta_path, stinger)
    result.append(cta_path)

    return result


def generate_thumbnail(
    intro_text: str, target_date: "Date", output_dir: Path,
    hashtags: list[str] | None = None, verbose: bool = False
) -> "Path | None":
    """Génère une illustration verticale via OpenAI gpt-image-2 à partir du texte d'intro."""
    if not OPENAI_API_KEY:
        print("   ⚠️  OPENAI_API_KEY absent — thumbnail ignoré.")
        return None
    if not BOTIRAN_PROFILE.exists():
        print(f"   ⚠️  Image de référence introuvable : {BOTIRAN_PROFILE} — thumbnail ignoré.")
        return None
    try:
        from openai import OpenAI
    except ImportError:
        print("   ⚠️  Package 'openai' non installé — thumbnail ignoré.")
        return None

    hashtags_str = ""
    if hashtags:
        sample = random.sample(hashtags, min(5, len(hashtags)))
        hashtags_str = " Thèmes clés : " + " ".join(sample) + "."
    prompt = (
        "Inspire-toi de l'image d'origine pour créer une illustration verticale au style "
        "journalistique pour un flash info audio de Guadeloupe. "
        f"Résumé du flash info : {intro_text[:600]}"
        f"{hashtags_str}"
    )
    print("🖼️  Génération thumbnail via OpenAI gpt-image-2…")
    if verbose:
        print("── Prompt thumbnail ─────────────────────────────────────")
        print(prompt)
        print("─────────────────────────────────────────────────────────")
    # dall-e-2 n'accepte que du PNG — conversion via FFmpeg si nécessaire
    profile_png = OUTPUT_DIR / "botiran_profile_ref.png"
    if BOTIRAN_PROFILE.suffix.lower() != ".png" or not profile_png.exists():
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(BOTIRAN_PROFILE),
            str(profile_png),
        ], check=True)
    try:
        from openai import BadRequestError
        client = OpenAI(api_key=OPENAI_API_KEY)
        result = client.images.edit(
            model="gpt-image-1.5",
            image=[open(str(profile_png), "rb")],
            prompt=prompt,
            size="1024x1536",
            quality="low",
            input_fidelity="high",
        )
        image_bytes = base64.b64decode(result.data[0].b64_json)
        thumbnail_path = output_dir / f"thumbnail-{target_date}.png"
        thumbnail_path.write_bytes(image_bytes)
        print(f"   Thumbnail : {thumbnail_path} ({len(image_bytes) // 1024} Ko)")
        return thumbnail_path
    except BadRequestError as e:
        default = MEDIA_DIR / "botiran_news_default_thumbnail.png"
        print(f"   ⚠️  Génération thumbnail échouée : {e.message} — utilisation du thumbnail par défaut.")
        return default if default.exists() else None


def _embed_thumbnail(video_path: Path, thumbnail_path: Path) -> Path:
    """Insère le thumbnail comme première frame du MP4 (1 frame à 30fps ≈ 33ms)."""
    tmp_path = video_path.with_suffix(".thumb.mp4")
    one_frame = f"{1/30:.6f}"
    proc = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", "30", "-t", one_frame,
        "-i", str(thumbnail_path),
        "-f", "lavfi", "-t", one_frame,
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-i", str(video_path),
        "-filter_complex",
        "[0:v][2:v]scale2ref[thumb][vid];"
        "[thumb]setsar=1[thumb_s];"
        "[thumb_s][1:a][vid][2:a]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-c:a", "aac",
        "-movflags", "+faststart",
        str(tmp_path),
    ], capture_output=True)
    if proc.returncode != 0:
        print(f"   ⚠️  Insertion première frame échouée : {proc.stderr.decode()[:200]}")
        tmp_path.unlink(missing_ok=True)
        return video_path
    tmp_path.replace(video_path)
    return video_path


def concatenate_videos(
    video_paths: list[Path],
    output_path: Path,
    metadata: dict[str, str] | None = None,
    srt_path: Path | None = None,
) -> Path:
    """
    Concatène les MP4 via le concat filter graph FFmpeg.
    Chaque stream vidéo est normalisé à 30fps/SAR=1 et chaque stream audio à 44100Hz
    avant d'être passé au filtre concat, ce qui garantit A/V sync parfaite à chaque
    jonction quelle que soit la source (segments TTS ou interstitiels lavfi).
    """
    n = len(video_paths)
    inputs = []
    for p in video_paths:
        inputs += ["-i", str(p)]

    has_srt = srt_path is not None and srt_path.exists()
    if has_srt:
        inputs += ["-i", str(srt_path)]

    # Normalise chaque clip indépendamment, puis les enchaîne
    filter_parts = []
    for i in range(n):
        filter_parts.append(f"[{i}:v]fps=30,setsar=1[v{i}]")
        filter_parts.append(f"[{i}:a]aresample=44100[a{i}]")

    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=1[vout][aout]")

    filter_complex = ";".join(filter_parts)

    meta_args = []
    for k, v in (metadata or {}).items():
        meta_args += ["-metadata", f"{k}={v}"]

    map_args  = ["-map", "[vout]", "-map", "[aout]"]
    sub_args  = []
    if has_srt:
        map_args += ["-map", f"{n}:s"]
        sub_args  = ["-c:s", "mov_text", "-metadata:s:s:0", "language=fra"]

    proc = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        *inputs,
        "-filter_complex", filter_complex,
        *map_args,
        "-c:v", "libx264", "-preset", "medium", "-crf", "28",
        "-c:a", "aac", "-b:a", "192k",
        *sub_args,
        *meta_args,
        str(output_path),
    ], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat error: {proc.stderr.decode()}")
    return output_path


def _youtube_full_description(segments: list[str], date_str: str) -> str:
    """Description YouTube pour la vidéo complète : chapitres + hashtags."""
    lines = [f"Flash Info Guadeloupe — {date_str}\n"]
    for i, seg in enumerate(segments):
        if i == 0:
            label = "Intro"
        elif i == len(segments) - 1:
            label = "Outro"
        elif i == 1:
            label = "Météo"
        else:
            label = f"Sujet {i - 1}"
        first = seg.split(".")[0].strip()
        if len(first) > 80:
            first = first[:77] + "…"
        lines.append(f"▸ {label} — {first}.")
    lines.append(f"\n{_HASHTAGS_BASE} {_HASHTAGS_NEWS} {_HASHTAGS_METEO}")
    return "\n".join(lines)


def upload_youtube_video(video_path: Path, title: str, description: str) -> str:
    """Upload une vidéo YouTube normale (pas un Short)."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    print(f"   ▶️  Upload vidéo complète : {video_path.name}…")
    creds = _youtube_credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": YOUTUBE_TAGS + ["flash info complet", "radio Guadeloupe"],
            "categoryId": YOUTUBE_CATEGORY_ID,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    from googleapiclient.errors import ResumableUploadError
    try:
        response = None
        while response is None:
            _, response = request.next_chunk()
    except ResumableUploadError as e:
        if "uploadLimitExceeded" in str(e):
            print(f"   ⚠️  Quota YouTube dépassé : limite journalière d'uploads atteinte — vidéo ignorée.")
            return ""
        raise

    url = f"https://youtube.com/watch?v={response['id']}"
    print(f"   ✅ {url}")
    return url


# ── Étape 8 : Publication LinkedIn ───────────────────────────────────────────

_LINKEDIN_CHUNK = 4 * 1024 * 1024  # 4 Mo par chunk


def _linkedin_save_tokens(access_token: str, refresh_token: str) -> None:
    env_path = Path(__file__).parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updates = {
        "LINKEDIN_ACCESS_TOKEN":  access_token,
        "LINKEDIN_REFRESH_TOKEN": refresh_token,
    }
    for key, val in updates.items():
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={val}"
                break
        else:
            lines.append(f"{key}={val}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("   Tokens LinkedIn sauvegardés dans .env")


def _linkedin_ensure_token() -> str:
    """Retourne un access token valide, en le rafraîchissant si possible."""
    global LINKEDIN_ACCESS_TOKEN, LINKEDIN_REFRESH_TOKEN
    if not (LINKEDIN_REFRESH_TOKEN and LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET):
        return LINKEDIN_ACCESS_TOKEN
    body = urllib.parse.urlencode({
        "grant_type":    "refresh_token",
        "refresh_token": LINKEDIN_REFRESH_TOKEN,
        "client_id":     LINKEDIN_CLIENT_ID,
        "client_secret": LINKEDIN_CLIENT_SECRET,
    }).encode()
    req = urllib.request.Request(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    LINKEDIN_ACCESS_TOKEN  = data["access_token"]
    LINKEDIN_REFRESH_TOKEN = data.get("refresh_token", LINKEDIN_REFRESH_TOKEN)
    _linkedin_save_tokens(LINKEDIN_ACCESS_TOKEN, LINKEDIN_REFRESH_TOKEN)
    return LINKEDIN_ACCESS_TOKEN


def upload_linkedin_video(video_path: Path, commentary: str) -> str:
    """Publie une vidéo sur LinkedIn avec le texte fourni."""
    token = _linkedin_ensure_token()
    owner = f"urn:li:person:{LINKEDIN_PERSON_ID}"
    file_size = video_path.stat().st_size
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "LinkedIn-Version": "202501",
    }

    # 1. Initialiser l'upload
    print(f"   ▶️  Initialisation upload LinkedIn : {video_path.name}…")
    init_body = json.dumps({
        "initializeUploadRequest": {
            "owner": owner,
            "fileSizeBytes": file_size,
            "uploadCaptions": False,
            "uploadThumbnail": False,
        }
    }).encode()
    req = urllib.request.Request(
        "https://api.linkedin.com/v2/videos?action=initializeUpload",
        data=init_body, headers=headers,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        init_data = json.loads(r.read())

    video_urn   = init_data["value"]["video"]
    upload_token = init_data["value"]["uploadToken"]
    instructions = init_data["value"]["uploadInstructions"]

    # 2. Upload par chunks
    video_bytes = video_path.read_bytes()
    etags = []
    for i, instruction in enumerate(instructions):
        first, last = instruction["firstByteOffset"], instruction["lastByteOffset"]
        chunk = video_bytes[first:last + 1]
        print(f"   Chunk {i + 1}/{len(instructions)} ({len(chunk) // 1024} Ko)…")
        put_req = urllib.request.Request(
            instruction["uploadUrl"],
            data=chunk, method="PUT",
            headers={"Content-Type": "application/octet-stream"},
        )
        with urllib.request.urlopen(put_req, timeout=300) as r:
            etags.append(r.headers.get("ETag", ""))

    # 3. Finaliser l'upload
    final_body = json.dumps({
        "finalizeUploadRequest": {
            "video": video_urn,
            "token": upload_token,
            "uploadedPartIds": etags,
        }
    }).encode()
    req = urllib.request.Request(
        "https://api.linkedin.com/v2/videos?action=finalizeUpload",
        data=final_body, headers=headers,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()

    # 4. Créer le post
    post_body = json.dumps({
        "author": owner,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "content": {
            "media": {"id": video_urn},
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }).encode()
    req = urllib.request.Request(
        "https://api.linkedin.com/v2/posts",
        data=post_body, headers=headers,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        post_id = r.headers.get("x-restli-id", "")

    url = f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else "https://www.linkedin.com/feed/"
    print(f"   ✅ {url}")
    return url


# ── Étape 9 : Publication Instagram ──────────────────────────────────────────

_INSTAGRAM_API = "https://graph.facebook.com/v21.0"


def _instagram_save_token(access_token: str) -> None:
    env_path = Path(__file__).parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    for i, line in enumerate(lines):
        if line.startswith("INSTAGRAM_ACCESS_TOKEN="):
            lines[i] = f"INSTAGRAM_ACCESS_TOKEN={access_token}"
            break
    else:
        lines.append(f"INSTAGRAM_ACCESS_TOKEN={access_token}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("   Token Instagram sauvegardé dans .env")


def _instagram_refresh_token() -> str:
    """Renouvelle le token Instagram long-lived (valide 60 jours)."""
    global INSTAGRAM_ACCESS_TOKEN
    if not INSTAGRAM_ACCESS_TOKEN:
        return INSTAGRAM_ACCESS_TOKEN
    qs = urllib.parse.urlencode({
        "grant_type":   "ig_refresh_token",
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    })
    req = urllib.request.Request(
        f"https://graph.instagram.com/refresh_access_token?{qs}"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    INSTAGRAM_ACCESS_TOKEN = data["access_token"]
    _instagram_save_token(INSTAGRAM_ACCESS_TOKEN)
    return INSTAGRAM_ACCESS_TOKEN


def upload_instagram_reel(video_path: Path, caption: str) -> str:
    """Publie un Reel Instagram via upload direct (sans URL publique)."""
    token = _instagram_refresh_token()
    file_size = video_path.stat().st_size

    # 1. Créer le container en mode upload resumable
    print(f"   ▶️  Initialisation upload Instagram : {video_path.name}…")
    qs = urllib.parse.urlencode({
        "media_type":  "REELS",
        "upload_type": "resumable",
        "caption":     caption,
        "access_token": token,
    })
    req = urllib.request.Request(
        f"{_INSTAGRAM_API}/{INSTAGRAM_USER_ID}/media?{qs}",
        data=b"", method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    container_id = data["id"]
    upload_uri   = data["uri"]

    # 2. Upload la vidéo
    print(f"   Upload vidéo ({file_size // 1024 // 1024} Mo)…")
    video_bytes = video_path.read_bytes()
    upload_req = urllib.request.Request(
        upload_uri,
        data=video_bytes, method="POST",
        headers={
            "Authorization": f"OAuth {token}",
            "offset":        "0",
            "file_size":     str(file_size),
            "Content-Type":  "video/mp4",
        },
    )
    with urllib.request.urlopen(upload_req, timeout=300) as r:
        r.read()

    # 3. Attendre que le container soit prêt (max 2 min 30)
    print("   Traitement Instagram en cours…")
    for attempt in range(30):
        qs_status = urllib.parse.urlencode({
            "fields": "status_code",
            "access_token": token,
        })
        status_req = urllib.request.Request(
            f"{_INSTAGRAM_API}/{container_id}?{qs_status}"
        )
        with urllib.request.urlopen(status_req, timeout=30) as r:
            status = json.loads(r.read())
        code = status.get("status_code", "")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"Instagram container en erreur : {status}")
        time.sleep(5)
    else:
        raise RuntimeError("Instagram : timeout en attente du container (150s)")

    # 4. Publier
    qs_pub = urllib.parse.urlencode({
        "creation_id":  container_id,
        "access_token": token,
    })
    pub_req = urllib.request.Request(
        f"{_INSTAGRAM_API}/{INSTAGRAM_USER_ID}/media_publish?{qs_pub}",
        data=b"", method="POST",
    )
    with urllib.request.urlopen(pub_req, timeout=30) as r:
        pub_data = json.loads(r.read())

    media_id = pub_data.get("id", "")
    url = f"https://www.instagram.com/p/{media_id}/" if media_id else "https://www.instagram.com/"
    print(f"   ✅ {url}")
    return url


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Flash info Guadeloupe — génère automatiquement un bulletin audio à partir\n"
            "des flux RSS locaux et de la météo Open-Meteo, rédigé par Maryse (Mistral)\n"
            "et synthétisé en MP3 via Voxtral TTS, puis diffusé sur Telegram et Buzzsprout.\n\n"
            "Workflow : Collecte RSS → Météo → Rédaction Maryse → TTS par segment\n"
            "           → Assemblage FFmpeg avec stinger → Telegram → Buzzsprout → X"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--date", metavar="YYYY-MM-DD",
        help=(
            "Date de collecte des actualités et de la météo (défaut : aujourd'hui).\n"
            "Permet de rejouer un flash pour une date passée ou future.\n"
            "Exemple : --date 2026-04-18"
        ),
    )
    parser.add_argument(
        "--edition", choices=["matin", "midi", "soir"], default=None,
        help=(
            "Édition à diffuser : matin (météo+prénoms+horoscope+infos), "
            "midi (infos uniquement), soir (météo demain+prénoms demain+infos). "
            "Auto-détection par heure de Paris si omis."
        ),
    )
    parser.add_argument(
        "--stinger", metavar="FICHIER",
        help=(
            f"Nom du fichier stinger à insérer entre chaque segment audio.\n"
            f"Le fichier doit se trouver dans : {STINGERS_DIR}\n"
            f"Si omis, le premier fichier du répertoire est utilisé automatiquement.\n"
            f"Si le répertoire est vide, un stinger synthétique (goutte d'eau) est généré.\n"
            f"Exemple : --stinger stinger_default.mp3"
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help=(
            "Mode test : génère le script, l'audio et envoie sur Telegram,\n"
            "mais n'envoie pas sur Buzzsprout ni X/Twitter."
        ),
    )
    parser.add_argument(
        "--no-send", action="store_true",
        help=(
            "Génère le fichier audio MP3 complet mais ne l'envoie pas\n"
            "(ni Telegram, ni Buzzsprout, ni X/Twitter).\n"
            "Utile pour écouter et valider avant diffusion."
        ),
    )
    parser.add_argument(
        "--output", type=Path, metavar="CHEMIN",
        help=(
            "Chemin complet du fichier MP3 de sortie.\n"
            "Défaut : /tmp/flash-YYYYMMDD-HHMM.mp3"
        ),
    )
    parser.add_argument(
        "--tiktok", action="store_true",
        help=(
            "Génère une vidéo MP4 TikTok (1080×1920) par segment audio.\n"
            "Waveform colorée selon la tonalité + sous-titres karaoke mot à mot\n"
            "via timestamps STT Voxtral. Vidéos dans /tmp/tiktok-YYYYMMDD-HHMM/.\n"
            "Compatible avec --no-send."
        ),
    )
    parser.add_argument(
        "--youtube", action="store_true",
        help=(
            "Publie les vidéos MP4 sur YouTube Shorts via l'API YouTube Data v3.\n"
            "Nécessite YOUTUBE_CLIENT_ID et YOUTUBE_CLIENT_SECRET dans .env.\n"
            "Le refresh token est sauvegardé automatiquement après la première autorisation.\n"
            "L'intro et l'outro sont exclus. Compatible avec --tiktok."
        ),
    )
    parser.add_argument(
        "--linkedin", action="store_true",
        help=(
            "Publie la vidéo complète sur LinkedIn avec l'intro et 5 hashtags aléatoires.\n"
            "Nécessite LINKEDIN_ACCESS_TOKEN et LINKEDIN_PERSON_ID dans .env.\n"
            "Compatible avec --tiktok et --youtube."
        ),
    )
    parser.add_argument(
        "--instagram", action="store_true",
        help=(
            "Publie la vidéo complète en Reel Instagram avec l'intro et 5 hashtags aléatoires.\n"
            "Nécessite INSTAGRAM_ACCESS_TOKEN et INSTAGRAM_USER_ID dans .env.\n"
            "Requiert un compte Instagram Business ou Créateur lié à une Page Facebook.\n"
            "Compatible avec --tiktok, --youtube et --linkedin."
        ),
    )
    parser.add_argument(
        "--twitter", action="store_true",
        help=(
            "Publie la vidéo complète du flash info sur X/Twitter.\n"
            "Nécessite X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET dans .env.\n"
            "Compatible avec --tiktok."
        ),
    )
    parser.add_argument(
        "--transcript", action="store_true",
        help=(
            "Transcrit l'audio généré via l'API Mistral STT (Voxtral).\n"
            "Permet de vérifier que le TTS a bien prononcé le texte attendu.\n"
            "La transcription est affichée et sauvegardée à côté du MP3 (.txt).\n"
            "Compatible avec --no-send et --dry-run."
        ),
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help=(
            "Mode verbeux : affiche le détail de chaque étape du pipeline.\n"
            "Étape 1 — articles collectés, retenus, écartés (avec raison).\n"
            "Étape 2 — ordre des segments, sources citées, zones géo utilisées.\n"
            "Étape 3 — chemins des fichiers temporaires et assemblage FFmpeg.\n"
            "Compatible avec --dry-run."
        ),
    )
    parser.add_argument(
        "--check-feeds", action="store_true",
        help="Vérifie la disponibilité de chaque flux RSS et affiche un rapport. Arrêt sans générer d'audio.",
    )
    parser.add_argument(
        "--test-interstitials", metavar="RÉPERTOIRE",
        help=(
            "Relit les seg_*.mp4 d'un répertoire généré précédemment, recrée les interstitiels,\n"
            "concatène et envoie la vidéo complète sur Telegram. Ne refait pas la pipeline audio.\n"
            "Exemple : --test-interstitials /tmp/tiktok-20260422-1100"
        ),
    )
    parser.add_argument(
        "--generate-thumbnail", action="store_true",
        help=(
            "Génère uniquement le thumbnail via OpenAI gpt-image-1.5 à partir d'un texte d'intro "
            "par défaut, sans lancer la pipeline complète. Utile pour tester la génération d'image."
        ),
    )
    parser.add_argument(
        "--horoscope-signs", type=int, default=3, metavar="N",
        help="Nombre de signes astrologiques à inclure dans la rubrique horoscope (défaut : 2).",
    )
    parser.add_argument(
        "--horoscope-include", nargs="+", action="append", default=[], metavar="SIGNE",
        help=(
            "Inclure un ou plusieurs signes de force dans l'horoscope (français ou anglais). "
            "Exemple : --horoscope-include gemini capricorn taurus. Répétable. "
            "Signes disponibles : "
            + ", ".join(f"{fr} ({en})" for en, fr in _SIGN_FR.items())
            + "."
        ),
    )
    parser.add_argument(
        "--test-horoscope", action="store_true",
        help=(
            "Récupère l'horoscope du jour pour N signes aléatoires (voir --horoscope-signs) "
            "et affiche le résultat brut de l'API, sans lancer la pipeline complète."
        ),
    )
    parser.add_argument(
        "--test-prenom", nargs="?", const="today", metavar="YYYY-MM-DD",
        help=(
            "Récupère les prénoms depuis nominis.cef.fr sans lancer la pipeline. "
            "Sans date : utilise aujourd'hui (ou --date si fourni). "
            "Exemple : --test-prenom 2026-04-26"
        ),
    )
    parser.add_argument(
        "--test-marroniers", action="store_true",
        help=(
            "Affiche les marroniers actifs à la date donnée (voir --date), "
            "sans lancer la pipeline complète."
        ),
    )
    parser.add_argument(
        "--thumbnail", type=Path, metavar="FICHIER",
        help=(
            "Utilise l'image fournie comme thumbnail (PNG/JPG) au lieu de la générer via OpenAI. "
            "L'image est embarquée dans le MP4 et envoyée sur Telegram avec la vidéo complète."
        ),
    )
    parser.add_argument(
        "--no-thumbnail", action="store_true",
        help="Désactive la génération et l'embed du thumbnail (première frame et envoi Telegram).",
    )
    parser.add_argument(
        "--flush-used-articles", nargs="?", const="today", metavar="YYYY-MM-DD",
        help=(
            "Vide la mémoire anti-répétition pour la date donnée (ou aujourd'hui si absent). "
            "Exemple : --flush-used-articles 2026-04-25"
        ),
    )
    parser.add_argument(
        "--generate-horoscope", nargs="?", const="only", metavar="only",
        help=(
            "Sans argument : lance la pipeline complète en forçant l'inclusion de l'horoscope. "
            "Avec 'only' (--generate-horoscope only) : génère UNIQUEMENT le segment horoscope "
            "(rédaction Maryse + TTS, sans intro/météo/conclusion) et sauvegarde le MP3. "
            "Combinable avec --horoscope-signs, --horoscope-include, --tiktok, --output."
        ),
    )
    args = parser.parse_args()

    if args.test_horoscope:
        _inc = [s for name in (n for group in args.horoscope_include for n in group) if (s := _resolve_sign(name))]
        result = fetch_horoscope(n_signs=args.horoscope_signs, include_signs=_inc or None)
        if result:
            text, signs_fr = result
            print("\n── Horoscope brut ───────────────────────────────────────")
            print(text)
            print(f"\nSignes retenus : {', '.join(signs_fr)}")
            print("─────────────────────────────────────────────────────────")
        return

    if args.generate_horoscope == "only":
        _inc = [s for name in (n for group in args.horoscope_include for n in group) if (s := _resolve_sign(name))]
        _gen_date = Date.fromisoformat(args.date) if args.date else Date.today()
        _date_sign = _sign_for_date(_gen_date)
        if _date_sign not in _inc:
            _inc = [_date_sign] + _inc
            print(f"📅 Signe déduit de la date ({_gen_date}) : {_SIGN_FR[_date_sign]}")
        result = fetch_horoscope(n_signs=args.horoscope_signs, include_signs=_inc or None)
        if not result:
            print("❌ Impossible de récupérer l'horoscope.", file=sys.stderr)
            sys.exit(1)
        horoscope_text, signs_fr = result
        n_signs = len(signs_fr)
        print(f"🔮 Signes retenus : {', '.join(signs_fr)}")
        if args.verbose:
            print("\n══════════════════════════════════════════════════════════")
            print("  VERBOSE — HOROSCOPE BRUT (fetch_horoscope)")
            print("══════════════════════════════════════════════════════════")
            print(horoscope_text)
            print("══════════════════════════════════════════════════════════\n")

        # Collecte du contexte local pour ancrage
        _weather_summary = None
        try:
            _weather_summary = fetch_weather(_gen_date)
        except Exception:
            pass
        _marroniers = _get_marroniers_du_jour(_gen_date)
        _contexte_lines = []
        if _weather_summary:
            _contexte_lines.append(f"Météo du jour à Pointe-à-Pitre : {_weather_summary}")
        if _marroniers:
            _contexte_lines.append("Événements du jour en Guadeloupe : " +
                " ; ".join(f"{m.evenement} ({m.lieu})" for m in _marroniers))
        _contexte_local = (
            "\n\nCONTEXTE LOCAL DU JOUR :\n" + "\n".join(_contexte_lines)
            if _contexte_lines else ""
        )

        # Prompt ciblé : âme de Maryse + instruction horoscope seule, sans structure de flash
        _date_label = _date_fr(_gen_date)
        _horoscope_only_system = (
            _load_prompt("maryse_ame.md") + "\n\n"
            "Tu rédiges UNIQUEMENT le segment horoscope — pas de météo, pas d'actualités. "
            "Juste la lecture de l'horoscope dans ta voix.\n"
            f"Commence OBLIGATOIREMENT par : 'Nous sommes le {_date_label} et ' "
            "puis enchaîne directement avec ta formule ancestrale d'introduction des signes.\n"
            "Termine OBLIGATOIREMENT par une courte formule de clôture dans ta voix — "
            "une phrase de bénédiction ou de congé, puis une formule de rendez-vous du type "
            "'À demain pour un nouvel horoscope' ou une variante naturelle, jamais la même tournure."
        )
        horoscope_instruction = HOROSCOPE_TEMPLATE.format(
            segment=1, n_signs=n_signs, s="s" if n_signs > 1 else "",
            lieux_spirituels=LIEUX_SPIRITUELS,
            contexte_local=_contexte_local,
        )
        horoscope_block = (
            f"HOROSCOPE DU JOUR ({n_signs} signe{'s' if n_signs > 1 else ''} "
            f"tiré{'s' if n_signs > 1 else ''} au hasard) :\n{horoscope_text}\n\n"
        )
        user_prompt = f"{horoscope_block}INSTRUCTIONS :\n{horoscope_instruction}"
        print("✍️  Rédaction horoscope par Maryse (Mistral Large)...")
        segment = _strip_markdown(call_mistral(_horoscope_only_system, user_prompt, temperature=0.75, max_tokens=250 * n_signs + 300))

        # TTS
        output_path = Path(args.output) if args.output else Path("horoscope.mp3")
        tmp = output_path.with_suffix(".tmp.mp3")
        print(f"🔊 Synthèse vocale → {output_path}")
        tone = classify_tones([segment])[0]
        print(f"   Tonalité : {tone}")
        _tts_call(_normalize_for_tts(segment), tmp, TTS_VOICES.get(tone, TTS_VOICE_DEFAULT))
        tmp.rename(output_path)
        print(f"✅ Segment horoscope sauvegardé : {output_path}")
        if args.verbose:
            print("\n── Texte rédigé ─────────────────────────────────────────")
            print(segment)
            print("─────────────────────────────────────────────────────────")

        # Génération vidéo TikTok/Shorts
        if args.tiktok:
            try:
                video_dir = output_path.parent / f"horoscope-{_gen_date.strftime('%Y%m%d')}"
                videos = generate_tiktok(
                    seg_paths=[output_path],
                    segments=[segment],
                    tones=[tone],
                    output_dir=video_dir,
                    has_prenom=False,
                    has_horoscope=True,
                    has_meteo=False,
                )
                if videos:
                    _, video_path = videos[0]
                    print(f"🎬 Vidéo horoscope : {video_path}")
                    send_telegram_video(video_path, f"🔮 Horoscope — {_date_fr(_gen_date)}")
            except Exception as _e:
                print(f"⚠️  TikTok/Telegram échoué (non bloquant) : {_e}")

        # Publication Buzzsprout
        if not args.dry_run and BUZZSPROUT_API_TOKEN and BUZZSPROUT_PODCAST_ID:
            _signs_label = ", ".join(signs_fr)
            _bz_title = f"Horoscope du {_date_fr(_gen_date)} — {_signs_label}"
            _bz_description = (
                f"Horoscope du {_date_fr(_gen_date)} par Maryse.\n"
                f"Signes du jour : {_signs_label}.\n\n"
                "Flash Info Karukera — actualités et horoscope de la Guadeloupe."
            )
            publish_buzzsprout(output_path, _bz_title, _bz_description, BUZZSPROUT_TAGS)  # retourne (episode_url, audio_url) mais non utilisé ici
        elif args.dry_run:
            print("--dry-run : pas de publication Buzzsprout.")
        else:
            print("⚠️  BUZZSPROUT_API_TOKEN / BUZZSPROUT_PODCAST_ID manquants — publication ignorée.")

        return

    if args.test_prenom is not None:
        if args.test_prenom not in (None, "today"):
            try:
                target_date = Date.fromisoformat(args.test_prenom)
            except ValueError:
                print(f"❌ Date invalide : '{args.test_prenom}'. Attendu : YYYY-MM-DD", file=sys.stderr)
                sys.exit(1)
        elif args.date:
            target_date = Date.fromisoformat(args.date)
        else:
            target_date = Date.today()
        prenoms = fetch_prenom_du_jour(target_date)
        if prenoms:
            print("\n── Prénoms ──────────────────────────────────────────────")
            print(f"Date    : {_date_fr(target_date)}")
            print(f"Prénoms : {', '.join(prenoms)}")
            print("─────────────────────────────────────────────────────────")
        return

    if args.flush_used_articles is not None:
        if args.flush_used_articles not in (None, "today"):
            try:
                target_date = Date.fromisoformat(args.flush_used_articles)
            except ValueError:
                print(f"❌ Date invalide : '{args.flush_used_articles}'. Attendu : YYYY-MM-DD", file=sys.stderr)
                sys.exit(1)
        elif args.date:
            target_date = Date.fromisoformat(args.date)
        else:
            target_date = Date.today()
        p = _used_articles_path(target_date)
        if p.exists():
            p.write_text(json.dumps({"titles": []}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"🗑️  Anti-répétition vidée pour le {_date_fr(target_date)} ({p.name})")
        else:
            print(f"ℹ️  Aucun fichier anti-répétition pour le {_date_fr(target_date)} ({p.name})")
        return

    if args.test_marroniers:
        target_date = Date.fromisoformat(args.date) if args.date else Date.today()
        marroniers = _get_marroniers_du_jour(target_date)
        print(f"\n── Marroniers du {target_date.strftime('%A %d %B %Y')} ─────────────────")
        if marroniers:
            for m in marroniers:
                print(f"  [{m.categorie}] {m.lieu}")
                print(f"    {m.evenement}")
        else:
            print("  Aucun marronieur pour cette date.")
        print("─────────────────────────────────────────────────────────")
        return

    if args.generate_thumbnail:
        _DEFAULT_THUMBNAIL_INTRO = (
            "Flash Info Guadeloupe — jeudi 23 avril 2026 "
            "Bèl bonjou à toute la diaspora, nous sommes le jeudi vingt-trois avril deux mille vingt-six "
            "et vous écoutez votre Flash Info avec les nouvelles de la Guadeloupe. "
            "Au programme : Kalash en concert à Luxembourg, le tribunal mixte de commerce de Pointe-à-Pitre "
            "qui doit trancher sur l'avenir d'Air Antilles et une joyeux anniversaire à Anne. C'est parti."
        )
        out = generate_thumbnail(
            _DEFAULT_THUMBNAIL_INTRO,
            Date.today(),
            OUTPUT_DIR,
            verbose=True,
        )
        if out:
            print(f"✅ Thumbnail généré : {out}")
            print("📤 Envoi thumbnail sur Telegram…")
            send_telegram_photo(out, caption=f"🖼️ Thumbnail test — {Date.today()}")
        return

    if args.test_interstitials:
        video_dir = Path(args.test_interstitials)
        if not video_dir.is_dir():
            print(f"❌ Répertoire introuvable : {video_dir}", file=sys.stderr)
            sys.exit(1)
        seg_files = sorted(video_dir.glob("seg_*.mp4"))
        if not seg_files:
            print(f"❌ Aucun fichier seg_*.mp4 dans {video_dir}", file=sys.stderr)
            sys.exit(1)
        items_json = video_dir / "items.json"
        if items_json.exists():
            saved_items = json.loads(items_json.read_text(encoding="utf-8"))
            # Reconstruit le champ category si absent (items.json généré avant cette feature)
            missing = sum(1 for it in saved_items if "category" not in it)
            if missing:
                print(f"   ⚠️  {missing} items sans category — reconstruction depuis le champ source")
                for it in saved_items:
                    if "category" not in it:
                        it["category"] = _SOURCE_CATEGORY.get(it.get("source", ""), "general")
        else:
            print("   ⚠️  items.json absent — catégories indisponibles, tout sera 'general'")
            saved_items = []
        print(f"🎞️  {len(seg_files)} segments trouvés dans {video_dir}")
        videos = [(int(p.stem.split("_")[1]), p) for p in seg_files]
        print("🎞️  Génération des interstitiels…")
        ordered = _interleave_interstitials(videos, saved_items, video_dir, resolve_stinger(args.stinger))
        full_video_path = video_dir / f"flash-info-complet-{target_date}.mp4"
        print("🎞️  Concaténation…")
        concatenate_videos(ordered, full_video_path)
        print(f"   Vidéo complète : {full_video_path} ({full_video_path.stat().st_size // 1024 // 1024} Mo)")
        send_telegram_video(full_video_path, f"🎙️ Test interstitiels — {video_dir.name}")
        print("✅ Envoyé sur Telegram.")
        return

    if args.check_feeds:
        if args.date:
            try:
                check_date = Date.fromisoformat(args.date)
            except ValueError:
                print(f"❌ Format de date invalide : '{args.date}'. Attendu : YYYY-MM-DD", file=sys.stderr)
                sys.exit(1)
        else:
            check_date = datetime.now(GUADELOUPE_TZ).date()

        print(f"🔍 Vérification des flux RSS pour le {_date_fr(check_date)}…\n")
        ok, ko = [], []
        for source in RSS_SOURCES:
            try:
                with urllib.request.urlopen(source.url, timeout=10) as r:
                    content = r.read()
                root = ET.fromstring(content)
                total_found = len(root.findall(".//item")) + len(root.findall(".//entry"))
                day_items = _parse_feed_items(root, check_date)
                print(f"  ✅  {source.name}")
                print(f"      {source.url}")
                print(f"      {total_found} entrées au total, {len(day_items)} pour le {check_date}")
                if args.verbose and day_items:
                    for _, title, date_str_item, desc in day_items:
                        print(f"        • [{date_str_item}] {title}")
                        if desc:
                            preview = desc[:120].replace("\n", " ")
                            print(f"          {preview}{'…' if len(desc) > 120 else ''}")
                print()
                ok.append(source.name)
            except Exception as e:
                print(f"  ❌  {source.name}")
                print(f"      {source.url}")
                print(f"      Erreur : {e}\n")
                ko.append(source.name)
        print(f"Résultat : {len(ok)} OK, {len(ko)} en erreur")
        if ko:
            sys.exit(1)
        return

    now_gwada = datetime.now(GUADELOUPE_TZ)
    heure_paris = _now_paris_str("%Hh%M")
    print(f"🕐 Heure locale Guadeloupe : {_date_fr(now_gwada.date())} — {now_gwada.strftime('%H:%M')} (UTC{now_gwada.strftime('%z')[:3]}:{now_gwada.strftime('%z')[3:]})")

    edition = args.edition or _detect_edition()
    print(f"📻  Édition : {edition.upper()}")

    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"❌ Format de date invalide : '{args.date}'. Attendu : YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
    else:
        target_date = now_gwada.date()

    tomorrow = target_date + timedelta(days=1)
    now = datetime.combine(target_date, datetime.min.time())
    date_str = _date_fr(target_date)

    # Étape 1 — Collecte RSS avec filtre anti-répétition
    used_titles = load_used_titles(target_date)
    if used_titles:
        print(f"🔁  Anti-répétition : {len(used_titles)} titre(s) déjà diffusé(s) aujourd'hui")
    items = fetch_news(RSS_FEEDS, MAX_ITEMS, target_date, edition=edition, exclude_titles=used_titles or None)
    if not items:
        print(f"⚠️  Aucune actualité pour le {date_str} — flash météo uniquement.")

    if items:
        print("🏷️  Génération des hashtags…")
        hashtags_list = generate_hashtags(items)
        for item, hashtags in zip(items, hashtags_list):
            item["hashtags"] = hashtags
        print(f"   {sum(len(h) for h in hashtags_list)} hashtags générés pour {len(items)} articles")

    if args.verbose:
        print("\n══════════════════════════════════════════════════════════")
        print("  VERBOSE — ÉTAPE 1 : COLLECTE RSS")
        print("══════════════════════════════════════════════════════════")
        print(f"  Date cible : {target_date}  |  Édition : {edition}  |  Articles retenus : {len(items)}\n")
        print("  JSON des articles collectés :")
        print(json.dumps(items, ensure_ascii=False, indent=2))
        print("══════════════════════════════════════════════════════════\n")

    # Collectes conditionnelles selon l'édition
    if edition in ("matin", "soir"):
        weather_date   = tomorrow if edition == "soir" else target_date
        weather        = fetch_weather(weather_date)
        weather_label  = "MÉTÉO DE DEMAIN" if edition == "soir" else "MÉTÉO DU JOUR"
        tomorrow_str   = _date_fr(tomorrow) if edition == "soir" else None
    else:
        weather = weather_label = tomorrow_str = None

    if edition == "matin":
        include_signs = []
        for name in (n for group in args.horoscope_include for n in group):
            resolved = _resolve_sign(name)
            if resolved:
                include_signs.append(resolved)
            else:
                print(f"⚠️  Signe inconnu ignoré : '{name}' (valeurs valides : {', '.join(_SIGNS)})")
        horoscope_result = fetch_horoscope(n_signs=args.horoscope_signs, include_signs=include_signs or None)
        horoscope, horoscope_signs = horoscope_result if horoscope_result else (None, [])
    else:
        horoscope = None
        horoscope_signs = []

    prenoms_date = tomorrow if edition == "soir" else target_date
    if edition == "soir":
        print(f"📅  Édition soir : prénoms et communes pour demain ({_date_fr(tomorrow)})")
    if edition != "midi":
        prenoms_du_jour  = fetch_prenom_du_jour(prenoms_date)
        communes_du_jour = get_communes_du_jour(prenoms_date) or None
        if communes_du_jour:
            print(f"⛪  Fête patronale {'de demain' if edition == 'soir' else 'du jour'} : {', '.join(communes_du_jour)}")
    else:
        prenoms_du_jour = communes_du_jour = None

    marroniers_du_jour = _get_marroniers_du_jour(target_date) or None
    if marroniers_du_jour:
        print(f"📅  Marroniers du jour : {', '.join(m.evenement for m in marroniers_du_jour)}")

    # Étape 2
    sources = list(dict.fromkeys(item["source"] for item in items))  # unique, ordre conservé

    if args.verbose and weather:
        print("\n══════════════════════════════════════════════════════════")
        print(f"  VERBOSE — {weather_label}")
        print("══════════════════════════════════════════════════════════")
        print(f"  {weather}")
        print("══════════════════════════════════════════════════════════\n")

    segments_maryse = build_segments(
        items, date_str, weather, sources,
        horoscope=horoscope,
        horoscope_signs=horoscope_signs,
        prenoms_du_jour=prenoms_du_jour,
        communes_du_jour=communes_du_jour,
        marroniers_du_jour=marroniers_du_jour,
        edition=edition,
        weather_label=weather_label or "MÉTÉO DU JOUR",
        tomorrow_str=tomorrow_str,
        heure_paris=heure_paris,
        verbose=args.verbose,
    )

    def _print_segments(segs: list[str], label: str) -> None:
        print(f"\n══════════════════════════════════════════════════════════")
        print(f"  VERBOSE — {label}")
        print(f"══════════════════════════════════════════════════════════")
        for i, seg in enumerate(segs):
            tag = _seg_label(i, len(segs), has_prenom=bool(prenoms_du_jour),
                             has_horoscope=horoscope is not None, has_meteo=weather is not None)
            print(f"\n  ── {tag} ──")
            print(f"  {seg.strip()}")
        print(f"\n  Texte brut (séparateurs inclus) :")
        print(f"\n{SEG_SEPARATOR}\n".join(segs))
        print("══════════════════════════════════════════════════════════\n")

    if args.verbose:
        _print_segments(segments_maryse, "SORTIE MARYSE (brut)")

    # Étape 2b — Révision stylistique
    segments = revise_style(segments_maryse, verbose=args.verbose)
    segments = _ensure_sources_in_outro(segments, sources)
    segments = _enforce_prononciations(segments)

    if args.verbose:
        _print_segments(segments, "SORTIE RÉVISEUR STYLISTIQUE")

    # Étape 2c — Ancrage local
    if args.verbose:
        print("\n══════════════════════════════════════════════════════════")
        print("  VERBOSE — JSON PASSÉ À L'ANCRAGE LOCAL")
        print("══════════════════════════════════════════════════════════")
        print(json.dumps(
            [{"titre": it["title"], "source": it["source"], "description": it["desc"]} for it in items],
            ensure_ascii=False, indent=2
        ))
        print("══════════════════════════════════════════════════════════\n")

    # segments = anchor_local(segments, items, verbose=args.verbose)
    segments = _ensure_sources_in_outro(segments, sources)
    segments = _enforce_prononciations(segments)

    _seg_label_kwargs = dict(has_prenom=bool(prenoms_du_jour),
                             has_horoscope=horoscope is not None,
                             has_meteo=weather is not None)

    if args.verbose:
        _print_segments(segments, "SORTIE ANCRAGE LOCAL (final)")
    else:
        print("\n── Script final (après ancrage) ────────────────────────")
        for i, seg in enumerate(segments):
            label = _seg_label(i, len(segments), **_seg_label_kwargs)
            print(f"\n{label}\n{seg}")
        print("\n────────────────────────────────────────────────────────\n")

    # ── Archive texte ─────────────────────────────────────────────────────────
    try:
        ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
        archive_path = ARCHIVES_DIR / f"flash-info-{target_date.strftime('%Y%m%d')}-{edition}.txt"
        header = (
            f"FLASH INFO KARUKERA — {edition.upper()} — {date_str} {datetime.now().strftime('%H:%M')}\n"
            f"Articles : {len(items)}\n"
            + "=" * 60 + "\n\n"
        )
        archive_path.write_text(
            header + ("\n\n" + "—" * 40 + "\n\n").join(segments),
            encoding="utf-8",
        )
        print(f"📁 Archive texte → {archive_path}")
    except Exception as _e:
        print(f"⚠️  Archive texte échouée (non bloquant) : {_e}")

    # Étape 2d — Classification tonale
    tones = classify_tones(segments)
    prenom_idx_0 = 1 if bool(prenoms_du_jour) else None
    horoscope_idx_0 = _seg_label_kwargs  # reuse dict to compute idx
    # Force tonalités fixes pour prénoms et horoscope
    _k0 = 0
    if bool(prenoms_du_jour): _k0 += 1; _pi = _k0
    else: _pi = None
    if weather is not None: _k0 += 1
    if horoscope is not None: _k0 += 1; _hi = _k0
    else: _hi = None
    if _pi is not None and len(tones) > _pi:
        tones[_pi] = "happy"
    if _hi is not None and len(tones) > _hi:
        tones[_hi] = "curious"

    if args.verbose:
        print("\n══════════════════════════════════════════════════════════")
        print("  VERBOSE — TONALITÉS PAR SEGMENT")
        print("══════════════════════════════════════════════════════════")
        for i, (tone, seg) in enumerate(zip(tones, segments)):
            label = _seg_label(i, len(segments), **_seg_label_kwargs)
            print(f"  {label:8s} → {tone:8s} ({TTS_VOICES.get(tone, TTS_VOICE_DEFAULT)})")
        print("══════════════════════════════════════════════════════════\n")

    # Étape 3
    stinger = resolve_stinger(args.stinger)
    output_path = args.output or OUTPUT_DIR / f"flash-info-{target_date.strftime('%Y%m%d')}-{edition}.mp3"

    if args.verbose:
        print("\n── VERBOSE : Étape 3 — Génération audio ────────────────")
        print(f"  Stinger    : {stinger}")
        print(f"  Sortie MP3 : {output_path}")
        print(f"  Segments   : {len(segments)} → {len(segments) - 1} stingers intercalés")
        print("────────────────────────────────────────────────────────\n")

    output_path, seg_paths = generate_audio(
        segments, output_path, stinger, tones=tones,
        keep_segments=args.tiktok or args.youtube or args.linkedin or args.instagram or args.twitter,
    )

    # Sauvegarde anti-répétition
    if items:
        save_used_titles(target_date, [it["title"] for it in items])

    title      = f"Flash Info Guadeloupe — {date_str}, édition du {edition}"
    intro_text = segments[0].strip() if segments else ""

    # ── Backblaze B2 — audio ──────────────────────────────────────────────────
    b2_key_audio = f"flash-info/{target_date.strftime('%Y/%m')}/{output_path.name}"
    b2_audio_url = _upload_to_b2(output_path, b2_key_audio)

    # ── GitHub Releases — audio public ───────────────────────────────────────
    gh_tag = f"flash-info-{target_date.strftime('%Y-%m')}"
    gh_release_name = f"Flash Info Guadeloupe — {target_date.strftime('%B %Y')}"
    gh_audio_url = _upload_to_github_release(output_path, gh_tag, gh_release_name)

    # ── Internet Archive — audio (non bloquant) ───────────────────────────────
    ia_identifier = f"botiran-flash-info-gwada-{target_date.strftime('%Y-%m')}"
    ia_url = _upload_to_archive_org(
        output_path,
        identifier=ia_identifier,
        title=title,
        description=intro_text,
        subject="guadeloupe;flash info;actualités;karukera;antilles;botiran",
    )

    main_msg_id: int | None = None

    if args.tiktok or args.youtube or args.linkedin or args.instagram or args.twitter:
        video_dir = OUTPUT_DIR / f"tiktok-{edition}-{now.strftime('%Y%m%d-%H%M')}"
        videos = generate_tiktok(seg_paths, segments, tones, video_dir,
                                  has_prenom=bool(prenoms_du_jour), has_horoscope=horoscope is not None,
                                  has_meteo=weather is not None)
        print(f"\n🎬 {len(videos)} vidéos dans {video_dir}")
        (video_dir / "items.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for sp in seg_paths:
            sp.unlink(missing_ok=True)

        n_seg = len(segments)

        # Segment videos stockés pour envoi en reply après la vidéo intégrale
        _segment_videos = [(idx, vp) for idx, vp in videos if idx != 0 and idx != n_seg - 1]

        if args.youtube:
            print("▶️  Publication YouTube Shorts...")
            for idx, video_path in videos:
                if idx == 0 or idx == n_seg - 1:
                    continue  # skip intro et outro
                yt_label = "Météo" if idx == 1 else "Horoscope" if idx == 2 else f"Sujet {idx - 2}"
                yt_title = f"Flash Info Guadeloupe — {date_str} — {yt_label}"
                yt_desc = _youtube_description(segments[idx], idx, n_seg, date_str)
                upload_youtube_short(video_path, yt_title, yt_desc)

        # Vidéo complète : générée dès que --tiktok ou --youtube est actif
        print("🎞️  Génération vidéo complète avec interstitiels…")
        full_video_path = video_dir / f"flash-info-complet-{target_date}.mp4"
        ordered = _interleave_interstitials(videos, items, video_dir, stinger,
                                             has_prenom=bool(prenoms_du_jour),
                                             has_horoscope=horoscope is not None,
                                             has_meteo=weather is not None,
                                             horoscope_signs=horoscope_signs,
                                             prenoms_du_jour=prenoms_du_jour)
        video_metadata = {
            "title":       title,
            "artist":      "Botiran",
            "album":       "Flash Info Karukera",
            "comment":     "Produit par Botiran Flash News",
            "copyright":   f"© {date_str} Flash Info Karukera par Botiran",
            "description": intro_text[:500],
            "date":        date_str,
            "genre":       "Flash Info / Actualités Guadeloupe",
        }
        # Sous-titres SRT embarqués (un chunk toutes les ~12 mots par segment)
        path_to_text = {str(vp): segments[idx] for idx, vp in videos if idx < len(segments)}
        srt_pairs = [(path_to_text.get(str(p)), _stinger_duration(p)) for p in ordered]
        srt_path = video_dir / "subtitles.srt"
        srt_path.write_text(_build_srt(srt_pairs), encoding="utf-8")
        concatenate_videos(ordered, full_video_path, metadata=video_metadata, srt_path=srt_path)
        print(f"   Vidéo complète : {full_video_path} ({full_video_path.stat().st_size // 1024 // 1024} Mo)")
        b2_key_video = f"flash-info/{target_date.strftime('%Y/%m')}/{full_video_path.name}"
        _upload_to_b2(full_video_path, b2_key_video)
        _upload_to_archive_org(
            full_video_path,
            identifier=ia_identifier,
            title=title,
            description=intro_text,
            subject="guadeloupe;flash info;vidéo;karukera;antilles;botiran",
        )

        # Hashtags agrégés (dédupliqués, ordre d'apparition)
        seen, all_hashtags = set(), []
        for it in items:
            for h in it.get("hashtags", []):
                if h not in seen:
                    seen.add(h)
                    all_hashtags.append(h)
        hashtags_line = " ".join(all_hashtags)

        # Thumbnail : fichier fourni par l'utilisateur ou génération OpenAI
        thumbnail_path = None
        if not args.no_thumbnail:
            if args.thumbnail:
                if not args.thumbnail.exists():
                    print(f"   ⚠️  Thumbnail introuvable : {args.thumbnail} — ignoré.")
                else:
                    thumbnail_path = args.thumbnail
                    print(f"   Thumbnail fourni : {thumbnail_path}")
            else:
                thumbnail_path = generate_thumbnail(
                    intro_text, target_date, video_dir,
                    hashtags=all_hashtags, verbose=args.verbose,
                )
        if thumbnail_path:
            _embed_thumbnail(full_video_path, thumbnail_path)

        headlines = "\n".join(f"• {it['title']}" for it in items if it.get("title"))
        full_caption = f"🎙️ {title}\n\n{headlines}\n\n{hashtags_line}".strip()
        if len(full_caption) > 1024:
            full_caption = full_caption[:1021] + "…"

        print("📤 Envoi vidéo complète sur Telegram (post principal)…")
        main_msg_id = send_telegram_video(full_video_path, full_caption, timeout=300, thumbnail_path=thumbnail_path)

        if args.tiktok and _segment_videos:
            print("📤 Envoi des segments en reply…")
            for idx, video_path in _segment_videos:
                caption = _tiktok_caption(segments[idx], idx, n_seg, date_str)
                send_telegram_video(video_path, caption, reply_to_message_id=main_msg_id)

        if args.youtube:
            print("▶️  Upload YouTube vidéo complète…")
            yt_full_desc = _youtube_full_description(segments, date_str)
            upload_youtube_video(full_video_path, title, yt_full_desc)

        if args.linkedin:
            print("▶️  Publication LinkedIn…")
            li_hashtags = random.sample(all_hashtags, min(5, len(all_hashtags)))
            li_commentary = f"{intro_text}\n\n{' '.join(li_hashtags)}".strip()
            upload_linkedin_video(full_video_path, li_commentary)

        if args.instagram:
            print("▶️  Publication Instagram Reel…")
            ig_hashtags = random.sample(all_hashtags, min(5, len(all_hashtags)))
            ig_caption = f"{intro_text}\n\n{' '.join(ig_hashtags)}".strip()
            upload_instagram_reel(full_video_path, ig_caption)

        if args.twitter:
            print("🐦 Publication X/Twitter…")
            x_hashtags = random.sample(all_hashtags, min(4, len(all_hashtags)))
            x_text = f"{title}\n\n{' '.join(x_hashtags)}"
            post_x(x_text, video_path=full_video_path)

    if args.transcript:
        print("📝 Transcription de l'audio généré...")
        transcript = transcribe_audio(output_path)
        print("\n── Transcription ────────────────────────────────────────")
        print(transcript)
        print("────────────────────────────────────────────────────────\n")
        transcript_path = output_path.with_suffix(".txt")
        transcript_path.write_text(transcript, encoding="utf-8")
        print(f"   Sauvegardé : {transcript_path}")

    # Étape 4 — Telegram (dry-run inclus)
    tg_audio_caption = f"🎙️ {title}\n\n{intro_text}".strip()
    if len(tg_audio_caption) > 1024:
        tg_audio_caption = tg_audio_caption[:1021] + "…"
    send_telegram(output_path, tg_audio_caption, reply_to_message_id=main_msg_id)

    if args.dry_run:
        print(f"--dry-run : audio généré et envoyé sur Telegram. Arrêt avant Buzzsprout/X.")
        return

    if args.no_send:
        print(f"--no-send : fichier disponible à {output_path}")
        return

    headlines = "\n".join(f"• {item['title']}" for item in items)
    sources_line = " | ".join(sources) if sources else "médias locaux"
    description = (
        f"Flash info du {date_str} — l'essentiel de l'actualité en Guadeloupe en moins de 2 minutes.\n\n"
        f"Au programme :\n{headlines}\n\n"
        f"Informations issues de : {sources_line}"
    )
    tags = BUZZSPROUT_TAGS

    # Étape 5 — Buzzsprout → Spotify
    episode_url, bz_audio_url = publish_buzzsprout(output_path, title, description, tags)

    # ── Podcast RSS — archive.org > Buzzsprout > B2 ──────────────────────────
    podcast_audio_url = gh_audio_url or ia_url or bz_audio_url or b2_audio_url
    if podcast_audio_url:
        _update_podcast_rss(
            rss_path=PODCAST_RSS_PATH,
            channel_title="Karukera — Flash Info & Horoscope",
            channel_desc="Flash info et horoscope de la Guadeloupe — matin, midi et soir par Botiran",
            episode_title=title,
            episode_desc=intro_text,
            audio_url=podcast_audio_url,
            audio_size=output_path.stat().st_size,
            duration_s=_stinger_duration(output_path),
            guid=output_path.stem,
            pub_date=datetime.utcnow(),
        )
        print(f"   📻 podcast.xml mis à jour → {podcast_audio_url}")
    else:
        print("   ⚠️  podcast.xml non mis à jour (aucune URL audio disponible)")

    print(f"\n✅ Flash info terminé : {output_path}")


if __name__ == "__main__":
    main()
