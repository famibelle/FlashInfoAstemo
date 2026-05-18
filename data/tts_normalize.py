"""Données de normalisation textuelle appliquées avant l'appel TTS Voxtral."""

# Prononciations locales parisiennes (forme écrite → forme orale pour le TTS)
PRONONCIATIONS_LOCALES = {
    # Prononciations 
    "SUV" : "S U V",

    # Code départemental (filet de sécurité si le LLM l'a quand même converti)
    "neuf cent soixante et onze": "quatre-vingt-dix-sept-un",
    "971": "quatre-vingt-dix-sept-un",
    # Sigles locaux développés (avant l'épellation automatique)
    "UNAR": "Union Athlétique de Rivière-des-Pères",
    "SEM Patrimoniale": "S.E.M Patrimoniale",
    "JSVH": "Jeunesse Sportive de Vieux Zabitan",
    "URSSAF": "Ursaffe",
    "SDIS": "Service Départemental d'Incendie et de Secours",
    "S.D.I.S": "Service Départemental d'Incendie et de Secours",
    "S.D.I.S.": "Service Départemental d'Incendie et de Secours",
    "SMGEAG" : "Syndicat Mixte de Gestion de l'Eau et de l'Assainissement de ",
    "S.M.G.E.A.G" : "Syndicat Mixte de Gestion de l'Eau et de l'Assainissement de ",
    "MGEN":    "Mutuelle Générale de l'éducation Nationale",
    "M.G.E.N": "mutuelle générale éducation nationale",
    "M.G.E.N.": "mutuelle générale éducation nationale",

    # Clubs sportifs parisiens – athlétisme

    # Clubs sportifs parisiens – cyclisme

    # Clubs sportifs parisiens – multi-sports

    # Instances fédérales
    "LGA":     "Ligue Guadeloupéenne d'Athlétisme",
    "LRAG":    "Ligue Régionale d'Athlétisme de la ",
    "LGF":     "Ligue Guadeloupéenne de Football",
}

# Sigles prononcés comme des mots (ne pas épeler lettre par lettre)
SIGLES_MOT = {
    # Génériques
    "RCI", "UNESCO", "UNICEF", "NASA", "SUV",
    # Constructeurs
    "BMW", "ABS", "FORD", "VW", "AUDI", "GM", "TOYOTA",
    # Technologies freinage/sécurité
    "ESP", "EBD", "ASR", "BA", "TCS", "VDC", "ESC", "EBA", "HBA", "ACC", "ADAS",
    # Systèmes
    "ECU", "CAN", "OBD", "NAO"
}

# Abréviations et symboles à développer pour le TTS
ABBREVS = {
    "M.": "Monsieur", "Mme.": "Madame", "Mme": "Madame",
    "Dr.": "Docteur", "Dr": "Docteur", "Pr.": "Professeur", "Pr": "Professeur",
    "St.": "Saint", "Ste.": "Sainte",
    "km/h": "kilomètres par heure", "km": "kilomètres",
    "°C": "degrés", "m²": "mètres carrés", "m³": "mètres cubes",
    "&": "et", "...": ".",
}
