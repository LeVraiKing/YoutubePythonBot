import shutil

for i in range(103):
    shutil.move(f"vidéo_n° {i + 1}.mp4", "vidéos/")
