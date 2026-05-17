"""Données de normalisation textuelle appliquées avant l'appel TTS Voxtral."""

# Prononciations locales guadeloupéennes (forme écrite → forme orale pour le TTS)
PRONONCIATIONS_LOCALES = {
    # Prononciations créoles
    
    "soukouyan": "soukougnan",
    "Piman Bouk" : "piment bouc",
    "bondamanjak" : "bonda ment jacques",
    "Pélikan" : "Pélican",
    "awokasié" : "avokassié",
    "palétuwyé" : "palétuvier",
    "mwen" : "moins",


    "punch": "ponche",
    "Jaden" : "Jadin",
    "Gwoka" : "GroKa",
    "Raizet" : "Rézé",
    "Lyannaj": "Lyanhnage",   # Lyan-naje, deux syllabes distinctes
    "lyannaj": "Lyanhnage",
    "Goyave":          "Gwayave",
    "Vieux-Habitants": "Vieux Zabitan",
    "Vieux Habitants":  "Vieux Zabitan",
    "Delgrès":          "Delgrèsse",   # /dɛl.ɡʁɛs/ — force le s final
    "Henri IV":         "Henri Quatre",
    "Henri 4":          "Henri Quatre",
    "cité Henri IV":    "cité Henri Quatre",
    "cité Henri 4":     "cité Henri Quatre",
    "FEADER" : "Fonds européen agricole pour le développement rural",
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
    "SMGEAG" : "Syndicat Mixte de Gestion de l'Eau et de l'Assainissement de Guadeloupe",
    "S.M.G.E.A.G" : "Syndicat Mixte de Gestion de l'Eau et de l'Assainissement de Guadeloupe",
    "MGEN":    "Mutuelle Générale de l'éducation Nationale",
    "M.G.E.N": "mutuelle générale éducation nationale",
    "M.G.E.N.": "mutuelle générale éducation nationale",
    # Clubs sportifs guadeloupéens – athlétisme
    "ACBM":    "Athlétic Club de Baie-Mahault",
    "ACCBE":   "Athlétic Club de Capesterre-Belle-Eau",
    "ACSA":    "Athlétic Club de Sainte-Anne",
    "ARA":     "Athletic Racing des Abymes",
    "ASAPB":   "Association Sportive Athlétique de Petit-Bourg",
    "ASCKS":   "Association Sportive et Culturelle Kannal Stars de Petit-Canal",
    "ASCSM":   "Avenir Sportif Club de Saint-Martin",
    "BPA":     "Bik Pointois d'Athlétisme de Pointe-à-Pitre",
    "CSM":     "Club Sportif Moulien du Moule",
    "CSP":     "Club Sportif Pointois d'Athlétisme",
    "CSC":     "Club Sportif Capesterrien de Capesterre-Belle-Eau",
    "DAAO":    "D'Arts et d'Actions Olympiques des Abymes",
    "EATG":    "Entente Athlétique Terres de Gwadloup",
    "EMAE":    "Étoile de Morne-à-l'Eau",
    "GAC":     "Gosier Athlétic Club du Gosier",
    "JAM":     "Jeunesse Athlétique Moulienne du Moule",
    "JEFC":    "Jeunesse Évolution Football Club de Baie-Mahault",
    "JSA":     "Jeunesse Sportive Abymienne des Abymes",
    "MCA":     "Monster Club Athlé des Abymes",
    "NGTAC":   "Nord Grande-Terre Athlétic Club de Port-Louis",
    "SS":      "Solidarité Scolaire de Baie-Mahault",
    "USBM":    "Union Sportive de Baie-Mahault",
    "USGB":    "Union Sportive de Grand-Bourg de Marie-Galante",
    "USR Athlé": "Unité Sainte-Rosienne Athlétisme de Sainte-Rose",
    # Clubs sportifs guadeloupéens – cyclisme
    "ACVPB":   "Association Cycliste de Petit-Bourg",
    "APCR":    "Amicale du Personnel du Conseil Régional Cyclotourisme",
    "ASVO":    "Association Sportive Vélo d'Or",
    "CCB":     "Citizen Club de Baillif",
    "CCBT":    "Citizen Club de Basse-Terre",
    "CCSBT":   "Club Cycliste du Sud Basse-Terre",
    "CRCIG":   "Comité Régional de Cyclisme des Îles de Guadeloupe",
    "UCM":     "Union Cycliste Moulienne",
    "VCN":     "Vélo Club du Nord d'Anse-Bertrand",
    "VCTR":    "Vélo Club de Trois-Rivières",
    "VO2C":    "Vélo d'Or du Centre et de la Caraïbe",
    # Clubs sportifs guadeloupéens – multi-sports
    "AOG":     "Association Omnisports Gourbeyrienne de Gourbeyre",
    "CERAL":   "Cercle d'Études, de Recherche et d'Animation du Lamentin",
    "MTC":     "Moule Triathlon Club du Moule",
    # Instances fédérales
    "LGA":     "Ligue Guadeloupéenne d'Athlétisme",
    "LRAG":    "Ligue Régionale d'Athlétisme de la Guadeloupe",
    "LGF":     "Ligue Guadeloupéenne de Football",
}

# Sigles prononcés comme des mots (ne pas épeler lettre par lettre)
SIGLES_MOT = {"RCI", "UNESCO", "UNICEF", "NASA"}

# Abréviations et symboles à développer pour le TTS
ABBREVS = {
    "M.": "Monsieur", "Mme.": "Madame", "Mme": "Madame",
    "Dr.": "Docteur", "Dr": "Docteur", "Pr.": "Professeur", "Pr": "Professeur",
    "St.": "Saint", "Ste.": "Sainte",
    "km/h": "kilomètres par heure", "km": "kilomètres",
    "°C": "degrés", "m²": "mètres carrés", "m³": "mètres cubes",
    "&": "et", "...": ".",
}
