import os
import subprocess

nb = 200
sf = 13  # Nombre de vidéos déjà créées

for i in range(sf, nb):
    subprocess.run(['python3', 'Bot.py'], check=True)
    os.rename('output_with_audio.mp4', f'vidéo_n° {i + 1}.mp4')