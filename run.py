import os
import subprocess
import shutil

nb = 200 # Nombre de vidéos à créer
sf = 103  # Nombre de vidéos déjà créées

for i in range(sf, nb):
    subprocess.run(['python3', 'Bot.py'], check=True)
    os.rename('output_with_audio.mp4', f'vidéo_n° {i + 1}.mp4')
    shutil.move(f"vidéo_n° {i + 1}.mp4", "vidéos/")