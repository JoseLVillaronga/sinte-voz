# 🎙️ Sinte-Voz

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-linux-lightgrey.svg)](https://www.linux.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

> 🌐 Rompiendo barreras de comunicación: Una solución de código abierto para personas sordas

Aplicación web para comunicación bidireccional a través de voz y texto, diseñada especialmente para personas sordas o con dificultades auditivas.

## Descripción
Sinte-Voz es una aplicación web diseñada para facilitar la comunicación bidireccional mediante voz y texto, con un enfoque especial en la accesibilidad para personas sordomudas. La aplicación permite que usuarios sordomudos participen en llamadas telefónicas y videoconferencias con personas oyentes, actuando como un puente de comunicación en tiempo real. Incorpora capacidades de síntesis de voz (TTS) y reconocimiento de voz (STT), funcionando con PulseAudio en sistemas Linux para una gestión avanzada del audio mediante dispositivos virtuales.

## Características

- 🎤 Captura de audio USB de alta calidad
- 🔄 Traducción bidireccional en tiempo real
- 💬 Chat de texto a voz y voz a texto
- 🌐 Soporte para múltiples idiomas
- 🎯 Baja latencia en reconocimiento de voz
- 🔌 Detección automática de dispositivos USB
- 🎙️ Micrófono virtual para aplicaciones de videoconferencia
- Interfaz web en tiempo real usando Socket.IO
- Síntesis de voz (TTS) usando gTTS
- Reconocimiento de voz usando Speech Recognition
- Traducción automática con Google Translate
- Manejo de dispositivos de audio virtuales con PulseAudio
- Grabación de audio en formato WAV

## Casos de Uso Principales
- **Asistencia para Personas Sordomudas**:
  - Permite participar en llamadas y videoconferencias escribiendo texto que se convierte en voz
  - Transcribe la voz del interlocutor a texto en tiempo real
  - Se integra con Zoom, aplicaciones de telefonía y otras plataformas de comunicación
  - Soporta comunicación multiidioma con traducción automática

- **Comunicación General**:
  - Chat en tiempo real con capacidades de voz
  - Traducción automática de idiomas
  - Grabación y archivo de conversaciones

## Requisitos del Sistema
- Python 3.11 o superior
- PulseAudio
- Navegador web moderno
- Conexión a Internet (para TTS y traducción)
- Dispositivo de audio USB
- Sistema operativo Linux (probado en Debian/Ubuntu)
- Dependencias del sistema:
  ```bash
  sudo apt-get install portaudio19-dev python3-pyaudio
  ```

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

## Configuración

1. Asegúrate de tener conectado tu dispositivo de audio USB
2. Verifica que el dispositivo sea reconocido:
   ```bash
   arecord -l
   ```
3. El dispositivo USB debería aparecer como "USB Audio Device"

## Integración con Zoom/Meet

1. En la configuración de audio de tu aplicación de videoconferencia:
   - Selecciona "Monitor of Null Output" como micrófono
   - Selecciona tu dispositivo de salida normal para los altavoces

2. Cuando alguien hable:
   - Su voz será capturada por el micrófono USB
   - El texto traducido aparecerá en el chat
   - Puedes responder escribiendo en el chat y se enviará como voz

## Solución de Problemas

- Si el dispositivo USB no es detectado:
  ```bash
  # Listar dispositivos de audio
  arecord -l
  aplay -l
  ```

- Si hay problemas con el micrófono virtual:
  ```bash
  # Reiniciar servicios de audio
  pulseaudio -k
  pulseaudio --start
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

## Contribuir

Las contribuciones son bienvenidas. Por favor, abre un issue para discutir cambios mayores.

## Licencia

Este proyecto está licenciado bajo los términos de la licencia MIT.
