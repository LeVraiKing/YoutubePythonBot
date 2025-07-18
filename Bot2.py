import pygame
import sys
import math
import random
import cv2
import numpy as np
import mido
import pygame.midi
import os
import tempfile
import subprocess
from scipy.io.wavfile import write

pygame.init()

# Game constants
WIDTH, HEIGHT = 1080, 1920 # Updated to 1080p resolution
CENTER = (WIDTH // 2, HEIGHT // 2)
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))  # Fixed syntax with tuple
pygame.display.set_caption("Spiral Escape - Shrinking Circles")

# Colors
BLACK = (0, 0, 0)
YELLOW = (255, 255, 0)
BLUE_LIGHT = (0, 200, 255) # Color for the rings

clock = pygame.time.Clock()

# Video & Audio Settings
recording = True
video_writer = None
final_video_path = "output.mp4"
merged_video_path = "output_with_audio.mp4"
sample_rate = 22050
VIDEO_FPS = 60.0
audio_events = []
frame_count = 0

# Create temporary file for audio WAV
temp_audio_file_obj = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
temp_audio_file_obj.close()
temp_audio_path = temp_audio_file_obj.name
print(f"Temporary audio file will be saved to: {temp_audio_path}")

# Initialize VideoWriter for recording
if recording:
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(final_video_path, fourcc, VIDEO_FPS, (WIDTH, HEIGHT))  # Updated dimensions
    print(f"Video recording started. Output will be: {final_video_path}")

# Initialize MIDI
try:
    pygame.mixer.init(frequency=sample_rate, size=-16, channels=2, buffer=512)
    pygame.midi.init()
    output_id = pygame.midi.get_default_output_id()
    midi_out = pygame.midi.Output(output_id)
    # Default to a simple MIDI file or create a basic note sequence
    midi_files = ['Tetris - Tetris Main Theme.mid']
    midi_path = None
    for file in midi_files:
        if os.path.exists(f'/home/augustin/Téléchargements/{file}'):
            midi_path = f'/home/augustin/Téléchargements/{file}'
            break
    
    if midi_path:
        midi_file = mido.MidiFile(midi_path)
        notes = [(msg.note, msg.velocity) for msg in midi_file if msg.type == 'note_on' and msg.velocity > 0]
    else:
        # Create a simple C major scale as fallback
        notes = [(60+i, 80) for i in range(8)] + [(60+i, 80) for i in range(7, -1, -1)]
    
    note_index = 0
    current_note = None
    midi_enabled = True
    print(f"MIDI initialized successfully with {len(notes)} notes.")
except Exception as e:
    print(f"Could not initialize MIDI. Sound will be generated but not sent to MIDI device. Error: {e}")
    midi_enabled = False
    notes = []
    note_index = 0

# Ball properties
ball_radius = 15  # Increased for better visibility at higher resolution
x = CENTER[0]
y = CENTER[1] - 50  # Position the ball well inside the inner circle
vx = random.randint(1, 2)  # Increase initial horizontal velocity
vy = 0.0
gravity = 0.15  # Reduce gravity to make it more realistic
friction = 0.999  # Increase friction retention for more bouncing
bounce_damping = 1.05  # Increase bounce damping for more energetic bounces
surface_friction = 0.98 # Reduce surface friction for more bouncing
passed_through_inner = False  # Add this variable
inner_circle_radius = 400  # Increased for better proportion on larger screen
num_rings = 10
ring_spacing = 40  # Increased spacing for larger screen
ring_thickness = 6  # Slightly thicker rings for higher resolution
ring_gap_size = math.radians(45) # Size of the gap in radians (45 degrees)
shrink_rate = 0.05 # Speed at which circles shrink
stangle = 270
inner_gap_angle = math.radians(stangle)  # point de départ
inner_gap_size = ring_gap_size  # même taille que les anneaux
ring_speed = 0.001  # Speed at which the rings rotate

# Initialize rings
rings = []
for i in range(num_rings):
    radius = inner_circle_radius + i * ring_spacing
    rings.append({"radius": radius, "gap_angle": math.radians(stangle)}) # Start gap at the top

# Font for displaying score/messages
font = pygame.font.SysFont(None, 36)

def play_midi_note():
    global note_index, current_note, frame_count, audio_events
    if not notes:
        return None, None

    try:
        note, velocity = notes[note_index]
        
        # Play note on MIDI device if enabled
        if midi_enabled:
            midi_out.note_on(note, velocity)
            current_note = (note, velocity)
            pygame.time.set_timer(pygame.USEREVENT + 1, 300, True)  # Schedule note_off

        note_index = (note_index + 1) % len(notes)

        # Record audio event for later rendering
        if recording:
            frequency = 440 * (2 ** ((note - 69) / 12))
            duration_s = 0.3  # Note duration in seconds
            amplitude = (velocity / 127.0) * 0.5  # Amplitude based on velocity
            start_time_s = frame_count / VIDEO_FPS
            audio_events.append({
                'start_time_s': start_time_s,
                'frequency': frequency,
                'duration_s': duration_s,
                'amplitude': amplitude
            })

            # Play sound using pygame.mixer for immediate feedback
            num_frames_mixer = int(duration_s * sample_rate)
            t_mixer = np.linspace(0., duration_s, num_frames_mixer, endpoint=False)
            wave_mixer = np.sin(2 * np.pi * frequency * t_mixer) * amplitude
            stereo_wave_mixer = np.column_stack((wave_mixer, wave_mixer)).astype(np.float32)
            sound = pygame.sndarray.make_sound((stereo_wave_mixer * 32767).astype(np.int16))
            sound.play()

        return note, velocity
    except Exception as e:
        print(f"Error playing MIDI note: {e}")
        return None, None

def render_and_save_audio(output_path, actual_duration_s):
    """Generate complete audio buffer from events and save to WAV file."""
    print("Rendering and saving audio from events...")
    
    num_samples_total = int(actual_duration_s * sample_rate)
    
    # Create empty audio buffer of exact video length
    final_audio_buffer = np.zeros((num_samples_total, 2), dtype=np.float32)

    for event in audio_events:
        start_sample = int(event['start_time_s'] * sample_rate)
        num_frames = int(event['duration_s'] * sample_rate)
        
        # Ensure audio event doesn't exceed buffer end
        end_sample = min(start_sample + num_frames, num_samples_total)
        actual_num_frames = end_sample - start_sample

        if actual_num_frames > 0:
            t = np.linspace(0., event['duration_s'], num_frames, endpoint=False)[:actual_num_frames]
            wave = np.sin(2 * np.pi * event['frequency'] * t) * event['amplitude']
            stereo_wave = np.column_stack((wave, wave)).astype(np.float32)
            
            # Check that write range is valid
            if start_sample < num_samples_total and end_sample <= num_samples_total:
                final_audio_buffer[start_sample:end_sample] += stereo_wave
            else:
                print(f"⚠️ Warning: Audio event out of bounds for final buffer")

    if np.any(final_audio_buffer):
        # Normalize audio to avoid clipping before converting to int16
        max_abs_val = np.max(np.abs(final_audio_buffer))
        if max_abs_val == 0: max_abs_val = 1.0  # Avoid division by zero
        
        normalized_audio = final_audio_buffer / max_abs_val
        
        # Convert to 16-bit PCM format
        wave_data = (normalized_audio * 32767).astype(np.int16)
        
        write(output_path, sample_rate, wave_data)
        print(f"✅ Audio successfully rendered and saved to: {output_path}")
    else:
        print("⚠️ Audio buffer is empty after rendering. An empty WAV file will be created.")
        # Create empty wav file so ffmpeg doesn't crash
        write(output_path, sample_rate, np.array([], dtype=np.int16))

def merge_audio_video(video_in_path, audio_in_path, video_out_path):
    """Merge recorded video and audio files using ffmpeg."""
    print(f"Merging video '{video_in_path}' and audio '{audio_in_path}'...")
    if not os.path.exists(video_in_path):
        print(f"❌ Error: Video file not found at {video_in_path}")
        return False
    if not os.path.exists(audio_in_path):
        print(f"❌ Error: Audio file not found at {audio_in_path}")
        return False

    command = [
        "ffmpeg",
        "-y",  # Overwrite output file if it exists
        "-i", video_in_path,
        "-i", audio_in_path,
        "-c:v", "copy",  # Copy video stream without re-encoding
        "-c:a", "aac",   # Re-encode audio to AAC
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

def end_recording():
    """Finalize the video and merge with audio."""
    global recording, video_writer, frame_count
    if not recording: return  # Already processed
    
    print("--- Finalizing Process Started ---")
    recording = False

    # 1. Finalize video file
    if video_writer:
        print("Releasing video writer...")
        video_writer.release()
        video_writer = None  # Prevent re-entry

    # Calculate actual video duration based on recorded frames
    actual_video_duration_s = frame_count / VIDEO_FPS

    # 2. Render and save collected audio, adjusted to actual video duration
    render_and_save_audio(temp_audio_path, actual_video_duration_s)

    # 3. Merge video and audio
    merge_audio_video(final_video_path, temp_audio_path, merged_video_path)
    
    # Clean up temp audio file
    if os.path.exists(temp_audio_path):
        try:
            os.unlink(temp_audio_path)
            print(f"Removed temporary audio file: {temp_audio_path}")
        except OSError as e:
            print(f"Error removing temporary file: {e}")

def angle_in_gap(angle, gap_center, effective_gap_width):
    start = (gap_center - effective_gap_width / 2) % (2 * math.pi)
    end = (gap_center + effective_gap_width / 2) % (2 * math.pi)

    if start < end:
        return start <= angle <= end
    else:
        # Gap wraps around 0/2*pi
        return angle >= start or angle <= end

# Game loop
running = True
while running:
    clock.tick(60)
    SCREEN.fill(BLACK) # Clear the screen
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.USEREVENT + 1 and midi_enabled and current_note:
            try:
                midi_out.note_off(current_note[0], current_note[1])
                current_note = None
            except Exception as e:
                print(f"Error sending note_off: {e}")
    
    vy += gravity
    vx *= friction
    vy *= friction
    x += vx
    y += vy
    dx = x - CENTER[0]
    dy = y - CENTER[1]
    dist = math.hypot(dx, dy) # Distance from ball center to screen center
    ball_angle = math.atan2(dy, dx) % (2 * math.pi) # Angle of the ball's center
    boundary_dist = inner_circle_radius - ball_radius
    if dist > boundary_dist:
        if angle_in_gap(ball_angle, inner_gap_angle, inner_gap_size):
            passed_through_inner = True  # La balle est sortie par le trou
        elif not passed_through_inner:
            if dist == 0:
                nx, ny = 0, -1
            else:
                nx, ny = -dx / dist, -dy / dist

            overlap = dist - boundary_dist
            if overlap > 0:
                x += nx * overlap
                y += ny * overlap

                dx = x - CENTER[0]
                dy = y - CENTER[1]
                dist = math.hypot(dx, dy)

            v_normal_mag = vx * nx + vy * ny
            v_tangent_mag = vx * (-ny) + vy * nx

            if v_normal_mag < 0:
                new_v_normal_mag = -v_normal_mag * bounce_damping
                new_v_tangent_mag = v_tangent_mag * surface_friction

                vx = new_v_normal_mag * nx + new_v_tangent_mag * (-ny)
                vy = new_v_normal_mag * ny + new_v_tangent_mag * nx
                
                # Play sound when ball bounces off boundary
                play_midi_note()

    if dist < boundary_dist - 2 * ball_radius:
        passed_through_inner = False
    inner_gap_angle += ring_speed
    rings_to_remove = [] 
    updated_rings = []

    for ring in rings:
        ring_radius = ring["radius"]
        gap_angle = ring["gap_angle"]

        # Vérifie la distance entre balle et ring
        if ring_radius > 10:
            if abs(dist - ring_radius) < ball_radius:
                if angle_in_gap(ball_angle, gap_angle, ring_gap_size):
                    continue
                else:
                    # Collision avec partie solide du ring
                    if dist == 0:
                        nx, ny = 0, -1
                    else:
                        nx, ny = dx / dist, dy / dist

                    if dist < ring_radius:
                        x = CENTER[0] + nx * (ring_radius - ball_radius)
                        y = CENTER[1] + ny * (ring_radius - ball_radius)
                        normal_x, normal_y = -nx, -ny
                    else:
                        x = CENTER[0] + nx * (ring_radius + ball_radius)
                        y = CENTER[1] + ny * (ring_radius + ball_radius)
                        normal_x, normal_y = nx, ny

                    dot_product = vx * normal_x + vy * normal_y
                    if dot_product < 0:
                        vx -= 2 * dot_product * normal_x * bounce_damping
                        vy -= 2 * dot_product * normal_y * bounce_damping
                        vx *= surface_friction
                        vy *= surface_friction
                        
                        # Play sound when ball bounces off ring
                        play_midi_note()

            # Shrink and rotate ring
            ring["radius"] -= shrink_rate
            ring["gap_angle"] += 200 / ring["radius"] * 0.01

            # Ajouter à la liste que si encore visible
            if ring["radius"] > ball_radius:
                updated_rings.append(ring)

    # Remplacer la liste complète des rings
    rings = updated_rings

    # Supprimer les anneaux traversés après la boucle
    for ring in rings_to_remove:
        if ring in rings:
            rings.remove(ring)

    new_rings = []
    for ring in rings:
        ring["radius"] -= shrink_rate
        rotation_speed = 200 / ring["radius"] * 0.02
        ring["gap_angle"] += rotation_speed
        if ring["radius"] > ball_radius:
            new_rings.append(ring)
    rings = new_rings

    inner_circle_radius -= shrink_rate
    # Inner circle also rotates faster as it shrinks
    inner_rotation_speed = 200 / inner_circle_radius * 0.01
    inner_gap_angle += inner_rotation_speed

    # Drawing the rings
    # Now, this loop will only iterate over the rings that are actually visible
    for ring in rings:
        temp_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA) # Surface for drawing transparent lines
        points = []
        # Draw the ring segments, skipping the gap
        for deg in range(361): # Iterate through 360 degrees
            angle = math.radians(deg)
            # Check if the current angle is NOT within the gap (for drawing solid parts)
            if not angle_in_gap(angle, ring["gap_angle"], ring_gap_size):
                px = CENTER[0] + ring["radius"] * math.cos(angle)
                py = CENTER[1] + ring["radius"] * math.sin(angle)
                points.append((px, py))
            else:
                # If we hit the gap, draw the accumulated points as a line segment
                if len(points) > 1:
                    pygame.draw.lines(temp_surf, BLUE_LIGHT, False, points, ring_thickness)
                points = [] # Reset points for the next segment
        # Draw any remaining points after the loop (for the last segment)
        if len(points) > 1:
            pygame.draw.lines(temp_surf, BLUE_LIGHT, False, points, ring_thickness)
        SCREEN.blit(temp_surf, (0, 0)) # Blit the transparent surface onto the main screen

    # Drawing the ball
    pygame.draw.circle(SCREEN, YELLOW, (int(x), int(y)), ball_radius)

    # Display remaining rings count
    text = font.render(f"Rings: {len(rings)}", True, (255, 255, 255))
    SCREEN.blit(text, (CENTER[0] - text.get_width() // 2, 20))

    pygame.display.flip()
    
    # Capture frame for video
    if recording and video_writer:
        frame = pygame.surfarray.array3d(pygame.display.get_surface())
        frame = np.transpose(frame, (1, 0, 2))
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        video_writer.write(frame)
        frame_count += 1  # Increment frame counter after writing

    if len(rings) == 0:
        running = False

# Finalize recording when game ends
if recording:
    end_recording()

# Clean up MIDI resources
if midi_enabled:
    midi_out.close()
    pygame.midi.quit()

pygame.quit()
sys.exit()

