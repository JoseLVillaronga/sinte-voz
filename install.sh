#!/bin/bash

echo " Instalando Sinte-Voz..."

# Verificar sistema operativo
if [[ "$(uname)" != "Linux" ]]; then
    echo " Este script solo funciona en Linux"
    exit 1
fi

# Instalar dependencias del sistema
echo " Instalando dependencias del sistema..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    portaudio19-dev \
    python3-pyaudio \
    pulseaudio

# Crear entorno virtual
echo " Creando entorno virtual..."
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias de Python
echo " Instalando dependencias de Python..."
pip install -r requirements.txt

# Crear directorios necesarios
echo " Creando directorios..."
mkdir -p static/temp
mkdir -p static/audio

# Configurar PulseAudio
echo " Configurando PulseAudio..."
pulseaudio -k
pulseaudio --start
sleep 2

# Crear dispositivos virtuales
echo " Creando dispositivos virtuales..."
# Virtual_Speaker para TTS
pactl load-module module-null-sink sink_name=virtual_speaker sink_properties=device.description="Virtual_Speaker"
sleep 2

# Virtual_Microphone_Input para entrada a Zoom/Meet
pactl load-module module-remap-source master=virtual_speaker.monitor source_properties=device.description="Virtual_Microphone_Input"
sleep 2

# Virtual_Speaker_Out para capturar audio de salida
pactl load-module module-null-sink sink_name=virtual_speaker_out sink_properties=device.description="Virtual_Speaker_Out"
sleep 2

# Verificar configuración
echo " Verificando configuración..."
pactl list short sources
pactl list short sinks

# Copiar archivo de configuración
echo " Creando archivo de configuración..."
cp config.example.env .env

echo """
 Instalación completada!

Para iniciar Sinte-Voz:
1. Activa el entorno virtual:
   source venv/bin/activate

2. Inicia el servidor:
   python main.py

3. Abre en tu navegador:
   http://localhost:8000
"""
