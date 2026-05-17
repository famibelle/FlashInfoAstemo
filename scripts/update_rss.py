#!/usr/bin/env python3
"""Script pour mettre à jour le flux RSS avec un nouvel épisode."""

import os
import sys
from pathlib import Path
from datetime import datetime

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flash_info_astemo import _update_podcast_rss

def main():
    date_str = os.environ.get('DATE', datetime.utcnow().strftime('%Y%m%d'))
    
    now = datetime.utcnow()
    date_formatted = now.strftime('%A %d %B %Y')
    
    audio_url = f'https://famibelle.github.io/FlashInfoAstemo/audio/flash-info-astemo-{date_str}-matin.mp3'
    file_path = Path(f'docs/audio/flash-info-astemo-{date_str}-matin.mp3')
    
    if not file_path.exists():
        print(f'ERREUR: Fichier non trouvé: {file_path}')
        sys.exit(1)
    
    _update_podcast_rss(
        rss_path=Path('docs/podcast.xml'),
        channel_title='Freinage — Flash Info',
        channel_desc='Flash info de Freinage — matin, midi et soir par Madelaine',
        episode_title=f'Flash Info Freinage — {date_formatted}, édition du matin',
        episode_desc=f'Flash info du {now.strftime("%Y-%m-%d")} — l essentiel de l actualité du freinage en moins de 2 minutes.',
        audio_url=audio_url,
        audio_size=file_path.stat().st_size,
        duration_s=0,
        guid=f'flash-info-astemo-{date_str}-matin',
        pub_date=now,
    )
    print('✅ podcast.xml mis à jour avec le nouvel épisode')

if __name__ == '__main__':
    main()
