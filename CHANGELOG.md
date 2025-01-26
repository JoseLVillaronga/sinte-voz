# Changelog

Todas las modificaciones notables a este proyecto serán documentadas en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-08

### Añadido
- Interfaz web con chat de texto y voz
- Traducción bidireccional español-inglés
- Síntesis de voz (TTS) usando gTTS
- Reconocimiento de voz usando Speech Recognition
- Integración con aplicaciones externas (Zoom)
- Sistema de audio virtual con PulseAudio
- Documentación completa del proyecto
- Sistema de grabación de audio

### Características Técnicas
- Servidor web con FastAPI y Socket.IO
- Frontend responsive con Bootstrap
- Sistema de audio virtual configurado
- Manejo asíncrono de audio
- Limpieza automática de archivos temporales
- Logging detallado para debugging

### Configuración
- Dispositivos de audio virtuales configurados
- Integración con PulseAudio
- Selección de idiomas en la interfaz
- Sistema de archivos temporales

### Documentación
- README.md completo
- Documentación de desarrollo
- Instrucciones de instalación
- Guía de configuración de audio

## [0.3.0] - 2025-01-26

### Added
- Captura de audio USB mejorada usando PyAudio
- Reconocimiento de voz optimizado para baja latencia
- Detección automática de dispositivo USB
- Traducción bidireccional en tiempo real del audio capturado
- Logs detallados para debugging

### Changed
- Migración de sounddevice a PyAudio para captura de audio USB
- Optimización de parámetros de audio (16kHz, mono, float32)
- Mejora en la detección de silencio y procesamiento de audio
- Reducción de latencia en la transcripción

### Fixed
- Error de callback en la captura de audio USB
- Problemas de detección del dispositivo USB
- Traducción faltante en el audio capturado
- Latencia excesiva en el reconocimiento de voz
