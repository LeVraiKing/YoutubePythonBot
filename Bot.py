import pygame, random, math, os, sys, time
import cv2
import numpy as np
import mido
import pygame.midi
import colorsys
import tempfile
import subprocess
from scipy.io.wavfile import write

# --- Configuration ---
WIDTH = 1080 // 2
HEIGHT = 1920 // 2
CENTER = (WIDTH // 2, HEIGHT // 2)
RADIUS = 200
BALL_RADIUS = 10
SPEED = 3
GRAVITY = 0.3
BALL_COUNT = 1 # Nombre initial de balles
BALL_FREEZE_TIME_MS = 4000 # Temps après lequel une balle se fige (4 secondes)
HOLE_ANGLE_WIDTH = math.radians(20)
hole_angle = 250
hole_speed = 0.05
clsth = ["If the ball escapes,", "This one made my ps crash", "The ball have", "If the ball escapes"]
clstb = ["you have to subscribe", "pls subscribe", "4 seconds to escape", "you're gay bro"]
t = random.randint(0, (len(clsth)-1) )
th = clsth[t]
tb = clstb[t]

# --- Video & Audio Settings ---
recording = True
video_writer = None
final_video_path = "output.mp4"
merged_video_path = "output_with_audio.mp4"
sample_rate = 22050
video_duration = 15  # Durée minimale souhaitée en secondes pour la vidéo (pour le redémarrage)
VIDEO_FPS = 60.0 # Fréquence d'images vidéo explicitement définie pour la synchronisation
clsm = ['melodie.mid', 'Coldplay - Viva La Vida.mid', 'Fur Elise.mid', 'Jasper Folks - River Flows in You.mid', 'Alice Deejay - Better Off Alone.mid']
print(f"{len(clsm)} fichiers midi")
for i in range(len(clsm)):
    if os.path.exists(clsm[i]):
        print(f"fichier midi {i + 1} touvé")
    else:
        print(f"fichier midi {i + 1 } manquant")
midi_file = mido.MidiFile(f'{random.choice(clsm)}') # Sélectionne un fichier MIDI aléatoire parmi ceux de clsm
audio_events = [] # Nouvelle liste pour stocker les événements audio

# --- Global State ---
color_time = 0
color_speed = 0.01
exit_timer_start = None
active_balls = []
frozen_balls_positions = [] # Réintroduit pour stocker les balles gelées
current_note = None # Plus utilisé pour le note_off MIDI, mais conservé pour la structure
frame_count = 0 # Variable globale pour suivre le nombre d'images enregistrées
ball_escaped_time = None # Nouvelle variable pour le temps d'échappement de la balle

# --- Initialization ---
print("Initializing Pygame and peripherals...")
pygame.init()
# pygame.mixer.init(frequency=sample_rate, size=-16, channels=2, buffer=512) # Supprimé car plus besoin de sortie audio locale
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Bouncing Balls with Moving Hole")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 56)

# Crée un fichier temporaire pour l'audio WAV
temp_audio_file_obj = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
temp_audio_file_obj.close()
temp_audio_path = temp_audio_file_obj.name
print(f"Temporary audio file will be saved to: {temp_audio_path}")

# Initialise VideoWriter pour l'enregistrement
if recording:
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(final_video_path, fourcc, VIDEO_FPS, (WIDTH, HEIGHT)) # Utilise VIDEO_FPS ici
    print(f"Video recording started. Output will be: {final_video_path}")

# Initialise Pygame MIDI - La sortie MIDI physique est désactivée
# Le bloc try-except pour pygame.midi.init() est supprimé car nous ne l'utilisons plus pour la sortie physique.
midi_enabled = False # Désactive explicitement la sortie MIDI physique
notes = []
note_index = 0
try:
    # Charger le fichier MIDI pour extraire les notes, même si la sortie MIDI est désactivée)
    notes = [(msg.note, msg.velocity) for msg in midi_file if msg.type == 'note_on' and msg.velocity > 0]
    print(f"MIDI file loaded successfully with {len(notes)} notes. Physical MIDI output is disabled.")
except Exception as e:
    print(f"Could not load MIDI file. No notes will be generated. Error: {e}")


def play_midi_note():
    """Joue la prochaine note MIDI et enregistre son événement audio pour un rendu ultérieur.
    Le timing audio est maintenant basé sur le nombre d'images vidéo pour une meilleure synchronisation."""
    global note_index, current_note, frame_count, audio_events # Accède à frame_count et audio_events
    if not notes:
        return None, None

    try:
        note, velocity = notes[note_index]
        
        # La sortie MIDI physique est désactivée, donc ces lignes sont commentées ou supprimées
        # if midi_enabled:
        #     midi_out.note_on(note, velocity)
        #     current_note = (note, velocity)
        #     pygame.time.set_timer(pygame.USEREVENT + 1, 300, True) # Schedule note_off

        note_index = (note_index + 1) % len(notes)

        # Enregistre l'événement audio pour un rendu ultérieur (toujours actif pour l'enregistrement vidéo)
        if recording:
            frequency = 440 * (2 ** ((note - 69) / 12))
            duration_s = 0.3  # Durée de la note en secondes
            amplitude = (velocity / 127.0) * 0.5 # Amplitude basée sur la vélocité

            # Calcule le temps de début de la note basé sur les images enregistrées pour la synchronisation
            audio_start_frame_offset = 1 # Décalage en nombre d'images (vous pouvez ajuster cette valeur)
            start_time_s = (frame_count + audio_start_frame_offset) / VIDEO_FPS 
            audio_events.append({
                'start_time_s': start_time_s,
                'frequency': frequency,
                'duration_s': duration_s,
                'amplitude': amplitude
            })

            # La lecture du son pour un retour immédiat via pygame.mixer est supprimée
            # num_frames_mixer = int(duration_s * sample_rate)
            # t_mixer = np.linspace(0., duration_s, num_frames_mixer, endpoint=False)
            # wave_mixer = np.sin(2 * np.pi * frequency * t_mixer) * amplitude
            # stereo_wave_mixer = np.column_stack((wave_mixer, wave_mixer)).astype(np.float32)
            # sound = pygame.sndarray.make_sound((stereo_wave_mixer * 32767).astype(np.int16))
            # sound.play()

        return note, velocity
    except Exception as e:
        print(f"Error playing MIDI note: {e}")
        return None, None

def render_and_save_audio(output_path, actual_duration_s):
    """Génère le tampon audio complet à partir des événements et le sauvegarde dans un fichier WAV."""
    print("Rendering and saving audio from events...")
    
    num_samples_total = int(actual_duration_s * sample_rate)
    
    # Crée un tampon audio vide de la taille exacte de la vidéo
    final_audio_buffer = np.zeros((num_samples_total, 2), dtype=np.float32)

    for event in audio_events:
        start_sample = int(event['start_time_s'] * sample_rate)
        num_frames = int(event['duration_s'] * sample_rate)
        
        # S'assure que l'événement audio ne dépasse pas la fin du tampon
        end_sample = min(start_sample + num_frames, num_samples_total)
        actual_num_frames = end_sample - start_sample

        if actual_num_frames > 0:
            t = np.linspace(0., event['duration_s'], num_frames, endpoint=False)[:actual_num_frames]
            wave = np.sin(2 * np.pi * event['frequency'] * t) * event['amplitude']
            stereo_wave = np.column_stack((wave, wave)).astype(np.float32)
            
            # Vérifie que la plage d'écriture est valide
            if start_sample < num_samples_total and end_sample <= num_samples_total:
                final_audio_buffer[start_sample:end_sample] += stereo_wave
            else:
                print(f"⚠️ Warning: Audio event out of bounds for final buffer. Start: {start_sample}, End: {end_sample}, Total: {num_samples_total}")

    if np.any(final_audio_buffer):
        # Normalise l'audio pour éviter l'écrêtage avant de convertir en int16
        max_abs_val = np.max(np.abs(final_audio_buffer))
        if max_abs_val == 0: max_abs_val = 1.0 # Évite la division par zéro
        
        normalized_audio = final_audio_buffer / max_abs_val
        
        # Convertit au format PCM 16 bits
        wave_data = (normalized_audio * 32767).astype(np.int16)
        
        write(output_path, sample_rate, wave_data)
        print(f"✅ Audio successfully rendered and saved to: {output_path} (duration: {num_samples_total / sample_rate:.2f}s)")
    else:
        print("⚠️ Audio buffer is empty after rendering. An empty WAV file will be created.")
        # Crée un fichier wav vide pour qu'ffmpeg ne tombe pas en panne
        write(output_path, sample_rate, np.array([], dtype=np.int16))


def merge_audio_video(video_in_path, audio_in_path, video_out_path):
    """Fusionne les fichiers vidéo et audio enregistrés en utilisant ffmpeg."""
    print(f"Merging video '{video_in_path}' and audio '{audio_in_path}'...")
    if not os.path.exists(video_in_path):
        print(f"❌ Error: Video file not found at {video_in_path}")
        return False
    if not os.path.exists(audio_in_path):
        print(f"❌ Error: Audio file not found at {audio_in_path}")
        return False

    command = [
        "ffmpeg",
        "-y",  # Écrase le fichier de sortie s'il existe
        "-i", video_in_path,
        "-i", audio_in_path,
        "-c:v", "copy",  # Copie le flux vidéo sans ré-encodage
        "-c:a", "aac",   # Ré-encode l'audio en AAC
        "-strict", "experimental",
        video_out_path
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        if not os.path.exists(video_out_path):
            raise FileNotFoundError(f"Merged file {video_out_path} was not created.")
        print(f"✅ Video and audio successfully merged into: {video_out_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg error during merge:\n{e.stderr}")
        return False
    except Exception as e:
        print(f"❌ An unexpected error occurred during merge: {e}")
        return False

# La fonction upload_to_youtube a été supprimée.

# --- Simulation Core Functions ---

def spawn_ball():
    angle = random.uniform(0, 2 * math.pi)
    r = random.uniform(0, RADIUS - BALL_RADIUS)
    x = CENTER[0] + r * math.cos(angle)
    y = CENTER[1] + r * math.sin(angle)
    theta = random.uniform(0, 2 * math.pi)
    vx = SPEED * math.cos(theta)
    vy = SPEED * math.sin(theta)
    color = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))
    # Ajout de 'escaped' et réintroduction de 'is_frozen'
    return {'pos': [x, y], 'vel': [vx, vy], 'start_time': pygame.time.get_ticks(), 'color': color, 'escaped': False, 'is_frozen': False}

def angle_between(p1, p2):
    return math.atan2(p2[1] - p1[1], p2[0] - p1[0]) % (2 * math.pi)

def angle_in_range(angle, start, width):
    angle %= (2 * math.pi)
    start %= (2 * math.pi)
    end = (start + width) % (2 * math.pi)
    return (start <= angle <= end) if start < end else (angle >= start or angle <= end)

def reflect_on_static_objects(ball, static_positions):
    bx, by = ball['pos']
    vx, vy = ball['vel']
    collision = False
    # Utilise frozen_balls_positions pour les collisions avec les balles gelées
    for pos, color in static_positions:
        fx, fy = pos
        dx, dy = bx - fx, by - fy
        dist = math.hypot(dx, dy)
        if dist < 2 * BALL_RADIUS and dist != 0:
            collision = True
            nx, ny = dx / dist, dy / dist
            dot = vx * nx + vy * ny
            vx -= 2 * dot * nx
            vy -= 2 * dot * ny
            overlap = (2 * BALL_RADIUS - dist)
            bx += nx * overlap
            by += ny * overlap
    if collision:
        play_midi_note()
    ball['pos'], ball['vel'] = [bx, by], [vx, vy]

def end_recording_and_upload():
    """La fonction principale pour finaliser la vidéo et fusionner l'audio."""
    global recording, video_writer, frame_count # Accède à frame_count
    if not recording: return # Déjà traité
    
    print("--- Finalizing Process Started ---")
    recording = False

    # 1. Finalise le fichier vidéo
    if video_writer:
        print("Releasing video writer...")
        video_writer.release()
        video_writer = None # Empêche la ré-entrée

    # Calcule la durée réelle de la vidéo basée sur les images enregistrées
    actual_video_duration_s = frame_count / VIDEO_FPS

    # 2. Rend et sauvegarde l'audio collecté, ajusté à la durée réelle de la vidéo
    render_and_save_audio(temp_audio_path, actual_video_duration_s)

    # 3. Fusionne la vidéo et l'audio
    merge_audio_video(final_video_path, temp_audio_path, merged_video_path)
    
    # Vérifie la durée de la vidéo et redémarre si nécessaire
    # La logique de redémarrage est maintenant gérée dans la section de nettoyage finale
    # pour s'assurer que les ressources sont libérées avant le redémarrage.

        
def reflect_ball_from_boundary(ball):
    global exit_timer_start, ball_escaped_time
    x, y = ball['pos']
    vx, vy = ball['vel']
    dx, dy = x - CENTER[0], y - CENTER[1]
    dist = math.hypot(dx, dy)

    # Si la balle s'est déjà échappée, elle ne doit plus interagir avec la frontière
    if ball['escaped']:
        return # Permet à la balle de continuer sa trajectoire hors de l'écran

    if dist >= RADIUS - BALL_RADIUS:
        ball_angle = angle_between(CENTER, (x, y))
        if angle_in_range(ball_angle, hole_angle, HOLE_ANGLE_WIDTH):
            # La balle est dans le trou, la marquer comme échappée
            ball['escaped'] = True
            if exit_timer_start is None:
                print("Ball escaped! Starting exit timer and finalizing video.")
                exit_timer_start = pygame.time.get_ticks()
                ball_escaped_time = pygame.time.get_ticks() # Enregistre le temps d'échappement
            # Pas de réflexion, la balle continue sa trajectoire
        else:
            # La balle a touché la frontière solide, la réfléchir
            nx, ny = dx / dist, dy / dist
            dot = vx * nx + vy * ny
            vx -= 2 * dot * nx
            vy -= 2 * dot * ny
            play_midi_note()
            
            # Repositionne la balle pour l'empêcher de rester bloquée
            overlap = (dist - (RADIUS - BALL_RADIUS))
            x -= nx * overlap
            y -= ny * overlap

    ball['pos'], ball['vel'] = [x, y], [vx, vy]

def update_ball_state(ball):
    # Si la balle s'est échappée, applique juste la physique et saute les vérifications de collision
    if ball['escaped']:
        ball['vel'][1] += GRAVITY # Applique toujours la gravity
        ball['pos'][0] += ball['vel'][0]
        ball['pos'][1] += ball['vel'][1]
        return # Saute les autres vérifications de collision pour les balles échappées

    # Si la balle est gelée, elle ne bouge pas
    if ball['is_frozen']:
        return

    # Applique la physique pour les balles actives (non échappées, non gelées)
    ball['vel'][1] += GRAVITY
    ball['pos'][0] += ball['vel'][0]
    ball['pos'][1] += ball['vel'][1]

    reflect_ball_from_boundary(ball) # Cela définira le drapeau 'escaped' si elle passe à travers
    reflect_on_static_objects(ball, frozen_balls_positions) # Vérifie les collisions avec les balles gelées

    # Condition de gel : si pas échappée et temps de vie dépassé
    if not ball['escaped'] and pygame.time.get_ticks() - ball['start_time'] > BALL_FREEZE_TIME_MS:
        ball['is_frozen'] = True
        # S'assure que la balle gelée est bien dans le cercle
        dx, dy = ball['pos'][0] - CENTER[0], ball['pos'][1] - CENTER[1]
        dist = math.hypot(dx, dy)
        max_dist = RADIUS - BALL_RADIUS
        if dist > max_dist:
            ratio = max_dist / dist
            ball['pos'][0] = CENTER[0] + dx * ratio
            ball['pos'][1] = CENTER[1] + dy * ratio
        frozen_balls_positions.append((list(ball['pos']), ball['color']))


def draw_circle_with_hole(surface, color, center, radius, hole_angle, hole_width, alpha=255):
    """Dessine un cercle avec un trou, avec une transparence."""
    temp_surface = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
    temp_surface.set_alpha(alpha)

    points = []
    for deg in range(361):
        angle = math.radians(deg)
        is_in_hole = angle_in_range(angle, hole_angle, hole_width)

        if not is_in_hole:
            points.append((center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)))
        else:
            if len(points) > 1:
                pygame.draw.lines(temp_surface, color, False, points, 2)
            points = []
            
    if len(points) > 1:
        pygame.draw.lines(temp_surface, color, False, points, 2)
    
    surface.blit(temp_surface, (0,0))

def draw_ball(surface, color, pos, radius, alpha=255):
    """Dessine une balle avec une transparence."""
    temp_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    temp_surface.set_alpha(alpha)
    pygame.draw.circle(temp_surface, color, (radius, radius), radius)
    surface.blit(temp_surface, (pos[0] - radius, pos[1] - radius))

def get_smooth_color(time_val):
    hue = (time_val * color_speed) % 1.0
    rgb = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
    return tuple(int(c * 255) for c in rgb)

# --- Main Game Loop ---
for _ in range(BALL_COUNT):
    active_balls.append(spawn_ball())

running = True
print("--- Starting Main Loop ---")
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # Met à jour l'état
    hole_angle = (hole_angle + hole_speed) % (2 * math.pi)
    color_time += 1

    # Met à jour toutes les balles (actives, gelées, échappées)
    for ball in active_balls:
        update_ball_state(ball)

    # Fait apparaître de nouvelles balles si le nombre de balles actives (non gelées et non échappées) est inférieur à BALL_COUNT
    # ET si aucune balle ne s'est encore échappée.
    if ball_escaped_time is None: # Si aucune balle n'est échappée, on peut faire apparaître de nouvelles balles
        num_active_and_moving_balls = sum(1 for ball in active_balls if not ball['is_frozen'] and not ball['escaped'])
        while num_active_and_moving_balls < BALL_COUNT:
            active_balls.append(spawn_ball())
            num_active_and_moving_balls += 1 # Incrémente le compteur pour la nouvelle balle

    # Dessin
    screen.fill((0, 0, 0))

    # Calcule l'alpha pour l'animation de disparition
    current_alpha = 255
    if ball_escaped_time is not None:
        time_since_escape = pygame.time.get_ticks() - ball_escaped_time
        fade_duration_ms = 2500 # Durée de l'animation de disparition en ms
        if time_since_escape < fade_duration_ms:
            current_alpha = 255 - int(255 * (time_since_escape / fade_duration_ms))
            current_alpha = max(0, current_alpha) # S'assure que l'alpha ne descend pas en dessous de 0
        else:
            current_alpha = 0 # Complètement transparent après la durée de fondu

    circle_color = get_smooth_color(color_time)
    draw_circle_with_hole(screen, circle_color, CENTER, RADIUS, hole_angle, HOLE_ANGLE_WIDTH, alpha=current_alpha)
    
    # Dessine les balles gelées
    for pos, color in frozen_balls_positions:
        draw_ball(screen, color, pos, BALL_RADIUS, alpha=current_alpha)

    # Dessine les balles actives (non échappées et non gelées)
    for ball in active_balls:
        if not ball['escaped'] and not ball['is_frozen']:
            draw_ball(screen, ball['color'], ball['pos'], BALL_RADIUS, alpha=current_alpha)
        # Si la balle est échappée ou gelée, elle est gérée par les autres boucles de dessin ou ignorée ici.

    # Le texte reste visible quelle que soit l'animation des cercles
    text_surface = font.render("Si la balle s'échappe,", True, (255, 255, 255))
    screen.blit(text_surface, (WIDTH // 2 - text_surface.get_width() // 2, 50))
    text_surface2 = font.render("la vidéo sera enregistrée", True, (255, 255, 255))
    screen.blit(text_surface2, (WIDTH // 2 - text_surface2.get_width() // 2, 100))

    pygame.display.flip()

    # Capture l'image pour la vidéo
    if recording and video_writer:
        frame = pygame.surfarray.array3d(pygame.display.get_surface())
        frame = np.transpose(frame, (1, 0, 2))
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        video_writer.write(frame)
        frame_count += 1 # Incrémente le compteur d'images après l'écriture

    clock.tick(60)

    # Vérifie la condition de sortie : si la balle s'échappe et que le temps d'attente est écoulé
    if exit_timer_start and pygame.time.get_ticks() - exit_timer_start >= 3000:
        running = False

# --- Cleanup ---
print("--- Main Loop Ended: Cleaning up resources ---")

# Finalise tout si la boucle a été quittée manuellement (par exemple, fermeture de la fenêtre)
# ou si le timer d'échappement a déclenché l'arrêt de la boucle.
if recording: 
    print("Finalizing video recording and audio...")
    end_recording_and_upload()

# Effectue le redémarrage si la durée de la vidéo est trop courte
actual_video_duration_s = frame_count / VIDEO_FPS 
if actual_video_duration_s < video_duration:
    print(f"Video duration ({actual_video_duration_s:.2f}s) is less than {video_duration}s. Restarting script.")
    os.execv(sys.executable, [sys.executable] + sys.argv)
else:
    print("✅ Script finished.")
    # Nettoie le fichier audio temporaire uniquement si le script ne redémarre pas
    if os.path.exists(temp_audio_path):
        try:
            os.unlink(temp_audio_path)
            print(f"Removed temporary audio file: {temp_audio_path}")
        except OSError as e:
            print(f"Error removing temporary file: {e}")

    # Les appels à pygame.midi.quit() et midi_out.close() sont supprimés car MIDI n'est plus utilisé.
    pygame.quit()
    sys.exit()
