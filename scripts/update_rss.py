#!/usr/bin/env python3
"""Script pour générer le flux RSS podcast à partir des fichiers audio et JSON dans docs/audio/."""

import os
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime


def get_audio_duration(audio_path: Path) -> float:
    """Récupère la durée du fichier audio en secondes via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def parse_filename(filename: str) -> dict:
    """Parse le nom de fichier pour extraire date et édition.
    Format attendu : flash-info-astemo-YYYYMMDD-EDITION.mp3 ou .json
    """
    parts = filename.replace('.mp3', '').replace('.json', '').split('-')
    if len(parts) >= 4:
        date_str = parts[-2]
        edition = parts[-1]
        try:
            date_obj = datetime.strptime(date_str, '%Y%m%d')
            return {
                'date_str': date_str,
                'edition': edition,
                'date_obj': date_obj,
                'filename': filename
            }
        except ValueError:
            pass
    return None


def load_metadata(json_path: Path) -> dict:
    """Charge les métadonnées depuis le fichier JSON."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"titre": "", "teaser": "", "texte": ""}


def generate_rss(episodes: list[dict]) -> str:
    """Génère le contenu XML du RSS à partir des épisodes."""
    items_xml = []
    for ep in episodes:
        mins, secs = divmod(int(ep['duration_s']), 60)
        duration_str = f"{mins:02d}:{secs:02d}"
        pub_date = ep['pub_date'].strftime('%a, %d %b %Y %H:%M:%S +0000')
        
        item = (
            f"    <item>\n"
            f"      <title>{ep['titre']}</title>\n"
            f"      <description><![CDATA[{ep['teaser']}]]></description>\n"
            f"      <pubDate>{pub_date}</pubDate>\n"
            f"      <enclosure url=\"{ep['audio_url']}\" length=\"{ep['audio_size']}\" type=\"audio/mpeg\"/>\n"
            f"      <guid isPermaLink=\"false\">{ep['guid']}</guid>\n"
            f"      <itunes:duration>{duration_str}</itunes:duration>\n"
            f"    </item>"
        )
        items_xml.append(item)
    
    items_block = "\n\n".join(items_xml)
    
    artwork = "https://famibelle.github.io/FlashInfoAstemo/artwork.jpg"
    
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">\n'
        '  <channel>\n'
        '    <title>L\'actualité du Freinage</title>\n'
        '    <link>https://famibelle.github.io/FlashInfoAstemo/</link>\n'
        '    <description>L\'actualité du Freinage — matin, midi et soir par MadelAIne</description>\n'
        '    <language>fr</language>\n'
        '    <copyright>© Botiran</copyright>\n'
        '    <itunes:author>Botiran</itunes:author>\n'
        '    <itunes:owner>\n'
        '      <itunes:name>Botiran</itunes:name>\n'
        '      <itunes:email>medhi.famibelle@outlook.fr</itunes:email>\n'
        '    </itunes:owner>\n'
        f'    <itunes:image href="{artwork}"/>\n'
        '    <image>\n'
        f'      <url>{artwork}</url>\n'
        '      <title>L\'actualité du Freinage</title>\n'
        '      <link>https://famibelle.github.io/FlashInfoAstemo/</link>\n'
        '    </image>\n'
        '    <itunes:category text="News">\n'
        '      <itunes:category text="Daily News"/>\n'
        '    </itunes:category>\n'
        '    <itunes:explicit>no</itunes:explicit>\n\n'
        f'{items_block}\n\n'
        '  </channel>\n'
        '</rss>'
    )
    return rss


def main():
    audio_dir = Path('docs/audio')
    rss_path = Path('docs/podcast.xml')
    
    if not audio_dir.exists():
        print(f"❌ Dossier {audio_dir} introuvable")
        sys.exit(1)
    
    # Lister tous les fichiers MP3
    mp3_files = sorted(audio_dir.glob('flash-info-astemo-*.mp3'), reverse=True)
    
    if not mp3_files:
        print("❌ Aucun fichier MP3 trouvé dans docs/audio/")
        sys.exit(1)
    
    episodes = []
    for mp3_path in mp3_files:
        # Trouver le JSON correspondant
        json_path = mp3_path.with_suffix('.json')
        
        # Parser le nom de fichier
        parsed = parse_filename(mp3_path.name)
        if not parsed:
            print(f"⚠️  Fichier non conforme : {mp3_path.name}")
            continue
        
        # Charger les métadonnées
        metadata = load_metadata(json_path) if json_path.exists() else {}
        
        # Calculer durée et taille
        duration_s = get_audio_duration(mp3_path)
        audio_size = mp3_path.stat().st_size
        
        # Construire l'URL
        audio_url = f'https://famibelle.github.io/FlashInfoAstemo/audio/{mp3_path.name}'
        
        episode = {
            'titre': metadata.get('titre', f"L'actualité du Freinage — {parsed['date_str']}"),
            'teaser': metadata.get('teaser', f"Épisode du {parsed['date_str']} — édition {parsed['edition']}"),
            'audio_url': audio_url,
            'audio_size': audio_size,
            'duration_s': duration_s,
            'pub_date': parsed['date_obj'],
            'guid': f"flash-info-astemo-{parsed['date_str']}-{parsed['edition']}"
        }
        episodes.append(episode)
        print(f"✅ Épisode trouvé : {parsed['date_str']}-{parsed['edition']} ({duration_s:.0f}s)")
    
    # Générer le RSS
    rss_content = generate_rss(episodes)
    rss_path.parent.mkdir(parents=True, exist_ok=True)
    rss_path.write_text(rss_content, encoding='utf-8')
    print(f"📻 RSS mis à jour → {rss_path} ({len(episodes)} épisodes)")


if __name__ == '__main__':
    main()
