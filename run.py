import os
import subprocess

nb = 163

i = 36

for i in range(nb):
    subprocess.run(['python3', 'Bot.py'], check=True)
    os.rename('output_with_audio.mp4', f'vidéo_n° {i + 1}.mp4')