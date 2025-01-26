#!/bin/bash

echo "🧪 Ejecutando pruebas de Sinte-Voz..."

# Verificar Python y entorno virtual
if [[ ! -d "venv" ]]; then
    echo "❌ Entorno virtual no encontrado. Ejecuta install.sh primero"
    exit 1
fi

source venv/bin/activate

# Verificar dependencias
echo "📦 Verificando dependencias..."
pip freeze > installed.txt
if ! cmp -s requirements.txt installed.txt; then
    echo "❌ Las dependencias no coinciden. Ejecuta: pip install -r requirements.txt"
    rm installed.txt
    exit 1
fi
rm installed.txt

# Verificar PulseAudio
echo "🔊 Verificando PulseAudio..."
if ! pulseaudio --check; then
    echo "❌ PulseAudio no está ejecutándose"
    exit 1
fi

# Verificar dispositivos de audio
echo "🎤 Verificando dispositivos de audio..."
arecord -l
aplay -l

# Verificar directorios
echo "📁 Verificando directorios..."
for dir in "static/temp" "static/audio"; do
    if [[ ! -d "$dir" ]]; then
        echo "❌ Directorio $dir no encontrado"
        exit 1
    fi
done

# Verificar permisos
echo "🔒 Verificando permisos..."
if [[ ! -w "static/temp" ]] || [[ ! -w "static/audio" ]]; then
    echo "❌ Permisos de escritura incorrectos en directorios static"
    exit 1
fi

echo """
✅ Todas las pruebas completadas!

Sistema listo para usar Sinte-Voz.
Para iniciar el servidor:
python main.py
"""
