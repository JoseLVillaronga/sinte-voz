# Sinte-Voz: Interfaz de Chat con Síntesis y Reconocimiento de Voz

## Descripción
Sinte-Voz es una aplicación web que permite la comunicación bidireccional mediante voz y texto, incorporando capacidades de síntesis de voz (TTS) y reconocimiento de voz (STT). La aplicación está diseñada para funcionar con PulseAudio en sistemas Linux, permitiendo la creación de dispositivos de audio virtuales para una mejor gestión del audio.

## Características
- Interfaz web en tiempo real usando Socket.IO
- Síntesis de voz (TTS) usando gTTS
- Reconocimiento de voz usando Speech Recognition
- Traducción automática con Google Translate
- Manejo de dispositivos de audio virtuales con PulseAudio
- Grabación de audio en formato WAV

## Requisitos del Sistema
- Python 3.11 o superior
- PulseAudio
- Navegador web moderno
- Conexión a Internet (para TTS y traducción)

## Instalación

1. Clonar el repositorio:
```bash
git clone [URL_DEL_REPOSITORIO]
cd sinte-voz
```

2. Crear y activar entorno virtual:
```bash
python -m venv venv
source ./venv/bin/activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Configurar dispositivos de audio virtuales:
```bash
pulseaudio -k
pulseaudio --start
aplay -l
sudo modprobe -r snd_usb_audio
sudo modprobe snd_usb_audio
pactl load-module module-alsa-card device_id=0
pactl load-module module-null-sink sink_name=virtual_speaker sink_properties=device.description="Virtual_Speaker"
sleep 2
pactl load-module module-remap-source master=virtual_speaker.monitor source_properties=device.description="Virtual_Microphone_Input"
sleep 2
pactl list short sources
```

## Uso

1. Iniciar el servidor:
```bash
python main.py
```

2. Abrir el navegador en `http://localhost:8000`

3. Para grabar audio del chat:
```bash
./grabar.sh
```

## Estructura del Proyecto
- `main.py`: Servidor principal y lógica de la aplicación
- `grabar.sh`: Script para grabar audio del chat
- `static/`: Archivos estáticos (HTML, CSS, JS)
  - `index.html`: Interfaz web principal
  - `styles.css`: Estilos CSS
  - `app.js`: Lógica del cliente
- `static/temp/`: Archivos temporales de audio

## Configuración de Audio
La aplicación utiliza dos dispositivos de audio virtuales:
- `virtual_speaker`: Para reproducción de audio TTS
- `virtual_mic`: Para captura de audio STT

## Licencia
[Especificar la licencia]
