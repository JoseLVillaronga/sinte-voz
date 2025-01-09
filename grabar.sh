#!/bin/bash

# Mostrar dispositivos disponibles
echo "Dispositivos PulseAudio disponibles:"
echo "=================================="
pactl list sources | awk '/^Source/ {id=$2} /Name:/ {name=$2} /Description:/ {for (i=2; i<=NF; i++) desc = desc $i " "; print "Fuente " id "\nNombre: " name "\nDescripción: " desc "\n"; desc=""}'

# Solicitar nombre del dispositivo
echo -n "Ingrese el nombre del dispositivo (por ejemplo, 'virtual_mic'): "
read device_name

# Generar nombre de archivo con timestamp
timestamp=$(date +%Y%m%d_%H%M%S)
output_file="grabacion_${timestamp}.wav"

echo "Grabando en ${output_file}..."
echo "Presione Ctrl+C para detener la grabación"

# Usar parec para grabar y ffmpeg para convertir a WAV
parec -d "$device_name" --format=s16le --rate=44100 --channels=2 | \
ffmpeg -f s16le -ar 44100 -ac 2 -i - \
       -c:a pcm_s16le "${output_file}" 2>/dev/null

# Verificar si la grabación fue exitosa
if [ $? -eq 0 ]; then
    echo "Grabación guardada en ${output_file}"
else
    echo "Error durante la grabación"
fi
