"""Marroniers annuels de Guadeloupe — événements récurrents à date fixe ou variable.

Ne contient PAS les fêtes communales/patronales (gérées dans fetes_patronales.py).
Les dates variables (carnaval, Pâques) sont calculées dynamiquement pour chaque année.
Utiliser `get_marroniers_du_jour(date)` pour obtenir les événements d'une date donnée.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass


# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Marronieur:
    evenement: str
    lieu: str
    categorie: str
    # Pour les dates fixes : "MM-DD", None si variable
    date_debut: str | None = None
    # Pour les événements multi-jours : "MM-DD" de fin (inclus), None sinon
    date_fin: str | None = None
    # Pour les dates variables : clé dans _DATES_VARIABLES, None si fixe
    date_variable: str | None = None
    # Durée en jours pour les événements variables multi-jours
    duree_jours: int = 1


# ── Calcul des dates variables ─────────────────────────────────────────────────


def _paques(year: int) -> datetime.date:
    """Algorithme de Meeus/Jones/Butcher — Pâques grégorien."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return datetime.date(year, month, day + 1)


def _mardi_gras(year: int) -> datetime.date:
    return _paques(year) - datetime.timedelta(days=47)


# Clés disponibles pour date_variable
_DATES_VARIABLES: dict[str, callable] = {
    "samedi_avant_mardi_gras": lambda y: _mardi_gras(y) - datetime.timedelta(days=3),
    "dimanche_gras":           lambda y: _mardi_gras(y) - datetime.timedelta(days=2),
    "lundi_gras":              lambda y: _mardi_gras(y) - datetime.timedelta(days=1),
    "mardi_gras":              lambda y: _mardi_gras(y),
    "mercredi_des_cendres":    lambda y: _mardi_gras(y) + datetime.timedelta(days=1),
    "semaine_apres_paques":    lambda y: _paques(y) + datetime.timedelta(days=7),
}


# ── Catalogue des marroniers ───────────────────────────────────────────────────


MARRONIERS: list[Marronieur] = [
    # ── Janvier ───────────────────────────────────────────────────────────────
    Marronieur(
        evenement="Fête des Grands-Fonds — courses de bœufs tirant et remise de prix",
        lieu="Sainte-Anne",
        categorie="Tradition",
        date_debut="01-01",
    ),
    Marronieur(
        evenement="Fête de Pombiray — grande fête indienne avec processions",
        lieu="Saint-François",
        categorie="Tradition / Religieux",
        date_debut="01-29",
        duree_jours=3,
    ),

    # ── Février ───────────────────────────────────────────────────────────────
    Marronieur(
        evenement="Foire artisanale",
        lieu="Bouillante",
        categorie="Culture",
        date_debut="02-15",
    ),
    Marronieur(
        evenement="Début des parades carnavalesques",
        lieu="Toute l'île",
        categorie="Carnaval",
        date_variable="samedi_avant_mardi_gras",
    ),
    Marronieur(
        evenement="Parade du dimanche gras",
        lieu="Pointe-à-Pitre",
        categorie="Carnaval",
        date_variable="dimanche_gras",
    ),
    Marronieur(
        evenement="Parade carnavalesque du lundi gras",
        lieu="Basse-Terre",
        categorie="Carnaval",
        date_variable="lundi_gras",
    ),
    Marronieur(
        evenement="Fin du carnaval — mercredi des Cendres",
        lieu="Toute l'île",
        categorie="Carnaval",
        date_variable="mercredi_des_cendres",
    ),

    # ── Mars / Avril ──────────────────────────────────────────────────────────
    Marronieur(
        evenement="Fête du crabe — cuisine créole, plages animées",
        lieu="Toute l'île",
        categorie="Gastronomie",
        date_variable="semaine_apres_paques",
        duree_jours=7,
    ),
    Marronieur(
        evenement="Fête du poisson et de la mer",
        lieu="Saint-François",
        categorie="Gastronomie / Culture",
        date_debut="04-01",
    ),
    Marronieur(
        evenement="Journée du crabe",
        lieu="Morne-à-l'Eau",
        categorie="Gastronomie",
        date_debut="04-15",
    ),

    # ── Juin ──────────────────────────────────────────────────────────────────
    Marronieur(
        evenement="Fête de la musique — Place de la Victoire",
        lieu="Pointe-à-Pitre",
        categorie="Culture / Musique",
        date_debut="06-21",
    ),

    # ── Juillet ───────────────────────────────────────────────────────────────
    Marronieur(
        evenement="Festival de Gwoka — animations multiples",
        lieu="Sainte-Anne",
        categorie="Culture",
        date_debut="07-05",
        date_fin="07-14",
    ),

    # ── Août ──────────────────────────────────────────────────────────────────
    Marronieur(
        evenement="Tour cycliste de Guadeloupe",
        lieu="Toute l'île",
        categorie="Sport",
        date_debut="08-06",
        date_fin="08-15",
    ),
    Marronieur(
        evenement="Fête des Cuisinières — défilé en costume traditionnel, dégustation créole",
        lieu="Pointe-à-Pitre",
        categorie="Tradition / Gastronomie",
        date_debut="08-15",
    ),
    Marronieur(
        evenement="Manifestations culturelles de Saint-Barthélemy",
        lieu="Saint-Barthélemy",
        categorie="Culture",
        date_debut="08-22",
    ),

    # ── Décembre ──────────────────────────────────────────────────────────────
    Marronieur(
        evenement="Animations de fin d'année — rues piétonnes et bonnes affaires",
        lieu="Pointe-à-Pitre",
        categorie="Culture",
        date_debut="12-01",
    ),
]


# ── Lookup ─────────────────────────────────────────────────────────────────────


def get_marroniers_du_jour(target_date: datetime.date) -> list[Marronieur]:
    """Retourne les marroniers actifs à la date donnée (début, fin inclus)."""
    year = target_date.year
    result: list[Marronieur] = []

    for m in MARRONIERS:
        if m.date_variable:
            compute = _DATES_VARIABLES.get(m.date_variable)
            if compute is None:
                continue
            debut = compute(year)
            fin = debut + datetime.timedelta(days=m.duree_jours - 1)
        else:
            debut = datetime.date(year, int(m.date_debut[:2]), int(m.date_debut[3:]))
            if m.date_fin:
                fin = datetime.date(year, int(m.date_fin[:2]), int(m.date_fin[3:]))
            else:
                fin = debut + datetime.timedelta(days=m.duree_jours - 1)

        if debut <= target_date <= fin:
            result.append(m)

    return result
