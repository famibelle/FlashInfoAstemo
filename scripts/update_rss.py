#!/usr/bin/env python3
"""Script pour mettre à jour le flux RSS avec un nouvel épisode."""

import os
import sys
import subprocess
import runpy
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

# Ajouter le répertoire parent au path pour que data/ soit accessible
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Définir la variable d'environnement requise (même vide) pour éviter l'erreur
os.environ.setdefault("MISTRAL_API_KEY_ASTEMO", "")

# Charger le module principal (nom avec tiret) via runpy
flash_info_astemo = runpy.run_path(str(project_root / "flash-info-astemo.py"))
_update_podcast_rss = flash_info_astemo['_update_podcast_rss']

def main():
    date_str = os.environ.get('DATE', datetime.utcnow().strftime('%Y%m%d'))
    catchy_title = os.environ.get('CATCHY_TITLE', f'L actualite du Freinage - {datetime.utcnow().strftime("%Y-%m-%d")}, edition du matin')
    teaser = os.environ.get('TEASER', f'Découvrez l actualité du freinage du {datetime.utcnow().strftime("%Y-%m-%d")}')
    
    now = datetime.utcnow()
    date_formatted = now.strftime('%A %d %B %Y')
    
    audio_url = f'https://famibelle.github.io/FlashInfoAstemo/audio/flash-info-astemo-{date_str}-matin.mp3'
    file_path = Path(f'docs/audio/flash-info-astemo-{date_str}-matin.mp3')
    
    if not file_path.exists():
        print(f'ERREUR: Fichier non trouvé: {file_path}')
        sys.exit(1)
    
    # Calculer la durée du fichier audio
    duration_s = get_audio_duration(file_path)
    print(f"⏱️  Durée audio : {duration_s:.1f}s")
    
    _update_podcast_rss(
        rss_path=Path('docs/podcast.xml'),
        channel_title='L\'actualité du Freinage',
        channel_desc='L\'actualité du Freinage - matin, midi et soir par MadelAIne',
        episode_title=catchy_title,
        episode_desc=f'{teaser}',
        audio_url=audio_url,
        audio_size=file_path.stat().st_size,
        duration_s=duration_s,
        guid=f'flash-info-astemo-{date_str}-matin',
        pub_date=now,
    )
    print('✅ podcast.xml mis à jour avec le nouvel épisode')

if __name__ == '__main__':
    main()
