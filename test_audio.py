import sounddevice as sd
import numpy as np
import time

# Configuración de audio
CHUNK = 1024 * 4
RATE = 44100
CHANNELS = 2

def audio_callback(indata, frames, time, status):
    if status:
        print(f"Status: {status}")
    rms = np.sqrt(np.mean(indata**2))
    print(f"Audio recibido: {len(indata)} muestras, RMS: {rms}")

# Obtener lista de dispositivos
print("\nDispositivos disponibles:")
devices = sd.query_devices()
print(devices)

# Intentar abrir el stream usando el dispositivo pulse
try:
    # Usar el dispositivo pulse que es la interfaz ALSA a PulseAudio
    with sd.InputStream(
        device=13,  # Dispositivo pulse (interfaz ALSA a PulseAudio)
        channels=CHANNELS,
        samplerate=RATE,
        blocksize=CHUNK,
        callback=audio_callback,
        dtype=np.float32
    ) as stream:
        print("\nStream abierto. Monitoreando audio...")
        print("PulseAudio se encargará de enrutar desde virtual_speaker.monitor")
        while True:
            time.sleep(0.1)
except KeyboardInterrupt:
    print("\nMonitoreo detenido por el usuario")
except Exception as e:
    print(f"\nError: {e}")
