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
import whisper
import librosa
import gc
from threading import Semaphore

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

# Variables globales para reconocimiento de voz
whisper_model = None
device = "cuda" if torch.cuda.is_available() else "cpu"

# Variables globales
audio_queue = queue.Queue()
gpu_worker = None  # Worker global

class GPUWorker:
    def __init__(self, model, queue, results, callback):
        self.model = model
        self.queue = queue
        self.results = results
        self.callback = callback
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.thread = threading.Thread(target=self._worker_loop)
        self.thread.daemon = True
        self.last_text = ""
        self.context_history = []  # Historial de frases para contexto
        self.max_history = 5  # Mantener las últimas 5 frases
        self.min_segment_length = 15
        self.processing_lock = Semaphore(1)  # Limitar a 1 proceso a la vez
        self.thread.start()

    def _clear_gpu_memory(self):
        """Liberar memoria GPU"""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()

    def _select_best_segment(self, segments, result):
        """Selecciona el mejor segmento basado en logprobs y contexto"""
        if not segments:
            return None

        # Filtrar segmentos muy cortos
        valid_segments = [seg for seg in segments if len(seg.get("text", "").strip()) >= self.min_segment_length]
        if not valid_segments:
            return None

        # Obtener logprobs promedio por segmento
        segment_scores = []
        for segment in valid_segments:
            text = segment["text"].strip()
            avg_logprob = segment.get("avg_logprob", -1)
            no_speech_prob = segment.get("no_speech_prob", 1)
            
            # Penalizar segmentos con alta probabilidad de no-voz
            score = avg_logprob * (1 - no_speech_prob)
            
            # Bonus por contexto
            if self.context_history:
                # Verificar si el texto actual continúa alguna frase del contexto
                for ctx in reversed(self.context_history):
                    if ctx.lower() in text.lower() or text.lower() in ctx.lower():
                        score += 2.0  # Bonus por continuidad
                        break
            
            segment_scores.append((text, score))

        # Ordenar por score y obtener el mejor
        if segment_scores:
            best_text = max(segment_scores, key=lambda x: x[1])[0]
            
            # Actualizar historial de contexto
            self.context_history.append(best_text)
            if len(self.context_history) > self.max_history:
                self.context_history.pop(0)
                
            return best_text
            
        return None

    def _worker_loop(self):
        """Mantiene la GPU activa procesando audio"""
        print("Realizando warm-up de GPU...")
        dummy_audio = torch.zeros((1, 16000), device=self.device)
        while True:
            try:
                if self.queue.empty():
                    with torch.cuda.amp.autocast():
                        _ = self.model.transcribe(dummy_audio.cpu().numpy(), 
                                                language="es",
                                                temperature=0.0)
                    torch.cuda.synchronize()
                    self._clear_gpu_memory()
                else:
                    # Esperar a que se libere el semáforo
                    with self.processing_lock:
                        audio_data = self.queue.get()
                        if audio_data is None:
                            break
                        
                        try:
                            # Procesar audio real
                            audio_tensor = torch.from_numpy(audio_data).to(self.device)
                            audio_tensor = audio_tensor.unsqueeze(0)
                            
                            with torch.cuda.amp.autocast():
                                result = self.model.transcribe(
                                    audio_tensor.cpu().numpy(), 
                                    language="es",
                                    task="transcribe",
                                    best_of=5,
                                    beam_size=5,
                                    temperature=0.2,
                                    condition_on_previous_text=True,
                                    fp16=True,
                                    compression_ratio_threshold=2.4,
                                    no_speech_threshold=0.6,
                                    return_segments=True
                                )
                            
                            # Asegurarse de que la GPU ha terminado
                            torch.cuda.synchronize()
                            
                            # Seleccionar el mejor segmento basado en logprobs y contexto
                            text = self._select_best_segment(result.get("segments", []), result)
                            
                            if text and text != self.last_text:
                                print(f"Transcribed: {text}")
                                translation = self.translate_to_spanish(text)
                                print(f"Translated to es: {translation}")
                                self.callback(text, translation)
                                self.last_text = text
                        
                        finally:
                            # Limpiar memoria GPU después de cada proceso
                            self._clear_gpu_memory()
                            
                            # Liberar tensores
                            if 'audio_tensor' in locals():
                                del audio_tensor
                            if 'result' in locals():
                                del result
                        
            except Exception as e:
                print(f"Error en worker: {str(e)}")
                self._clear_gpu_memory()
                continue
    
    def transcribe(self, audio):
        self.queue.put(audio)
        self.queue.join()
        return self.results.get()
    
    def stop(self):
        self.running = False
        self.thread.join()

def initialize_whisper():
    global gpu_worker, whisper_model
    
    print("Inicializando Whisper con CUDA...")
    
    # Configurar CUDA para máximo rendimiento
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.benchmark = True
    torch.backends.cudnn.deterministic = False
    
    # Mostrar info de GPU
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"Memoria GPU Total: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.0f}MB")
        print(f"Memoria GPU Disponible: {torch.cuda.mem_get_info()[0] / 1024**2:.0f}MB")
    
    # Cargar y optimizar modelo
    print("Realizando warm-up de GPU...")
    whisper_model = whisper.load_model("large-v3", device="cuda")
    
    # Compilar funciones críticas con torch.compile
    whisper_model.encoder = torch.compile(whisper_model.encoder, mode="max-autotune")
    whisper_model.decoder = torch.compile(whisper_model.decoder, mode="max-autotune")
    whisper_model.transcribe = torch.compile(whisper_model.transcribe, mode="max-autotune")
    
    # Crear worker global
    gpu_worker = GPUWorker(whisper_model, queue.Queue(), queue.Queue(), lambda x, y: None)
    
    print("Whisper inicializado con CUDA")
    print(f"Memoria GPU después de cargar modelo: {torch.cuda.memory_allocated() / 1024**2:.1f}MB")
    print(f"CUDA disponible: {torch.cuda.is_available()}")

# Inicializar Whisper al arrancar
initialize_whisper()

class AudioStream:
    def __init__(self, device_name):
        self.device_name = device_name
        self.stream = None
        self.is_active = False
        self.sample_rate = 16000  # Unificado a 16kHz para Whisper
        self._setup_stream()

    def _setup_stream(self):
        try:
            if self.stream and self.stream.active:
                self.stream.stop()
                self.stream.close()

            print(f"\nConfigurando stream para {self.device_name}")
            
            # Reducir blocksize a 25ms para menor latencia
            self.stream = sd.InputStream(
                device=self.device_name,
                channels=1,  # Mono para Whisper
                samplerate=self.sample_rate,
                blocksize=int(self.sample_rate * 0.025),  # 25ms blocks
                callback=self._audio_callback
            )
            
            print(f"Stream configurado:")
            print(f"- Dispositivo: {self.device_name}")
            print(f"- Sample rate: {self.sample_rate}Hz")
            print(f"- Canales: 1 (mono)")
            print(f"- Block size: {int(self.sample_rate * 0.025)} muestras (25ms)")
            
            self.stream.start()
            self.is_active = True
            
        except Exception as e:
            print(f"Error configurando stream: {e}")
            self.is_active = False
            if self.stream:
                try:
                    self.stream.close()
                except:
                    pass
            self.stream = None

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(f"Estado del stream: {status}")
        if self.is_active and not audio_queue.full():
            # Convertir a mono si es necesario
            if indata.shape[1] > 1:
                audio_mono = indata.mean(axis=1)
            else:
                audio_mono = indata.flatten()
            audio_queue.put(audio_mono)

    def stop(self):
        print(f"\nDeteniendo stream para {self.device_name}")
        self.is_active = False
        if self.stream:
            try:
                if self.stream.active:
                    self.stream.stop()
                self.stream.close()
            except Exception as e:
                print(f"Error cerrando stream: {e}")
        self.stream = None

active_streams = {}

@sio.on('start_monitoring')
async def start_monitoring(sid, data):
    device_name = data.get('device')
    print(f"\nIniciando monitoreo para {device_name}")
    
    # Detener stream existente si hay
    if device_name in active_streams:
        print(f"Deteniendo stream existente para {device_name}")
        active_streams[device_name].stop()
        del active_streams[device_name]
    
    # Crear y configurar nuevo stream
    try:
        stream = AudioStream(device_name)
        if stream.stream and stream.stream.active:
            active_streams[device_name] = stream
            print(f"Monitoreo iniciado exitosamente para {device_name}")
            return {'status': 'success', 'message': f'Monitoreando dispositivo: {device_name}'}
        else:
            print(f"Error: Stream no se inició correctamente para {device_name}")
            return {'status': 'error', 'message': 'Error iniciando stream'}
    except Exception as e:
        print(f"Error iniciando monitoreo: {e}")
        return {'status': 'error', 'message': str(e)}

@sio.on('stop_monitoring')
async def stop_monitoring(sid, data):
    device_name = data.get('device')
    print(f"\nDeteniendo monitoreo para {device_name}")
    
    if device_name in active_streams:
        active_streams[device_name].stop()
        del active_streams[device_name]
        print(f"Monitoreo detenido para {device_name}")
        return {'status': 'success', 'message': f'Monitoreo detenido para {device_name}'}
    else:
        print(f"No hay stream activo para {device_name}")
        return {'status': 'error', 'message': 'No hay stream activo para este dispositivo'}

async def process_audio_queue(recognizer, source_lang):
    """Procesa el audio de la cola y lo transcribe."""
    audio_processor = AudioProcessor(sample_rate=16000)
    
    while True:
        try:
            while not audio_queue.empty():
                chunk = audio_queue.get()
                if audio_processor.add_audio(chunk):
                    audio_batch = audio_processor.get_audio()
                    
                    try:
                        if whisper_model is not None and gpu_worker is not None:
                            print("\n=== Inicio transcripción ===")
                            print(f"Memoria GPU antes: {torch.cuda.memory_allocated() / 1024**2:.1f}MB")
                            print(f"Potencia GPU: {torch.cuda.get_device_properties(0).max_power_limit}W")
                            
                            start_time = time.time()
                            
                            # Pre-transferir a GPU en paralelo con el próximo procesamiento
                            audio_tensor = torch.from_numpy(audio_batch)
                            audio_future = torch.cuda._current_device_guard(
                                lambda: audio_tensor.cuda(non_blocking=True)
                            )
                            
                            # Procesar audio y obtener resultado
                            result = gpu_worker.transcribe(audio_future.wait())
                            
                            # Procesar resultados
                            for segment in result["segments"]:
                                text = segment["text"].strip()
                                if text and not audio_processor.is_duplicate(text):
                                    print(f"Transcripción: {text}")
                                    audio_processor.add_text(text)
                                    await sio.emit('received_message', {
                                        'text': text,
                                        'start_time': segment["start"],
                                        'end_time': segment["end"]
                                    })
                            
                            end_time = time.time()
                            print(f"Tiempo batch: {(end_time - start_time)*1000:.0f}ms")
                            print(f"Memoria GPU después: {torch.cuda.memory_allocated() / 1024**2:.1f}MB")
                            
                    except Exception as e:
                        print(f"Error en Whisper: {e}")
                        traceback.print_exc()
            
            await asyncio.sleep(0.01)  # Reducido a 10ms
            
        except Exception as e:
            print(f"Error procesando audio: {e}")
            traceback.print_exc()
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

class AudioProcessor:
    def __init__(self, sample_rate=44100, chunk_size=4410):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio_buffer = []
        self.last_process_time = time.time()
        self.min_audio_length = 0.5 * 16000  # Reducido a 500ms para menor latencia
        self.max_audio_length = 30 * 16000   # 30 segundos para batches grandes
        self.last_texts = []
        self.current_batch = []
        self.batch_size = 8  # Reducido para procesar más frecuentemente
        self.overlap = 0.25  # 25% de overlap para balance entre contexto y latencia

    def add_audio(self, audio_chunk):
        """Añade audio al buffer y retorna True si hay suficiente audio para procesar"""
        if self.sample_rate != 16000:
            audio_chunk = librosa.resample(
                audio_chunk.flatten(),
                orig_sr=self.sample_rate,
                target_sr=16000
            )
        
        self.audio_buffer.extend(audio_chunk)
        
        # Verificar si tenemos suficiente audio
        current_time = time.time()
        buffer_duration = len(self.audio_buffer) / 16000
        time_since_last = current_time - self.last_process_time
        
        # Procesar más frecuentemente (100ms)
        should_process = (len(self.audio_buffer) >= self.min_audio_length and time_since_last > 0.1) or \
                        len(self.audio_buffer) >= self.max_audio_length
        
        if should_process:
            # Crear segmentos con overlap
            segment_length = len(self.audio_buffer)
            overlap_samples = int(segment_length * self.overlap)
            
            # Dividir en segmentos con overlap
            for start in range(0, len(self.audio_buffer) - overlap_samples, overlap_samples):
                end = start + segment_length
                if end > len(self.audio_buffer):
                    end = len(self.audio_buffer)
                segment = self.audio_buffer[start:end]
                if len(segment) >= self.min_audio_length:
                    self.current_batch.append(np.array(segment))
            
            self.audio_buffer = self.audio_buffer[-overlap_samples:]
            
            if len(self.current_batch) >= self.batch_size or time_since_last > 0.5:
                return True
        
        return False

    def get_audio(self):
        """Retorna el batch de audio actual y limpia el buffer"""
        batch = self.current_batch
        self.current_batch = []
        self.last_process_time = time.time()
        return batch

    def is_duplicate(self, text):
        """Verifica si el texto es un duplicado reciente"""
        for prev_text in self.last_texts:
            if text.lower() == prev_text.lower():
                return True
        return False

    def add_text(self, text):
        """Añade texto a la lista de textos recientes"""
        self.last_texts.append(text)
        if len(self.last_texts) > 5:
            self.last_texts.pop(0)

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
