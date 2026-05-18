#!/usr/bin/env python3
"""
Script pour redimensionner docs/artwork.jpg en 3000x3000 pixels, format JPG, RVB.
Nécessite Pillow : pip install pillow
"""

from PIL import Image, ImageOps
import os

# Chemins
input_path = "docs/artwork.jpg"
output_path = "docs/artwork.jpg"  # Écrasera l'origine

# Paramètres Apple Podcasts
TARGET_SIZE = (3000, 3000)
FORMAT = "JPEG"
QUALITY = 95  # Qualité JPG (1-100)

# Vérification
if not os.path.exists(input_path):
    print(f"❌ Erreur : {input_path} introuvable.")
    exit(1)

# Ouverture
img = Image.open(input_path)
print(f"📄 Image originale : {img.size} pixels, mode={img.mode}, format={img.format}")

# Conversion RVB si nécessaire
if img.mode != "RGB":
    img = img.convert("RGB")
    print("🎨 Converti en RVB.")

# Redimensionnement avec padding (pour garder les proportions)
img_resized = ImageOps.fit(img, TARGET_SIZE, method=Image.Resampling.LANCZOS, bleed=0.0, centering=(0.5, 0.5))
print(f"✅ Redimensionné à {TARGET_SIZE} pixels (avec padding si nécessaire).")

# Sauvegarde
img_resized.save(output_path, format=FORMAT, quality=QUALITY)
print(f"💾 Sauvegardé en {FORMAT} (qualité={QUALITY}) : {output_path}")
print("✨ Fait ! Vérifiez le fichier avant de le déployer.")
