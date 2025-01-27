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

async def start_usb_monitor(sid, data):
    """Inicia el monitoreo del dispositivo USB usando ALSA."""
    try:
        device_id = data.get('device_id', 'hw:0,0')  # Por defecto usar la card 0 (USB)
        source_lang = data.get('source_lang', 'es')
        
        print(f"\nIniciando monitoreo USB con device_id: {device_id}")
        
        # Configurar el reconocedor
        recognizer = sr.Recognizer()
        
        # Configurar la captura de audio usando ALSA/PyAudio
        import pyaudio
        p = pyaudio.PyAudio()
        
        # Configuración del stream
        CHUNK = 1024 * 3  # Aumentamos el tamaño del chunk para tener más datos
        FORMAT = pyaudio.paInt16
        CHANNELS = 2
        RATE = 44100
        
        # Obtener el índice del dispositivo
        device_index = None
        if device_id != 'default':
            card_num = int(device_id.split(',')[0].replace('hw:', ''))
            # Buscar el dispositivo que corresponde a la card
            for i in range(p.get_device_count()):
                dev_info = p.get_device_info_by_index(i)
                if dev_info['maxInputChannels'] > 0:  # Es un dispositivo de entrada
                    name = dev_info['name'].lower()
                    if f'hw:{card_num}' in name or ('usb' in name and card_num == 0):
                        device_index = i
                        print(f"Encontrado dispositivo USB en índice {i}: {dev_info['name']}")
                        break
        
        # Abrir stream
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK
        )
        
        print(f"Stream USB abierto correctamente con device_index: {device_index}")
        
        # Función para procesar audio
        async def process_audio():
            accumulated_data = b''
            while True:
                try:
                    # Leer audio
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    accumulated_data += data
                    
                    # Cada 3 segundos aproximadamente
                    if len(accumulated_data) >= RATE * 3 * 2:  # 3 segundos * 2 bytes por muestra
                        # Crear AudioData object
                        audio_segment = sr.AudioData(accumulated_data, RATE, 2)
                        accumulated_data = b''  # Reiniciar el buffer
                        
                        try:
                            # Transcribir
                            text = recognizer.recognize_google(audio_segment, language=source_lang)
                            if text.strip():
                                print(f"Transcribed from USB: {text}")
                                # Emitir el texto transcrito
                                await sio.emit('received_message', {'text': text}, to=sid)
                        except sr.UnknownValueError:
                            pass
                        except sr.RequestError as e:
                            print(f"Error en la solicitud a Google Speech Recognition; {e}")
                            
                except Exception as e:
                    print(f"Error procesando audio USB: {e}")
                    await asyncio.sleep(1)
                
                await asyncio.sleep(0.1)
        
        # Iniciar el procesamiento de audio en segundo plano
        asyncio.create_task(process_audio())
        
        await sio.emit('monitor_status', {'status': 'started'}, to=sid)
        
    except Exception as e:
        print(f"Error starting USB monitor: {e}")
        await sio.emit('error', {'message': str(e)}, to=sid)

@sio.on('start_usb_monitor')
async def handle_start_monitor(sid, data):
    await start_usb_monitor(sid, data)

@sio.on('stop_usb_monitor')
async def handle_stop_monitor(sid):
    # Detener la captura de audio
    sd.stop()
    await sio.emit('monitor_status', {'status': 'stopped'}, to=sid)

@fastapi_app.get("/")
async def get():
    return FileResponse("static/index.html")

@fastapi_app.get("/audio-devices")
async def get_audio_devices():
    """Obtener lista de dispositivos de audio."""
    try:
        # Obtener dispositivos PulseAudio/sounddevice para output
        devices = sd.query_devices()
        output_devices = []
        
        for i, dev in enumerate(devices):
            if dev.get('max_output_channels', 0) > 0:
                device_info = {
                    'id': str(i),
                    'name': dev['name'],
                    'channels': dev.get('max_output_channels', 0),
                    'is_input': False,
                    'is_default': sd.default.device[1] == i
                }
                output_devices.append(device_info)
        
        # Obtener dispositivos ALSA para input (usando arecord)
        import subprocess
        result = subprocess.run(['arecord', '-l'], capture_output=True, text=True)
        
        input_devices = []
        for line in result.stdout.split('\n'):
            if line.startswith('card '):
                parts = line.split(':')
                if len(parts) >= 2:
                    card_num = parts[0].replace('card ', '')
                    device_name = parts[1].strip()
                    if '[' in device_name:
                        device_name = device_name.split('[')[1].split(']')[0]
                    
                    device_info = {
                        'id': f"hw:{card_num},0",
                        'name': device_name,
                        'channels': 2,
                        'is_input': True,
                        'is_default': 'USB' in device_name
                    }
                    input_devices.append(device_info)
        
        # Agregar opción "default"
        input_devices.insert(0, {
            'id': 'default',
            'name': 'Default Input Device',
            'channels': 2,
            'is_input': True,
            'is_default': True
        })
        
        print("\nDispositivos de entrada (ALSA):")
        for dev in input_devices:
            print(f"ID: {dev['id']} - Name: {dev['name']}")
            
        print("\nDispositivos de salida (PulseAudio):")
        for dev in output_devices:
            print(f"ID: {dev['id']} - Name: {dev['name']}")
        
        return {
            'input_devices': input_devices,
            'output_devices': output_devices,
            'virtual_mic': {
                'name': 'Virtual_Microphone_Input',
                'description': None,
                'source_name': None
            }
        }
        
    except Exception as e:
        print(f"Error getting audio devices: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

# Eventos de Socket.IO
@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

@sio.on('text_to_speech')
async def handle_text_to_speech(sid, data):
    try:
        text = data.get('text', '')
        source_lang = data.get('source_lang', 'es')  # Idioma del texto de entrada
        target_lang = data.get('target_lang', 'en')  # Idioma para el audio
        print(f"Texto original ({source_lang}): {text}")
        
        # Traducir al idioma objetivo
        translator = Translator()
        translated = translator.translate(text, src=source_lang, dest=target_lang)
        text = translated.text
        print(f"Texto traducido ({target_lang}): {text}")
        
        # Generar un nombre único para el archivo
        timestamp = int(time.time() * 1000)
        output_path = f"static/temp/output_{timestamp}.mp3"
        
        # Generar el audio con gTTS en el idioma objetivo
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
        print(f"Error in text_to_speech: {str(e)}")
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

@sio.on('start_usb_monitor')
async def handle_start_usb_monitor(sid, data):
    """Maneja la solicitud de inicio de monitoreo USB."""
    try:
        # Siempre usar hw:0,0 para el dispositivo USB
        device_id = 'hw:0,0'
        source_lang = data.get('source_lang', 'es')
        target_lang = data.get('target_lang', 'en')
        
        print(f"\nIniciando monitoreo USB con device_id: {device_id}")
        print(f"Idioma origen: {source_lang}, Idioma destino: {target_lang}")
        
        # Detener monitoreo existente si hay uno
        if sid in monitoring_tasks:
            await handle_stop_usb_monitor(sid)
        
        # Iniciar el monitoreo como una tarea
        task = asyncio.create_task(monitor_audio(device_id, sid, source_lang, target_lang))
        monitoring_tasks[sid] = {'task': task}
        await sio.emit('monitor_status', {'status': 'started'}, to=sid)
            
    except Exception as e:
        print(f"Error starting USB monitor: {e}")
        await sio.emit('error', {'message': str(e)}, to=sid)

@sio.on('stop_usb_monitor')
async def handle_stop_usb_monitor(sid):
    """Detiene el monitoreo de audio USB."""
    try:
        if sid in monitoring_tasks:
            # Cancelar la tarea
            monitoring_tasks[sid]['task'].cancel()
            del monitoring_tasks[sid]
            await sio.emit('monitor_status', {'status': 'stopped'}, to=sid)
    except Exception as e:
        print(f"Error al detener monitoreo USB: {e}")

async def monitor_audio(device_id, sid, source_lang='es', target_lang='en'):
    """Monitorea el audio del dispositivo especificado."""
    try:
        print(f"\nMonitoreando audio USB en dispositivo {device_id}")
        
        # Configurar PyAudio
        p = pyaudio.PyAudio()
        
        # Configuración del stream optimizada para voz
        CHUNK = 1024  # Reducido para menor latencia
        FORMAT = pyaudio.paFloat32  # Mejor calidad
        CHANNELS = 1  # Mono es suficiente para voz
        RATE = 16000  # Tasa común para reconocimiento de voz
        
        # Obtener el índice del dispositivo
        device_index = None
        for i in range(p.get_device_count()):
            dev_info = p.get_device_info_by_index(i)
            print(f"Checking device {i}: {dev_info['name']}")
            if dev_info['maxInputChannels'] > 0:  # Es un dispositivo de entrada
                name = dev_info['name'].lower()
                if 'usb' in name:
                    device_index = i
                    print(f"Encontrado dispositivo USB en índice {i}: {dev_info['name']}")
                    break
        
        if device_index is None:
            print("No se encontró dispositivo USB, usando default")
            device_index = p.get_default_input_device_info()['index']
        
        # Abrir stream
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK
        )
        
        print(f"Stream USB abierto correctamente con device_index: {device_index}")
        
        # Configurar reconocedor
        recognizer = sr.Recognizer()
        # Ajustar parámetros para mejor reconocimiento
        recognizer.energy_threshold = 300  # Umbral de energía más bajo
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.5  # Pausa más corta entre frases
        
        # Configurar traductor
        translator = Translator()
        
        # Buffer para acumular audio
        audio_buffer = []
        silence_counter = 0
        
        while True:
            try:
                # Verificar si el monitoreo debe continuar
                if sid not in monitoring_tasks:
                    print(f"Deteniendo monitoreo para {sid}")
                    break
                
                # Leer audio
                data = np.frombuffer(stream.read(CHUNK, exception_on_overflow=False), dtype=np.float32)
                
                # Detectar silencio
                if np.abs(data).mean() < 0.01:
                    silence_counter += 1
                else:
                    silence_counter = 0
                    audio_buffer.append(data)
                
                # Procesar cuando hay suficiente audio o después de silencio
                buffer_duration = len(audio_buffer) * CHUNK / RATE
                if (buffer_duration >= 1.0 and silence_counter >= 2) or buffer_duration >= 2.0:
                    if len(audio_buffer) > 0:
                        # Convertir a formato correcto para speech_recognition
                        audio_data = np.concatenate(audio_buffer)
                        audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
                        audio_segment = sr.AudioData(audio_bytes, RATE, 2)
                        audio_buffer = []  # Reiniciar buffer
                        
                        try:
                            # Transcribir
                            text = recognizer.recognize_google(audio_segment, language=source_lang)
                            if text.strip():
                                print(f"Transcribed from USB: {text}")
                                
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
                    
            except Exception as e:
                print(f"Error procesando audio USB: {e}")
                await asyncio.sleep(0.1)
            
            await asyncio.sleep(0.01)  # Reduced sleep time
            
    except Exception as e:
        print(f"Error iniciando monitoreo: {e}")
    finally:
        if 'stream' in locals():
            stream.stop_stream()
            stream.close()
        if 'p' in locals():
            p.terminate()
        if sid in monitoring_tasks:
            del monitoring_tasks[sid]

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
