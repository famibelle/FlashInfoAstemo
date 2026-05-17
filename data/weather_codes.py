"""Codes météorologiques WMO (World Meteorological Organization) → description française.

Utilisé pour traduire les codes renvoyés par l'API Open-Meteo en texte lisible
pour le bulletin radio.
"""

WMO_CODES = {
    0: "ciel dégagé", 1: "principalement dégagé", 2: "partiellement nuageux", 3: "couvert",
    45: "brouillard", 48: "brouillard givrant",
    51: "bruine légère", 53: "bruine modérée", 55: "bruine dense",
    61: "pluie légère", 63: "pluie modérée", 65: "pluie forte",
    80: "averses légères", 81: "averses modérées", 82: "averses violentes",
    95: "orage", 96: "orage avec grêle", 99: "orage violent avec grêle",
}
