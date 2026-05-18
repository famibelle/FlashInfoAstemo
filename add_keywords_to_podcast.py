#!/usr/bin/env python3
"""
Script pour ajouter les mots-clés (itunes:keywords) aux épisodes existants de podcast.xml
à partir des fichiers JSON dans docs/audio/.

Utilisation : python3 add_keywords_to_podcast.py
"""

import json
import re
from pathlib import Path

# Chemins
JSON_DIR = Path("docs/audio")
RSS_PATH = Path("docs/podcast.xml")

# Mots à exclure (stop words français + termes génériques)
STOP_WORDS = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "à", "au", "aux",
    "pour", "par", "sur", "dans", "avec", "sans", "plus", "mais", "donc", "or", "ni", "car",
    "ce", "cette", "ces", "qui", "que", "dont", "où", "se", "ne", "pas", "si", "comme",
    "est", "sont", "a", "ont", "était", "étaient", "sera", "seront",
    "l", "d", "j", "m", "n", "s", "t", "y", "c",
    "actualité", "info", "news", "matin", "midi", "soir", "édition",
    "voici", "bonjour", "bonsoir", "toutes", "tous", "vous", "nous", "ils", "elles",
    "cette", "cet", "ces", "son", "sa", "ses", "leur", "leurs", "notre", "nos",
    "côté", "segment", "voilà", "sources", "issu", "issus", "issue",
    "prêt", "prêts", "prête", "découvrez", "programme", "aujourd", "hui",
    "frein", "sommes", "écoutez", "votre", "tour", "horizon", "industrie", "mobilité",
    "parti", "programme", "essentiel", "moins", "minutes", "freinage", "jour",
    "demain", "nouvelle", "édition", "bonne", "journée", "soirée",
}

# Mots techniques prioritaires (freinage automobile) - ensemble pour test rapide
TECHNICAL_TERMS = {
    "subaru", "ford", "bmw", "mercedes", "lamborghini", "daimler", "toyota", "nissan",
    "marelli", "pailton", "jlm", "brembo", "abs", "esp", "nao",
    "disque", "plaquette", "étrier", "garniture", "freinage", "suspension", "direction",
    "simulateur", "météo", "température", "pluie", "vent", "course",
    "constructeur", "aftermarket", "réparation", "entretien", "nettoyage",
    "composant", "pièce", "système", "technologie", "innovation", "modèle",
    "véhicule", "voiture", "camion", "poids", "lourd", "léger", "hybride",
    "électrique", "thermique", "régénératif", "dynamique", "modulation",
    "effort", "fade", "usure", "durabilité", "stabilité", "sécurité",
    "test", "essai", "développement", "prototypage", "conception",
    "marché", "vente", "prix", "coût", "garantie", "client", "atelier",
    "maintenance", "contrôle", "performance", "puissance",
    "confort", "conducteur", "route", "piste", "franchissement", "virage",
    "accélération", "décélération", "transfert", "masse", "algorithme",
    "électronique", "hydraulique", "mécanique", "pédale",
}


def extract_keywords(text: str) -> str:
    """Extrait les mots-clés pertinents d'un texte et retourne une chaîne séparée par des virgules."""
    # Extraire uniquement le contenu entre les séparateurs --- (le corps de l'article)
    # Diviser par --- et prendre les parties du milieu
    sections = re.split(r'\s*---\s*', text)
    if len(sections) > 2:
        # Prendre toutes les sections entre les --- (safter la première intro)
        content_sections = sections[1:-1]  # Exclure intro et outro
        relevant_text = " ".join(content_sections)
    else:
        # Sinon, prendre tout le texte
        relevant_text = text
    
    # Nettoyer le texte : remplacer les séparateurs spéciaux par des espaces
    relevant_text = relevant_text.replace("—", " ").replace("–", " ").replace("\n", " ")
    relevant_text = re.sub(r'[^\w\sÀ-ÿ-]', ' ', relevant_text)  # Garder lettres, chiffres, espaces et tirets
    
    # Extraire tous les mots (conserver la casse originale)
    words = re.findall(r'[À-ÿA-Za-z0-9-]+', relevant_text)
    
    # Filtrer les mots
    keywords = []
    for word in words:
        lower_word = word.lower()
        # Garder si :
        # 1. C'est un terme technique
        # 2. Ou ce n'est pas un stop word ET le mot fait au moins 4 caractères
        if lower_word in TECHNICAL_TERMS:
            # Garder la casse originale si le mot commence par une majuscule
            if word[0].isupper():
                keywords.append(word)
            else:
                keywords.append(word)
        elif lower_word not in STOP_WORDS and len(word) >= 4:
            keywords.append(word)
    
    # Supprimer les doublons tout en conservant l'ordre
    seen = set()
    unique_keywords = []
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower not in seen:
            seen.add(kw_lower)
            unique_keywords.append(kw)
    
    return ", ".join(unique_keywords[:15])  # Max 15 mots-clés


def main():
    # Lire le RSS existant
    rss_content = RSS_PATH.read_text(encoding="utf-8")
    
    # Trouver tous les items
    item_pattern = re.compile(r'(<item>.*?</item>)', re.DOTALL)
    items = item_pattern.findall(rss_content)
    
    print(f"📄 Trouvé {len(items)} épisodes dans podcast.xml")
    
    # Lire tous les JSON
    json_files = sorted(JSON_DIR.glob("flash-info-astemo-*.json"))
    print(f"📁 Trouvé {len(json_files)} fichiers JSON dans {JSON_DIR}\n")
    
    # Créer un mapping guid -> keywords
    guid_keywords = {}
    for json_file in json_files:
        data = json.loads(json_file.read_text(encoding="utf-8"))
        
        # Extraire le guid depuis le nom de fichier (sans .json)
        guid = json_file.stem  # Ex: flash-info-astemo-20260518-matin
        
        # Extraire les keywords depuis titre + texte
        text_for_keywords = f"{data.get('titre', '')} {data.get('texte', '')}"
        keywords = extract_keywords(text_for_keywords)
        
        if keywords:
            guid_keywords[guid] = keywords
            print(f"  ✅ {guid}: {keywords[:60]}...")
        else:
            print(f"  ⚠️  {guid}: aucun mot-clé trouvé")
    
    # Mettre à jour chaque item dans le RSS
    new_items = []
    for item in items:
        # Extraire le guid
        guid_match = re.search(r'<guid[^>]*>([^<]+)</guid>', item)
        if not guid_match:
            new_items.append(item)
            continue
        
        guid = guid_match.group(1).strip()
        
        if guid in guid_keywords:
            keywords = guid_keywords[guid]
            # Supprimer l'ancienne balise itunes:keywords si elle existe
            item_clean = re.sub(r'\s*<itunes:keywords>.*?</itunes:keywords>\s*\n?', '', item)
            
            # Trouver la position de </item>
            lines = item_clean.rstrip().split('\n')
            # Trouver la dernière ligne (devrait être </item>)
            if lines and lines[-1].strip() == '</item>':
                lines[-1] = f'      <itunes:keywords>{keywords}</itunes:keywords>\n    </item>'
            else:
                lines.append(f'      <itunes:keywords>{keywords}</itunes:keywords>')
                lines.append('    </item>')
            new_item = '\n'.join(lines)
            new_items.append(new_item)
            print(f"  📝 Mots-clés mis à jour pour: {guid}")
        else:
            new_items.append(item)
            print(f"  ⚠️  {guid}: pas de mots-clés (JSON manquant)")
    
    # Reconstruire le RSS
    new_rss = rss_content
    for old_item, new_item in zip(items, new_items):
        new_rss = new_rss.replace(old_item, new_item)
    
    # Sauvegarder
    RSS_PATH.write_text(new_rss, encoding="utf-8")
    print(f"\n✅ podcast.xml mis à jour avec les mots-clés pour {len(new_items)} épisodes !")


if __name__ == "__main__":
    main()
