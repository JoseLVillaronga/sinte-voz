from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
import speech_recognition as sr
import os
from googletrans import Translator
import sounddevice as sd
import numpy as np
import socketio
import base64
from pathlib import Path
import traceback
from gtts import gTTS
import asyncio
from collections import deque
from threading import Lock
import time
import soundfile as sf
import queue
import threading
import pyaudio
import subprocess
import re
import torch
from TTS.api import TTS

# Crear la aplicación FastAPI
fastapi_app = FastAPI()

# Montar archivos estáticos
fastapi_app.mount("/static", StaticFiles(directory="static"), name="static")

# Configurar CORS
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar Socket.IO
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
socket_app = socketio.ASGIApp(sio, fastapi_app)

# Configuración inicial
SAMPLE_RATE = 16000
CHANNELS = 1

# Configuración para monitoreo de audio USB
USB_BUFFER_SIZE = 1024
USB_SAMPLE_RATE = 16000
USB_CHANNELS = 1
USB_DTYPE = np.int16

# Crear directorio para archivos temporales si no existe
Path("temp").mkdir(exist_ok=True)

# Cola global para los mensajes de texto a voz
tts_queue = deque()
tts_lock = Lock()

# Almacenar tareas de monitoreo por sid
monitoring_tasks = {}

# Cola global para el audio
audio_queue = queue.Queue()

async def process_audio_queue(recognizer, source_lang):
    """Procesa el audio de la cola y lo transcribe."""
    while True:
        # Esperar audio en la cola
        audio_data = []
        try:
            # Recolectar 3 segundos de audio (asumiendo 16000Hz)
            for _ in range(30):  # 30 chunks * 0.1s = 3s
                if not audio_queue.empty():
                    chunk = audio_queue.get()
                    audio_data.extend(chunk.flatten())
                await asyncio.sleep(0.1)
            
            if not audio_data:
                continue

            # Convertir a bytes
            audio_array = np.array(audio_data, dtype=np.float32)
            audio_bytes = (audio_array * 32767).astype(np.int16).tobytes()
            
            # Crear AudioData object
            audio_segment = sr.AudioData(audio_bytes, 16000, 2)
            
            try:
                # Transcribir
                text = recognizer.recognize_google(audio_segment, language=source_lang)
                if text.strip():
                    print(f"Transcribed: {text}")
                    # Emitir el texto transcrito a todos los clientes
                    await sio.emit('received_message', {'text': text})
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"Error en la solicitud a Google Speech Recognition; {e}")
                
        except Exception as e:
            print(f"Error procesando audio: {e}")
            await asyncio.sleep(1)

async def monitor_audio(device_id, sid, source_lang='es', target_lang='en'):
    """Monitorea el audio del dispositivo seleccionado usando PulseAudio."""
    try:
        print(f"\nMonitoreando dispositivo: {device_id}")
        
        # Configurar reconocedor
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.5
        
        # Configurar traductor
        translator = Translator()
        
        # Configuración de audio
        CHUNK = 1024 * 4
        RATE = 44100
        CHANNELS = 2
        
        # Buffer para acumular audio
        audio_buffer = []
        silence_counter = 0
        
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"Status: {status}")
            if sid not in monitoring_tasks:
                raise sd.CallbackAbort()
            audio_buffer.append(indata.copy())
        
        # Configurar el stream usando PulseAudio a través de ALSA
        try:
            # Configurar PulseAudio para usar el dispositivo seleccionado como fuente
            subprocess.run(['pactl', 'set-default-source', device_id], check=True)
            
            # Configuración del stream usando el dispositivo pulse
            stream = sd.InputStream(
                device=13,  # Dispositivo pulse (interfaz ALSA a PulseAudio)
                channels=CHANNELS,
                samplerate=RATE,
                blocksize=CHUNK,
                callback=audio_callback,
                dtype=np.float32
            )
            
            with stream:
                print(f"Stream abierto usando dispositivo pulse, capturando desde {device_id}")
                await sio.emit('monitor_status', {'status': 'started'}, to=sid)
                
                while sid in monitoring_tasks:
                    if len(audio_buffer) > 0:
                        # Procesar audio acumulado
                        audio_data = np.concatenate(audio_buffer)
                        audio_buffer.clear()
                        
                        # Detectar silencio usando RMS
                        rms = np.sqrt(np.mean(audio_data**2))
                        if rms < 0.01:
                            silence_counter += 1
                            if silence_counter > 20:
                                silence_counter = 0
                                audio_buffer.clear()
                        else:
                            silence_counter = 0
                            
                            try:
                                # Convertir float32 a int16 para speech_recognition
                                audio_mono = audio_data.mean(axis=1) if len(audio_data.shape) > 1 else audio_data
                                audio_int16 = (audio_mono * 32767).astype(np.int16)
                                audio_bytes = audio_int16.tobytes()
                                
                                audio_segment = sr.AudioData(audio_bytes, RATE, 2)
                                
                                # Transcribir
                                text = recognizer.recognize_google(audio_segment, language=source_lang)
                                if text.strip():
                                    print(f"Transcribed: {text}")
                                    
                                    # Traducir si los idiomas son diferentes
                                    if source_lang != target_lang:
                                        translation = translator.translate(text, src=source_lang, dest=target_lang)
                                        text = translation.text
                                        print(f"Translated to {target_lang}: {text}")
                                    
                                    # Emitir el texto traducido
                                    await sio.emit('received_message', {'text': text}, to=sid)
                            except sr.UnknownValueError:
                                pass
                            except sr.RequestError as e:
                                print(f"Error en la solicitud a Google Speech Recognition; {e}")
                    
                    await asyncio.sleep(0.1)
                
        except Exception as e:
            print(f"Error al abrir el stream: {e}")
            raise
            
    except Exception as e:
        print(f"Error iniciando monitoreo: {e}")
        await sio.emit('error', {'message': str(e)}, to=sid)
    finally:
        if sid in monitoring_tasks:
            del monitoring_tasks[sid]
            await sio.emit('monitor_status', {'status': 'stopped'}, to=sid)

@fastapi_app.get("/audio_devices")
async def get_audio_devices():
    """Obtiene la lista de dispositivos de audio disponibles usando PulseAudio."""
    try:
        # Obtener fuentes de PulseAudio usando pactl
        result = subprocess.run(['pactl', 'list', 'short', 'sources'], 
                             capture_output=True, text=True, check=True)
        
        devices = []
        for line in result.stdout.split('\n'):
            if line.strip():
                # Formato: id, name, module, sample_spec, state
                parts = line.split('\t')
                if len(parts) >= 5:
                    idx, name, module, sample_spec, state = parts[:5]
                    # Solo incluir dispositivos que estén en estado IDLE o RUNNING
                    if state in ['IDLE', 'RUNNING']:
                        devices.append({
                            'id': name,  # Usar el nombre como ID para PulseAudio
                            'name': name.replace('_', ' ').title(),  # Formato más amigable
                            'isInput': True,  # Todas son fuentes de entrada
                            'state': state
                        })
        
        return {"devices": devices}
    except subprocess.CalledProcessError as e:
        print(f"Error al obtener dispositivos: {e}")
        return {"error": str(e)}
    except Exception as e:
        print(f"Error inesperado: {e}")
        return {"error": str(e)}

@sio.on('start_monitor')
async def handle_start_monitor(sid, data):
    """Inicia el monitoreo de audio usando PulseAudio."""
    try:
        device_id = data.get('device_id')
        source_lang = data.get('source_lang', 'es')
        target_lang = data.get('target_lang', 'en')
        
        if not device_id:
            raise ValueError("Se requiere device_id")
            
        # Detener monitoreo existente si hay uno
        if sid in monitoring_tasks:
            await handle_stop_monitor(sid)
            
        # Iniciar nuevo monitoreo
        task = asyncio.create_task(monitor_audio(device_id, sid, source_lang, target_lang))
        monitoring_tasks[sid] = task
        
    except Exception as e:
        print(f"Error starting monitor: {e}")
        await sio.emit('error', {'message': str(e)}, to=sid)

@sio.on('stop_monitor')
async def handle_stop_monitor(sid):
    """Detiene el monitoreo de audio."""
    try:
        if sid in monitoring_tasks:
            # Cancelar la tarea
            monitoring_tasks[sid] = False
            await sio.emit('monitor_status', {'status': 'stopped'}, to=sid)
    except Exception as e:
        print(f"Error al detener monitoreo: {e}")

@fastapi_app.get("/")
async def get():
    return FileResponse("static/index.html")

@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

# Variables globales para TTS
tts_engines = {}
use_cuda = torch.cuda.is_available()
print(f"CUDA disponible: {use_cuda}")

def initialize_tts():
    """Inicializa los motores TTS con soporte CUDA si está disponible."""
    global tts_engines
    device = "cuda" if use_cuda else "cpu"
    
    try:
        # Modelo en español
        tts_engines['es'] = TTS("tts_models/es/css10/vits").to(device)
        print(f"Modelo español inicializado usando {device}")
        
        # Modelo en inglés
        tts_engines['en'] = TTS("tts_models/en/ljspeech/vits").to(device)
        print(f"Modelo inglés inicializado usando {device}")
        
        return True
    except Exception as e:
        print(f"Error inicializando TTS: {e}")
        tts_engines = {}
        return False

# Inicializar TTS al arrancar
initialize_tts()

@sio.on('text_to_speech')
async def handle_text_to_speech(sid, data):
    try:
        text = data.get('text', '')
        source_lang = data.get('source_lang', 'es')  # Idioma del texto de entrada
        target_lang = data.get('target_lang', 'en')  # Idioma para el audio
        
        if not text:
            return
            
        print(f"Texto original ({source_lang}): {text}")
        
        # Traducir al idioma objetivo
        translator = Translator()
        translated = translator.translate(text, src=source_lang, dest=target_lang)
        text = translated.text
        print(f"Texto traducido ({target_lang}): {text}")
        
        timestamp = int(time.time() * 1000)
        output_path = f"static/temp/output_{timestamp}.mp3"
        
        try:
            if target_lang in tts_engines:
                # Usar el modelo específico para el idioma objetivo
                print(f"Generando audio con Coqui TTS en {target_lang}...")
                tts_engines[target_lang].tts_to_file(text=text, file_path=output_path)
            else:
                # Fallback a gTTS si no tenemos modelo para ese idioma
                print(f"Usando gTTS como fallback para {target_lang}...")
                tts = gTTS(text=text, lang=target_lang)
                tts.save(output_path)
            
            print(f"Audio generated at {output_path}")
            
            # Verificar que el archivo existe y tiene tamaño
            if os.path.exists(output_path):
                size = os.path.getsize(output_path)
                print(f"Audio file size: {size} bytes")
                
                # Reproducir en virtual_speaker
                print("Playing audio...")
                os.system(f'paplay --device=virtual_speaker "{output_path}"')
                
                # Enviar URL del audio al cliente
                await sio.emit('text_to_speech_response', {
                    'audio_url': f'/temp/output_{timestamp}.mp3'
                }, to=sid)
                
                # Limpiar archivos antiguos
                cleanup_old_files()
                
            else:
                print("Warning: Audio file was not created!")
            
        except Exception as e:
            print(f"Error en síntesis de voz: {e}")
            traceback.print_exc()
            await sio.emit('error', {'message': str(e)}, to=sid)
            
    except Exception as e:
        print(f"Error en handle_text_to_speech: {e}")
        traceback.print_exc()
        await sio.emit('error', {'message': str(e)}, to=sid)

@sio.on('speech_to_text')
async def speech_to_text(sid, data):
    try:
        audio_data = data.get('audio', '')
        source_lang = data.get('source_lang', 'es')  # Idioma del audio de entrada
        target_lang = data.get('target_lang', 'en')  # Idioma para el texto
        
        # Decodificar el audio
        audio_bytes = base64.b64decode(audio_data)
        
        # Guardar temporalmente el archivo de audio
        temp_filename = "temp/temp_audio.wav"
        with open(temp_filename, "wb") as f:
            f.write(audio_bytes)
        
        # Inicializar el reconocedor
        r = sr.Recognizer()
        
        # Cargar el archivo de audio
        with sr.AudioFile(temp_filename) as source:
            audio = r.record(source)
            
            # Reconocer el texto en el idioma de origen
            text = r.recognize_google(audio, language=source_lang)
            print(f"Texto reconocido ({source_lang}): {text}")
            
            # Traducir al idioma objetivo si es diferente
            if source_lang != target_lang:
                translator = Translator()
                translated = translator.translate(text, src=source_lang, dest=target_lang)
                text = translated.text
                print(f"Texto traducido ({target_lang}): {text}")
            
            # Enviar el texto al cliente
            await sio.emit('speech_to_text_response', {'text': text}, to=sid)
            
    except Exception as e:
        print(f"Error in speech_to_text: {str(e)}")
        await sio.emit('error', {'message': str(e)}, to=sid)

def cleanup_old_files():
    """Limpia archivos de audio antiguos"""
    temp_dir = "static/temp"
    current_time = time.time()
    
    for filename in os.listdir(temp_dir):
        if filename.startswith("output_") and (filename.endswith(".mp3") or filename.endswith(".wav")):
            filepath = os.path.join(temp_dir, filename)
            # Eliminar archivos más antiguos que 5 minutos
            if current_time - os.path.getctime(filepath) > 300:
                try:
                    os.remove(filepath)
                    print(f"Removed old file: {filepath}")
                except Exception as e:
                    print(f"Error removing file {filepath}: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(socket_app, host="0.0.0.0", port=8000)
