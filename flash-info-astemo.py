#!/home/medhi/SourceCode/KreyolKeyb/.venv/bin/python3
"""
Flash Info — workflow complet
Collecte RSS → Script → Audio TTS (Voxtral)
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

from data.sources import RSS_FEEDS, RSS_SOURCES

_FEED_CATEGORY: dict[str, str] = {s.url: s.category for s in RSS_SOURCES}
MAX_ITEMS      = 7     # 7 sujets → ~2m-2m30 audio
DESC_MAX_CHARS = 400   # description tronquée pour donner assez de contexte
HASHTAG_COUNT  = 5     # nombre de hashtags générés par article

MISTRAL_API_KEY_ASTEMO     = os.environ["MISTRAL_API_KEY_ASTEMO"]
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



X_API_KEY            = os.environ.get("X_API_KEY", "")
X_API_SECRET         = os.environ.get("X_API_SECRET", "")
X_ACCESS_TOKEN       = os.environ.get("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET", "")

OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")

ARCHIVE_ACCESS_KEY = os.environ.get("ARCHIVE_ACCESS_KEY", "")
ARCHIVE_SECRET_KEY = os.environ.get("ARCHIVE_SECRET_KEY", "")

GITHUB_TOKEN     = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO      = "famibelle/FlashInfoFreinage"

OUTPUT_DIR      = Path(tempfile.gettempdir()) / "flash_info_output"
STINGERS_DIR    = Path(__file__).parent / "Stingers"
PROMPTS_DIR     = Path(__file__).parent / "prompts"
MEDIA_DIR       = Path(__file__).parent / "Media"
DATA_DIR        = Path(__file__).parent / "data"
ARCHIVES_DIR    = Path(__file__).parent / "archives" / "flash-info"
DOCS_DIR        = Path(__file__).parent / "docs"
PODCAST_RSS_PATH = DOCS_DIR / "podcast.xml"
BOTIRAN_PROFILE = MEDIA_DIR / "botiran_profile.jpg"
FREINAGE_TZ   = ZoneInfo("Europe/Paris")

# ── Éditions ──────────────────────────────────────────────────────────────────

_EDITION_INTRO_INSTRUCTION = {
    "matin": (
        "ÉDITION DU MATIN — Intro : commence par 'Bonjour' — ton chaleureux et "
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
    "matin": ("Bonne journée",      "à demain pour une nouvelle édition"),
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

WEATHER_LAT  = 48.9086   # Drancy (Seine-Saint-Denis)
WEATHER_LON  = 2.4431
WEATHER_API         = "https://api.open-meteo.com/v1/forecast"
WEATHER_API_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_FORECAST_DAYS = 16  # fenêtre maximale de l'API forecast

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


def _lieu_priority(lieu: str) -> int:
    """Toujours 1 car lieu = N/A."""
    return 1


NEWS_WINDOW_HOURS = {
    "matin": 24,  # couvre toute la journée précédente
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
            "source": next((s.name for s in RSS_SOURCES if s.url == feed_url), feed_url.split("/")[2].capitalize()),
            "lieu": "N/A",
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
        f'[[\"#Haiti\",\"#Caraibes\"],[\"#Sport\",\"#Freinage\"]].\n\n'
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
        "timezone": "Europe/Paris",
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

    return "\n".join(entries), signs_fr


# ── Étape 2 : Segments rédigés par Madelaine via Mistral ─────────────────────

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
            "Authorization": f"Bearer {MISTRAL_API_KEY_ASTEMO}",
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


MADELAINE_SYSTEM = _load_prompt("madelaine_ame.md") + "\n\n" + _load_prompt("madelaine.md") + "\n\n" + _load_prompt("instructions.md")
MARYSE_SYSTEM = MADELAINE_SYSTEM  # alias pour compatibilité


def _strip_markdown(text: str) -> str:
    import re
    text = re.sub(r"\*+([^*]+)\*+", r"\1", text)
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"^\s*[-#>]+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()





def build_segments(
    items: list[dict], date_str: str, weather: "str | None", sources: list[str],
    marroniers_du_jour: "list | None" = None,
    edition: str = "matin",
    weather_label: str = "MÉTÉO DU JOUR",
    tomorrow_str: "str | None" = None,
    heure_paris: "str | None" = None,
    verbose: bool = False,
) -> list[str]:
    print(f"✍️  Rédaction des segments par Madelaine — édition {edition.upper()} (Mistral Large)...")
    articles = "\n\n".join(
        f"[{i+1}] {item['title']}\n{item['desc']}" for i, item in enumerate(items)
    )
    has_meteo = bool(weather)

    # Calcul dynamique des indices (1-based dans le prompt LLM)
    _idx = 1  # INTRO = segment 1
    meteo_seg = None
    if has_meteo:
        _idx += 1; meteo_seg = _idx
    news_offset = _idx + 1  # premier segment d'actu (1-based)

    sources_str = " et ".join(sources) if sources else "les médias locaux"
    base_segs = 2 + (1 if has_meteo else 0)

    salut, rdv = _EDITION_OUTRO[edition]
    if items:
        n_segs = len(items) + base_segs
        news_block = f"Voici les {len(items)} actualités du jour :\n\n{articles}\n\n"
        outro_template = (
            f"Voilà pour ce L'actualité du Freinage du {date_str}. "
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

    marroniers_block = ""
    if marroniers_du_jour:
        lignes = "\n".join(
            f"- {m.evenement} ({m.lieu})" for m in marroniers_du_jour
        )
        marroniers_block = f"ÉVÉNEMENTS RÉCURRENTS DU JOUR (marroniers) :\n{lignes}\n\nTu peux mentionner ces événements dans l'intro ou dans un segment d'actualité si cela enrichit le flash, mais sans les inventer ni les développer au-delà de ce qui est indiqué.\n\n"

    meteo_block = ""
    meteo_instruction = ""
    if has_meteo:
        label_detail = f"prévisions pour demain {tomorrow_str}" if tomorrow_str else "toute la région parisienne"
        meteo_block = f"{weather_label} ({label_detail}) :\n{weather}\n\n"
        meteo_instr_text = (
            "prévisions météo de demain en style oral — prépare les auditeurs pour la journée de demain"
            if edition == "soir" else "météo du jour en style oral"
        )
        meteo_instruction = f"- Segment {meteo_seg} : {meteo_instr_text}\n"

    edition_instruction = _EDITION_INTRO_INSTRUCTION[edition]

    heure_ctx = f" — il est {heure_paris} à Paris" if heure_paris else ""
    user_prompt = (
        f"Flash Info du {date_str}{heure_ctx} — {edition_instruction}\n\n"
        f"{meteo_block}"
        f"{marroniers_block}"
        f"{news_block}"
        f"Rédige exactement {n_segs} segments séparés par \"{SEG_SEPARATOR}\" :\n"
        f"- Segment 1 : intro (jour + date + accroche)\n"
        f"{news_instructions}"
    )
    if verbose:
        print("\n══════════════════════════════════════════════════════════")
        print("  VERBOSE — PROMPT MADELAINE (system)")
        print("══════════════════════════════════════════════════════════")
        print(MARYSE_SYSTEM)
        print("\n  ── user_prompt ──")
        print(user_prompt)
        print("══════════════════════════════════════════════════════════\n")
    _base_tokens = 1400 if has_meteo else 1200
    raw = call_mistral(MARYSE_SYSTEM, user_prompt, temperature=0.75, max_tokens=_base_tokens)

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
            r"(Voilà pour ce L'actualité du Freinage[^.]*\.)",
            rf"\1 Sources : {sources_str}.",
            outro,
            count=1,
        )
        segments = segments[:-1] + [outro]
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
    """Appelle l'API TTS Mistral avec retry exponentiel (4s, 8s, 16s, 32s)."""
    import time
    
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
            "Authorization": f"Bearer {MISTRAL_API_KEY_ASTEMO}",
            "Content-Type": "application/json",
        },
    )
    
    delays = [4, 8, 16, 32]  # Délais de retry en secondes
    last_error = None
    
    for attempt in range(len(delays) + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                response = json.loads(r.read())
            if "audio_data" not in response:
                raise RuntimeError(f"TTS error: {response}")
            
            # Assurez-vous que output_path est un Path
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(base64.b64decode(response["audio_data"]))
            return  # Succès, sort de la fonction
            
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last_error = e
            if attempt < len(delays):
                delay = delays[attempt]
                print(f"   ⏳ TTS échoué (attempt {attempt + 1}/{len(delays) + 1}) — retry dans {delay}s...")
                time.sleep(delay)
            else:
                raise RuntimeError(f"TTS échoué après {len(delays) + 1} tentatives: {last_error}") from last_error


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
            "Authorization": f"Bearer {MISTRAL_API_KEY_ASTEMO}",
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
    artwork = "https://famibelle.github.io/FlashInfoFreinage/artwork.jpg"
    items_block = "\n\n".join([new_item] + existing[:199])
    rss_path.parent.mkdir(parents=True, exist_ok=True)
    rss_path.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">\n'
        f'  <channel>\n'
        f'    <title>{channel_title}</title>\n'
        f'    <link>https://famibelle.github.io/FlashInfoFreinage/</link>\n'
        f'    <description>{channel_desc}</description>\n'
        f'    <language>fr</language>\n'
        f'    <copyright>© Botiran</copyright>\n'
        f'    <itunes:author>Botiran</itunes:author>\n'
        f'    <itunes:owner><itunes:name>Botiran</itunes:name><itunes:email>medhi.famibelle@outlook.fr</itunes:email></itunes:owner>\n'
        f'    <itunes:image href="{artwork}"/>\n'
        f'    <image><url>{artwork}</url><title>{channel_title}</title><link>https://famibelle.github.io/FlashInfoFreinage/</link></image>\n'
        f'    <itunes:category text="News"><itunes:category text="Daily News"/></itunes:category>\n'
        f'    <itunes:explicit>no</itunes:explicit>\n\n'
        f'{items_block}\n\n'
        f'  </channel>\n'
        f'</rss>\n',
        encoding="utf-8",
    )
    print(f"   📻 RSS mis à jour → {rss_path.name} ({len(existing) + 1} épisodes)")





# ── Main ──────────────────────────────────────────────────────────────────────

def _generate_catchy_title(items: list[dict], edition: str, date_str: str) -> str:
    """Génère un titre accrocheur via Mistral LLM à partir des actualités."""
    if not items:
        return f"Flash Info {edition.capitalize()} — {date_str}"
    
    articles_list = "\n".join(f"- {item['title']}" for item in items[:5])
    
    prompt = (
        f"Tu es un rédacteur en chef spécialisé dans le freinage automobile.\n"
        f"À partir des actualités suivantes, invente un titre ACCROCHEUR et PERCUTANT\n"
        f"(max 60 caractères) pour un flash info du {edition}.\n"
        f"\n"
        f"⚠️  INTERDIT : ne pas utiliser 'Freinage 2026', 'L'actualité du Freinage', ou des termes redondants.\n"
        f"Sois original et direct.\n\n"
        f"Actualités :\n{articles_list}\n\n"
        f"Réponds UNIQUEMENT avec le titre, sans guillemets, sans points, sans retour à la ligne."
    )
    
    try:
        title = call_mistral(
            system="Tu es un assistant strict. Réponds UNIQUEMENT avec le texte demandé, sans ajout ni explication.",
            user=prompt,
            temperature=0.8,
            max_tokens=100,
        )
        # Nettoyer le résultat
        title = title.strip().strip('"').strip("'").strip()
        # Retirer les termes redondants
        title = title.replace("Freinage 2026", "").strip()
        title = title.replace("L'actualité du Freinage", "").strip()
        title = title.replace("Flash Info", "").strip()
        # Limiter à 60 caractères
        return title[:60] if title else f"Flash Info {edition.capitalize()} — {date_str}"
    except Exception as e:
        print(f"   ⚠️  Génération titre accrocheur échouée : {e}")
        return f"Flash Info {edition.capitalize()} — {date_str}"


def _generate_teaser(items: list[dict], edition: str, date_str: str) -> str:
    """Génère un teaser (accroche courte) via Mistral LLM à partir des actualités."""
    if not items:
        return f"Découvrez le flash info du {date_str} — {edition}"
    
    articles_list = "\n".join(f"- {item['title']}" for item in items[:5])
    
    prompt = (
        f"Tu es un rédacteur en chef spécialisé dans le freinage automobile.\n"
        f"À partir des actualités suivantes, écris un TEASER accrocheur (une phrase courte et percutante)\n"
        f"pour donner envie d'écouter le flash info du {edition}.\n"
        f"Max 120 caractères. Style punchy et professionnel.\n"
        f"\n"
        f"⚠️  INTERDIT : ne pas utiliser 'Freinage 2026', 'L'actualité du Freinage', ou 'Flash Info'.\n"
        f"Sois original et engageant.\n\n"
        f"Actualités :\n{articles_list}\n\n"
        f"Réponds UNIQUEMENT avec le teaser, sans guillemets, sans retour à la ligne."
    )
    
    try:
        teaser = call_mistral(
            system="Tu es un assistant strict. Réponds UNIQUEMENT avec le texte demandé.",
            user=prompt,
            temperature=0.9,
            max_tokens=150,
        )
        # Nettoyer le résultat
        teaser = teaser.strip().strip('"').strip("'").strip()
        # Retirer les termes redondants
        for term in ["Freinage 2026", "L'actualité du Freinage", "Flash Info"]:
            teaser = teaser.replace(term, "").strip()
        return teaser[:120] if teaser else f"Découvrez le flash info du {date_str} — {edition}"
    except Exception as e:
        print(f"   ⚠️  Génération teaser échouée : {e}")
        return f"Découvrez le flash info du {date_str} — {edition}"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Flash Info — génère automatiquement un bulletin audio à partir\n"
            "des flux RSS locaux et de la météo Open-Meteo, rédigé par Madelaine (Mistral)\n"
            "et synthétisé en MP3 via Voxtral TTS.\n\n"
            "Workflow : Collecte RSS → Météo → Rédaction Madelaine → TTS par segment\n"
            "           → Assemblage FFmpeg avec stinger"
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
            "Édition à diffuser : matin (météo+infos), "
            "midi (infos uniquement), soir (météo demain+infos). "
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
            "Mode test : génère le script et l'audio,\n"
            "mais n'envoie pas sur Buzzsprout."
        ),
    )
    parser.add_argument(
        "--no-send", action="store_true",
        help=(
            "Génère le fichier audio MP3 complet mais ne l'envoie pas\n"
            "(ni Buzzsprout).\n"
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
        "--test-marroniers", action="store_true",
        help=(
            "Affiche les marroniers actifs à la date donnée (voir --date), "
            "sans lancer la pipeline complète."
        ),
    )
    parser.add_argument(
        "--thumbnail", type=Path, metavar="FICHIER",
        help=(
            "Utilise l'image fournie comme thumbnail (PNG/JPG). "
        ),
    )
    parser.add_argument(
        "--flush-used-articles", nargs="?", const="today", metavar="YYYY-MM-DD",
        help=(
            "Vide la mémoire anti-répétition pour la date donnée (ou aujourd'hui si absent). "
            "Exemple : --flush-used-articles 2026-04-25"
        ),
    )

    args = parser.parse_args()







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
        if args.date:
            try:
                check_date = Date.fromisoformat(args.date)
            except ValueError:
                print(f"❌ Format de date invalide : '{args.date}'. Attendu : YYYY-MM-DD", file=sys.stderr)
                sys.exit(1)
        else:
            check_date = datetime.now(FREINAGE_TZ).date()

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

    now_freinage = datetime.now(FREINAGE_TZ)
    heure_paris = _now_paris_str("%Hh%M")
    print(f"🕐 Heure locale Freinage : {_date_fr(now_freinage.date())} — {now_freinage.strftime('%H:%M')} (UTC{now_freinage.strftime('%z')[:3]}:{now_freinage.strftime('%z')[3:]})")

    edition = args.edition or _detect_edition()
    print(f"📻  Édition : {edition.upper()}")

    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"❌ Format de date invalide : '{args.date}'. Attendu : YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
    else:
        target_date = now_freinage.date()

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

    # Générer un titre accrocheur via LLM
    catchy_title = _generate_catchy_title(items, edition, date_str) if items else f"L'actualité du Freinage — {date_str}, édition du {edition}"
    print(f"🎯 Titre accrocheur : {catchy_title}")
    
    # Générer un teaser accrocheur via LLM
    teaser = _generate_teaser(items, edition, date_str) if items else f"Découvrez l'actualité du freinage du {date_str}"
    print(f"🎣 Teaser : {teaser}")
    
    # Exporter pour utilisation par update_rss.py
    os.environ["CATCHY_TITLE"] = catchy_title
    os.environ["TEASER"] = teaser

    segments_madelaine = build_segments(
        items, date_str, weather, sources,
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
            tag = "INTRO" if i == 0 else "OUTRO" if i == len(segs) - 1 else f"SEGMENT {i}"
            print(f"\n  ── {tag} ──")
            print(f"  {seg.strip()}")
        print(f"\n  Texte brut (séparateurs inclus) :")
        print(f"\n{SEG_SEPARATOR}\n".join(segs))
        print("══════════════════════════════════════════════════════════\n")

    if args.verbose:
        _print_segments(segments_madelaine, "SORTIE MADELAINE (brut)")

    # Étape 2b — Révision stylistique
    segments = segments_madelaine
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

    if args.verbose:
        _print_segments(segments, "SORTIE ANCRAGE LOCAL (final)")
    else:
        print("\n── Script final (après ancrage) ────────────────────────")
        for i, seg in enumerate(segments):
            label = "INTRO" if i == 0 else "OUTRO" if i == len(segments) - 1 else f"SEGMENT {i}"
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

    # Sauvegarder les métadonnées dans un JSON (titre, teaser, texte)
    if items and args.output:
        json_output_path = args.output.with_suffix('.json')
        metadata = {
            "titre": catchy_title,
            "teaser": teaser,
            "texte": "\n\n---\n\n".join(segments)
        }
        json_output_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"💾 Métadonnées sauvegardées → {json_output_path}")

    # Étape 2d — Classification tonale
    tones = classify_tones(segments)
    _k0 = 0
    if weather is not None: _k0 += 1

    if args.verbose:
        print("\n══════════════════════════════════════════════════════════")
        print("  VERBOSE — TONALITÉS PAR SEGMENT")
        print("══════════════════════════════════════════════════════════")
        for i, (tone, seg) in enumerate(zip(tones, segments)):
            label = "INTRO" if i == 0 else "OUTRO" if i == len(segments) - 1 else f"SEG {i}"
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
        keep_segments=False,
    )

    # Sauvegarde anti-répétition
    if items:
        save_used_titles(target_date, [it["title"] for it in items])

    title      = f"L'actualité du Freinage — {date_str}, édition du {edition}"
    intro_text = segments[0].strip() if segments else ""

    headlines = "\n".join(f"• {item['title']}" for item in items)
    sources_line = " | ".join(sources) if sources else "médias locaux"
    description = (
        f"Flash info du {date_str} — l'essentiel de l'actualité à Freinage en moins de 2 minutes.\n\n"
        f"Au programme :\n{headlines}\n\n"
        f"Informations issues de : {sources_line}"
    )
    # ── Podcast RSS ───────────────────────────────────────────────────────────
    # Utiliser l'URL GitHub Pages pour le fichier audio
    podcast_audio_url = f"https://famibelle.github.io/FlashInfoAstemo/audio/{output_path.name}"
    if podcast_audio_url:
        _update_podcast_rss(
            rss_path=PODCAST_RSS_PATH,
            channel_title="L'actualité du Freinage",
            channel_desc="Flash info de Freinage — matin, midi et soir par Botiran",
            episode_title=title,
            episode_desc=intro_text,
            audio_url=podcast_audio_url,
            audio_size=output_path.stat().st_size,
            duration_s=0,
            guid=output_path.stem,
            pub_date=datetime.utcnow(),
        )
        print(f"   📻 podcast.xml mis à jour → {podcast_audio_url}")
    else:
        print("   ⚠️  podcast.xml non mis à jour (aucune URL audio disponible)")

    print(f"\n✅ Flash info terminé : {output_path}")


if __name__ == "__main__":
    main()
