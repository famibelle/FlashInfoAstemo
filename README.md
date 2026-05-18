# MadelAIne - L'actualité du Freinage

> ⚠️ **ATTENTION** : Ne jamais commiter de clés API ou secrets dans ce dépôt. Utilisez **exclusivement** les GitHub Secrets pour les informations sensibles.

---

## 📌 À propos

**MadelAIne** est un bot qui génère automatiquement des **flashs info audio** sur l'actualité du freinage automobile, matin, midi et soir. Le système :
- Collecte les dernières actualités via des flux RSS spécialisés
- Génère un script structuré avec Mistral AI
- Synthétise la voix avec Voxtral TTS (Mistral)
- Publie le podcast sur GitHub Pages et Apple Podcasts

---

## ⚙️ Prérequis

- **Python 3.10+**
- **FFmpeg** (pour le montage audio)
- **Git** (pour les commits automatiques)

### Dépendances Python
```bash
pip install -r requirements.txt
```

### Clés API requises
| Service | Variable d'environnement | Où la configurer |
|---------|-------------------------|------------------|
| Mistral AI (TTS/LLM) | `MISTRAL_API_KEY_ASTEMO` | GitHub Secrets |

> ❌ **JAMAIS** dans le code ou le README. Utilisez **uniquement** [GitHub Secrets](https://github.com/famibelle/FlashInfoAstemo/settings/secrets/actions).

---

## 🚀 Installation

1. **Cloner le dépôt** :
   ```bash
   git clone https://github.com/famibelle/FlashInfoAstemo.git
   cd FlashInfoAstemo
   ```

2. **Installer les dépendances** :
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurer les secrets** :
   - Allez dans **Settings → Secrets → Actions**
   - Ajoutez `MISTRAL_API_KEY_ASTEMO` avec votre clé Mistral

---

## 🎙️ Utilisation

### Génération manuelle
```bash
python flash-info-astemo.py --edition matin --output docs/audio/flash-info-$(date +%Y%m%d)-matin.mp3
```

### Options disponibles
| Option | Description | Exemple |
|--------|-------------|---------|
| `--edition` | matin/midi/soir | `--edition matin` |
| `--date` | Date au format YYYY-MM-DD | `--date 2026-05-20` |
| `--output` | Chemin du fichier MP3 | `--output output.mp3` |
| `--verbose` | Mode détaillé | `--verbose` |

### Mise à jour du RSS
```bash
python scripts/update_rss.py
```

---

## 🤖 GitHub Actions

Le workflow **`daily-flash-info-astemo.yml`** génère automatiquement :
- Un nouveau flash info **tous les matins à 3h UTC** (5h en été, 4h en hiver)
- Push des fichiers vers `docs/audio/` et `docs/podcast.xml`

### Structure du workflow
1. **Sync Git** → Synchronisation avec `origin/main`
2. **Setup** → Installation de Python et dépendances
3. **Génération** → Création du MP3 via `flash-info-astemo.py`
4. **Mise à jour RSS** → Régénération de `podcast.xml` avec le nouvel épisode
5. **Commit & Push** → Publication automatique

> ℹ️ Le workflow utilise `concurrency: cancel-in-progress: true` pour éviter les exécutions simultanées.

---

## 📁 Structure du projet

```
FlashInfoAstemo/
├── docs/
│   ├── audio/              # Fichiers MP3 des épisodes
│   ├── podcast.xml         # Flux RSS du podcast
│   └── index.html          # Page web avec player
├── scripts/
│   ├── update_rss.py       # Générateur du RSS
│   └── ...                 # Autres scripts utilitaires
├── data/
│   └── tts_normalize.py    # Règles de normalisation TTS
├── prompts/                # Prompts pour le LLM
├── archives/               # Archives des flashs info
├── .github/
│   └── workflows/          # Workflows GitHub Actions
└── flash-info-astemo.py    # Script principal
```

---

## 🔧 Configuration

### Fichiers clés à modifier

| Fichier | Rôle |
|---------|------|
| `data/tts_normalize.py` | Ajouter des acronymes (ex: `BMW`, `ABS`) pour éviter l'épellation TTS |
| `prompts/instructions.md` | Personnaliser les instructions du LLM |
| `.github/workflows/daily-flash-info-astemo.yml` | Modifier la planification |

### Ajouter un acronyme (ex: "ESC")
Dans `data/tts_normalize.py` :
```python
SIGLES_MOT = {
    "RCI", "UNESCO", "BMW", "ABS", "ESP", "EBD",  # ...
    "ESC",  # ← Ajout ici
}
```

---

## 📊 Podcast

- **Flux RSS** : `https://famibelle.github.io/FlashInfoAstemo/podcast.xml`
- **Page web** : `https://famibelle.github.io/FlashInfoAstemo/`
- **Apple Podcasts** : [À configurer via Apple Podcasts Connect](https://podcastsconnect.apple.com/)

### Validation Apple Podcasts
Pour être conforme :
- ✅ Artwork 3000×3000px (JPG/PNG, RGB)
- ✅ `<itunes:summary>` (obligatoire)
- ✅ `<itunes:explicit>` (obligatoire par item)
- ✅ `<itunes:keywords>` (recommandé)
- ✅ Catégorie définie

---

## 🛡️ Bonnes pratiques

### ❌ À NE JAMAIS FAIRE
- **Commiter des clés API** dans le code ou le README
- **Utiliser un PAT** (Personal Access Token) → Préférer `GITHUB_TOKEN`
- **Oublier `concurrency`** dans les workflows (risque de conflits Git)
- **Faire `git push` sans `git pull --rebase`** avant

### ✅ À TOUJOURS FAIRE
- **Utiliser GitHub Secrets** pour les clés API
- **Vérifier `git status`** avant de commiter
- **Tester localement** avant de pousser
- **Lire `.github/GIT_TROUBLESHOOTING.md`** en cas d'erreur Git

---

## 🤝 Contribuer

1. Fork le projet
2. Crée une branche (`git checkout -b feature/xxx`)
3. Commit tes modifications (`git commit -m "feat: ..."`)
4. Push vers ta branche (`git push origin feature/xxx`)
5. Ouvre une Pull Request

---

## 📄 Licence

© Botiran - [MIT](LICENSE)
