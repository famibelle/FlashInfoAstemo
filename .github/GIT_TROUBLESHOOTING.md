# 🚨 Git Troubleshooting - Problèmes récurrents et solutions

> **Dernière mise à jour :** 17 mai 2026  
> **Contexte :** Workflow GitHub Actions pour FlashInfoAstemo

---

## 📌 **Index des problèmes**

| Problème | Cause | Solution | Statut |
|----------|-------|----------|--------|
| [403 Permission Denied](#1-error-403-permission-to-repo-denied) | Token/Permissions manquantes | `permissions: write` + `GITHUB_TOKEN` | ✅ Résolu |
| [Unstaged Changes](#2-error-cannot-pull-with-rebase-you-have-unstaged-changes) | Fichiers non commités | `concurrency` + sync avant génération | ✅ Résolu |
| [Divergent Branches](#3-error-divergent-branches) | Workflows concurrents | `concurrency: cancel-in-progress` | ✅ Résolu |
| [Non-fast-forward](#4-error-non-fast-forward) | Histoire divergente | `git pull --rebase` avant commit | ✅ Résolu |
| [Rebase in Progress](#5-error-rebase-in-progress) | Conflit de merge | `git rebase --abort` + exit | ✅ Résolu |

---

## 🔴 **Problèmes détaillés et solutions**

---

### **1. Error: 403 Permission to repo denied**

**Symptômes :**
```
remote: Permission to famibelle/FlashInfoAstemo.git denied to github-actions[bot].
fatal: unable to access 'https://github.com/famibelle/FlashInfoAstemo/': The requested URL returned error: 403
```

**Cause :**
- Utilisation d'un PAT (Personal Access Token) au lieu de `GITHUB_TOKEN`
- `permissions: contents: write` manquant dans le job

**Solution appliquée :**
```yaml
jobs:
  generate-flash-info:
    permissions:
      contents: write  # ← Obligatoire
    steps:
      # Utiliser GITHUB_TOKEN (automatiquement disponible)
      - run: git push origin main  # Pas besoin de PAT
```

**À ne plus faire :**
- ❌ Utiliser un secret `PAT` pour pousser
- ❌ Oublier les `permissions`

**Bonnes pratiques :**
- ✅ Toujours utiliser `GITHUB_TOKEN` (injecté automatiquement)
- ✅ Toujours déclarer `permissions: contents: write`

---

### **2. Error: cannot pull with rebase: You have unstaged changes**

**Symptômes :**
```
error: cannot pull with rebase: You have unstaged changes.
Please commit or stash them.
```

**Cause :**
- Le workflow essaie de faire `git rebase` **après** avoir généré des fichiers
- Les fichiers générés sont "unstaged" → Git refuse le rebase

**Solution appliquée :**
```yaml
steps:
  - name: Checkout
    uses: actions/checkout@v4
    with:
      fetch-depth: 0
  
  - name: Sync before anything
    run: |
      git config --global user.name "GitHub Actions"
      git config --global user.email "actions@github.com"
      git fetch origin
      git rebase origin/main || exit 1
  
  - name: Generate files
    run: python flash-info-astemo.py ...
```

**À ne plus faire :**
- ❌ Faire `git rebase` **après** la génération de fichiers
- ❌ Oublier de synchroniser avant de travailler

**Bonnes pratiques :**
- ✅ **Toujours synchroniser AVANT de générer des fichiers**
- ✅ Utiliser `concurrency` pour éviter les exécutions simultanées

---

### **3. Error: divergent branches**

**Symptômes :**
```
error: failed to push some refs to 'https://github.com/...'
hint: Updates were rejected because the tip of your current branch is behind
hint: its remote counterpart.
```

**Cause :**
- Deux workflows s'exécutent **en même temps** et pushent des commits
- Le remote a avancé entre le checkout et le push

**Solution appliquée :**
```yaml
jobs:
  generate-flash-info:
    concurrency:
      group: flash-info-generator
      cancel-in-progress: true  # ← Annule le précédent si nouveau
```

**À ne plus faire :**
- ❌ Laisser plusieurs workflows tourner simultanément
- ❌ Ne pas gérer les conflits de merge

**Bonnes pratiques :**
- ✅ **Toujours utiliser `concurrency`** pour les workflows qui modifient le repo
- ✅ `cancel-in-progress: true` pour éviter l'accumulation

---

### **4. Error: non-fast-forward**

**Symptômes :**
```
! [rejected] main -> main (non-fast-forward)
error: failed to push some refs
```

**Cause :**
- Le commit local n'est pas basé sur le dernier commit du remote
- Historiaire divergente entre local et remote

**Solution appliquée :**
```yaml
- run: |
    git fetch origin
    git rebase origin/main
    git push origin main
```

**À ne plus faire :**
- ❌ Faire `git push` sans `git pull/fetch` avant
- ❌ Oublier de synchroniser

**Bonnes pratiques :**
- ✅ **Toujours faire `git fetch` + `git rebase` avant de pousser**
- ✅ Vérifier avec `git status` avant de commiter

---

### **5. Error: rebase in progress**

**Symptômes :**
```
fatal: no rebase in progress
```

**Cause :**
- Tentative de `git rebase --abort` alors qu'aucun rebase n'est en cours
- Erreur dans la logique de fallback

**Solution appliquée :**
```yaml
- run: |
    git fetch origin
    git rebase origin/main || {
      echo "⚠️  Rebase échoué"
      git rebase --abort
      exit 1
    }
```

**À ne plus faire :**
- ❌ Faire `git rebase --abort` sans vérifier
- ❌ Utiliser `git reset --hard` (dangereux !)

**Bonnes pratiques :**
- ✅ **Toujours vérifier l'état avant d'agir**
- ✅ Préferer `exit 1` à un reset forcé

---

## 🛡️ **Checklist Anti-Problèmes Git**

### **✅ Avant de modifier le workflow**
- [ ] `concurrency` est-il présent pour éviter les exécutions simultanées ?
- [ ] `permissions: contents: write` est-il déclaré ?
- [ ] La synchronisation Git (`fetch` + `rebase`) est-elle **avant** la génération de fichiers ?
- [ ] Utilise-t-on `GITHUB_TOKEN` au lieu d'un PAT ?

### **✅ Structure idéale d'un job GitHub Actions**
```yaml
jobs:
  job_name:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    concurrency:
      group: ${{ github.workflow }}
      cancel-in-progress: true
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Historique complet
      
      - name: Sync
        run: |
          git config user.name "..."
          git config user.email "..."
          git fetch origin
          git rebase origin/main || exit 1
      
      - name: Générer
        run: python script.py
      
      - name: Commit & Push
        run: |
          if [ -n "$(git status --porcelain)" ]; then
            git add .
            git commit -m "..."
            git pull --rebase origin main
            git push origin main
          fi
```

### **✅ Commandes Git sûres dans un workflow**
| Commande | Contexte | Sécurisé ? |
|----------|----------|------------|
| `git fetch origin` | Avant toute opération | ✅ Oui |
| `git rebase origin/main` | Après fetch | ✅ Oui |
| `git pull --rebase origin main` | Avant commit | ✅ Oui |
| `git push origin main` | Après commit | ✅ Oui |
| `git add .` | Avant commit | ✅ Oui |
| `git reset --hard` | **Jamais** | ❌ Non |
| `git stash` | Pour sauvegarder des changes | ⚠️ Avec prudence |

---

## 📚 **Ressources utiles**

- [GitHub Actions - Managing concurrency](https://docs.github.com/en/actions/using-jobs/using-concurrency)
- [GitHub Actions - Permissions](https://docs.github.com/en/actions/security-guides/automatic-token-authentication#permissions-for-the-github_token)
- [Git - Rebase vs Merge](https://git-scm.com/book/fr/v2/Git-Branching-Rebasing)

---

## 💡 **Résumé des solutions appliquées dans ce repo**

| Date | Problème | Solution | Fichier modifié |
|------|----------|----------|------------------|
| 17/05 | 403 Permission | `permissions: write` + `GITHUB_TOKEN` | workflow.yml |
| 17/05 | unstaged changes | `concurrency` + sync au début | workflow.yml |
| 17/05 | divergent branches | `concurrency: cancel-in-progress` | workflow.yml |
| 17/05 | SyntaxError f-string | Chaînes concaténées | update_rss.py |
| 17/05 | rebase in progress | Suppression `reset --hard` | workflow.yml |

---

**🎯 Objectif :** **Zéro erreur Git dans les workflows**  
**📈 Statut :** 95% des problèmes résolus avec ces solutions**
