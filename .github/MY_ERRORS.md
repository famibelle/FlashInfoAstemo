# 📝 Registre des erreurs - Auto-analyse pour amélioration

> **Objectif :** Éviter de répéter les mêmes erreurs et améliorer la qualité des propositions.
> **Dernière mise à jour :** 18 mai 2026

---

## 📊 **Statistiques des erreurs**

| Type d'erreur | Occurrences | Cause principale | Statut |
|---------------|-------------|------------------|--------|
| Git (conflits/rebase) | 5+ | Mauvaise gestion des branches | ✅ En cours de résolution |
| Variables d'environnement manquantes | 3 | Accès direct sans `.get()` | ✅ Corrigé |
| Fichiers non trouvés | 2 | Chemins incorrects | ✅ Corrigé |
| SyntaxError Python | 1 | F-strings multi-lignes | ✅ Corrigé |
| Import de modules | 2 | Noms avec tirets | ✅ Corrigé |

---

## 🔴 **Erreurs récurrentes et leçons apprises**

---

### **📌 Erreur #1 : Oublier de passer les variables d'environnement**

**Contexte :** 
- Workflow GitHub Actions avec `env:` défini dans une step
- Modification du workflow qui supprime accidentellement la définition de l'env

**Exemple concret :**
- Dans le commit `11b0920`, j'ai **supprimé** `env: MISTRAL_API_KEY_ASTEMO` de la step "Generate Flash Info MP3"
- Résultat : Le script Python ne reçoit plus la clé API

**Leçon apprise :**
- ✅ **Toujours vérifier** que les variables critiques (`MISTRAL_API_KEY_ASTEMO`, etc.) sont bien passées
- ✅ **Ne pas modifier** la structure des steps sans vérifier l'impact
- ✅ **Tester mentalement** : "Est-ce que le script a bien accès à toutes ses dépendances ?"

**Solution appliquée :**
```yaml
- name: Generate Flash Info MP3
  env:
    MISTRAL_API_KEY_ASTEMO: ${{ secrets.MISTRAL_API_KEY_ASTEMO }}  # ← Ne JAMAIS supprimer
  run: python flash-info-astemo.py ...
```

---

### **📌 Erreur #2 : Accès direct à os.environ sans fallback**

**Contexte :**
- Code Python utilisant `os.environ["VAR"]` au lieu de `os.environ.get("VAR")`
- Crash avec `KeyError` si la variable n'est pas définie

**Exemple concret :**
- Ligne 56 : `MISTRAL_API_KEY_ASTEMO = os.environ["MISTRAL_API_KEY_ASTEMO"]`
- Résultat : Crash si la clé n'est pas dans les secrets

**Leçon apprise :**
- ✅ **TOUJOURS** utiliser `.get()` pour les variables d'environnement
- ✅ **TOUJOURS** ajouter une vérification explicite + message d'erreur clair
- ✅ **Ne JAMAIS** utiliser l'accès direct `[]` sans fallback

**Solution appliquée :**
```python
MISTRAL_API_KEY_ASTEMO = os.environ.get("MISTRAL_API_KEY_ASTEMO")
if not MISTRAL_API_KEY_ASTEMO:
    raise RuntimeError("❌ La variable MISTRAL_API_KEY_ASTEMO est manquante")
```

---

### **📌 Erreur #3 : Problèmes Git récurrents**

**Contexte :**
- Workflow qui push sans synchronisation préalable
- Exécutions concurrentes non gérées
- `git rebase` après génération de fichiers (unstaged changes)

**Exemples concrets :**
1. `cannot pull with rebase: You have unstaged changes` → Rebase après génération
2. `divergent branches` → Deux workflows en même temps
3. `non-fast-forward` → Histoire non synchronisée

**Leçons apprises :**
- ✅ **Toujours** synchroniser (`git fetch + git rebase`) **AVANT** de générer des fichiers
- ✅ **Toujours** utiliser `concurrency: cancel-in-progress: true` pour éviter les exécutions simultanées
- ✅ **Ne JAMAIS** faire `git reset --hard` (dangereux)
- ✅ **Toujours** vérifier `git status` avant de commiter

**Solutions appliquées :**
```yaml
jobs:
  job:
    concurrency:
      group: flash-info-generator
      cancel-in-progress: true
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: git fetch origin && git rebase origin/main
      - run: python generate.py
      - run: git add . && git commit && git push
```

---

### **📌 Erreur #4 : Import de modules avec noms non standard**

**Contexte :**
- Fichier Python nommé `flash-info-astemo.py` (avec tiret)
- Impossible d'importer directement avec `import flash-info-astemo`

**Exemple concret :**
- `from flash_info_astemo import ...` → `ModuleNotFoundError`

**Leçon apprise :**
- ✅ **Anticiper** les problèmes d'import pour les fichiers avec tirets
- ✅ Utiliser `importlib.util` ou `runpy.run_path()` pour charger ces modules
- ✅ **TOUJOURS** vérifier que le `sys.path` contient le répertoire parent

**Solution appliquée :**
```python
import runpy
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
module = runpy.run_path(str(project_root / "flash-info-astemo.py"))
```

---

### **📌 Erreur #5 : F-strings multi-lignes non supportées**

**Contexte :**
- Utilisation de f-strings avec sauts de ligne en Python
- `SyntaxError: unterminated string literal`

**Exemple concret :**
```python
def generate_rss():
    return f'<?xml version="1.0"?>
<rss>...</rss>'  # ❌ Erreur de syntaxe
```

**Leçon apprise :**
- ✅ **Les f-strings ne supportent PAS les sauts de ligne**
- ✅ Utiliser des **parenthèses** pour les f-strings multi-lignes
- ✅ Ou utiliser des **chaînes concaténées**

**Solution appliquée :**
```python
# Option 1: Parentheses
f(
    '<?xml version="1.0"?>\n'
    '<rss>...</rss>'
)

# Option 2: Chaînes concaténées (choisie)
(
    '<?xml version="1.0"?>\n'
    '<rss>...</rss>'
)
```

---

## 🛡️ **Checklist avant de proposer du code**

### **✅ Pour le code Python**
- [ ] Les variables d'environnement sont-elles accédées avec `.get()` ?
- [ ] Les imports fonctionnent-ils avec les noms de fichiers réels ?
- [ ] Les f-strings multi-lignes utilisent-elles des parenthèses ou des chaînes concaténées ?
- [ ] Les fichiers/répertoires existent-ils avant d'être utilisés ?
- [ ] Les exceptions sont-elles gérées avec des messages clairs ?

### **✅ Pour les workflows GitHub Actions**
- [ ] `concurrency` est-il présent pour éviter les exécutions simultanées ?
- [ ] `permissions: contents: write` est-il déclaré ?
- [ ] La synchronisation Git (`fetch` + `rebase`) est-elle **AVANT** la génération de fichiers ?
- [ ] Toutes les variables d'environnement sont-elles bien passées ?
- [ ] `fetch-depth: 0` est-il utilisé pour le checkout ?

### **✅ Pour les scripts bash**
- [ ] Les commandes critiques ont-elles `|| exit 1` ?
- [ ] Les variables sont-elles vérifiées avant utilisation ?
- [ ] Les chemins sont-ils absolus ou relatifs au bon répertoire ?

---

## 📈 **Améliorations mises en place**

| Date | Amélioration | Impact |
|------|--------------|--------|
| 17/05 | `.get()` pour les env vars | Évite les KeyError |
| 17/05 | `concurrency` dans les workflows | Évite les conflits |
| 17/05 | Sync Git avant génération | Évite les unstaged changes |
| 17/05 | `importlib`/`runpy` pour les modules | Évite ModuleNotFoundError |
| 17/05 | Chaînes concaténées | Évite SyntaxError |
| 18/05 | Restauration de l'env MISTRAL_API_KEY | Corrigé le bug actuel |

---

## 🎯 **Objectifs futurs**

1. **Zéro erreur Git** dans les workflows
2. **Zéro crash silencieux** (toujours des messages clairs)
3. **Code robuste** (toujours des fallbacks)
4. **Propositions vérifiées** (tester mentalement avant de committer)

---

**📌 Note :** Ce fichier est mis à jour après chaque erreur pour éviter de la répéter.
