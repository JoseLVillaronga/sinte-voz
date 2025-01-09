from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
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

# Crear la aplicación FastAPI
fastapi_app = FastAPI()
app = fastapi_app  # Mantener una referencia para las rutas

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

# Crear la aplicación ASGI combinada
app = socketio.ASGIApp(sio, fastapi_app)

# Configuración inicial
SAMPLE_RATE = 16000
CHANNELS = 1

# Crear directorio para archivos temporales si no existe
Path("temp").mkdir(exist_ok=True)

# Cola global para los mensajes de texto a voz
tts_queue = deque()
tts_lock = Lock()

@fastapi_app.get("/")
async def get():
    with open("static/index.html") as f:
        return HTMLResponse(f.read())

@fastapi_app.get("/audio-devices")
async def get_audio_devices():
    try:
        # Obtener dispositivos de entrada (micrófonos)
        input_devices = []
        output_devices = []
        
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            device_info = {
                'id': i,
                'name': device['name'],
                'channels': device['max_input_channels'] if device['max_input_channels'] > 0 else device['max_output_channels']
            }
            
            if device['max_input_channels'] > 0:
                input_devices.append(device_info)
            if device['max_output_channels'] > 0:
                output_devices.append(device_info)
        
        # Obtener el dispositivo virtual
        virtual_mic_info = {
            'name': 'virtual_mic',
            'description': None,
            'source_name': None
        }
        
        try:
            import subprocess
            result = subprocess.run(['pactl', 'list', 'sources'], capture_output=True, text=True)
            current_source = {}
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('Nombre: '):
                    current_source['name'] = line.split('Nombre: ')[1]
                elif line.startswith('Descripción: '):
                    current_source['description'] = line.split('Descripción: ')[1]
                    if current_source.get('name') == 'virtual_mic':
                        virtual_mic_info['description'] = current_source['description']
                        virtual_mic_info['source_name'] = current_source['name']
                        break
        
        except Exception as e:
            print(f"Error getting virtual mic: {e}")
        
        return JSONResponse({
            'input_devices': input_devices,
            'output_devices': output_devices,
            'virtual_mic': virtual_mic_info
        })
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)

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
    uvicorn.run(app, host="0.0.0.0", port=8000)
