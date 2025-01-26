# Preguntas Frecuentes (FAQ)

## General

### ¿Qué es Sinte-Voz?
Sinte-Voz es una aplicación web que permite a personas sordas o con dificultades auditivas participar en llamadas telefónicas y videoconferencias mediante un sistema de traducción bidireccional de voz a texto y texto a voz.

### ¿Es gratuito?
Sí, Sinte-Voz es un proyecto de código abierto y gratuito.

### ¿Qué idiomas soporta?
Soporta múltiples idiomas para traducción bidireccional, incluyendo español, inglés, portugués, francés, alemán, entre otros.

## Técnico

### ¿Por qué solo funciona en Linux?
Sinte-Voz utiliza características específicas de PulseAudio para crear dispositivos de audio virtuales, que son esenciales para la integración con aplicaciones de videoconferencia.

### ¿Qué micrófono USB necesito?
Cualquier micrófono USB estándar debería funcionar. Lo importante es que sea reconocido por el sistema como dispositivo de entrada.

### ¿Funciona con auriculares bluetooth?
Sí, pero recomendamos usar un micrófono USB para mejor calidad de captura de audio.

## Uso

### ¿Cómo empiezo una llamada?
1. Inicia Sinte-Voz
2. Selecciona los idiomas de entrada/salida
3. Conecta tu micrófono USB
4. Inicia el monitoreo de audio
5. Abre tu aplicación de videoconferencia

### ¿Por qué hay retraso en la traducción?
Un pequeño retraso es normal debido al proceso de:
1. Captura de audio
2. Reconocimiento de voz
3. Traducción
4. Síntesis de voz

### ¿Puedo usar Sinte-Voz con cualquier aplicación?
Sí, funciona con cualquier aplicación que use audio, incluyendo:
- Zoom
- Google Meet
- Microsoft Teams
- Skype
- Aplicaciones de telefonía IP

## Solución de Problemas

### El micrófono USB no es detectado
1. Verifica que está conectado
2. Ejecuta `arecord -l`
3. Reinicia PulseAudio si es necesario
4. Reconecta el dispositivo USB

### No se escucha la voz sintetizada
1. Verifica que "Monitor of Null Output" está seleccionado como micrófono
2. Comprueba que PulseAudio está funcionando
3. Ajusta el volumen del sistema

### La transcripción no es precisa
1. Habla más claro y a velocidad normal
2. Verifica el nivel de ruido ambiente
3. Usa un micrófono de mejor calidad
4. Ajusta la posición del micrófono

## Privacidad y Seguridad

### ¿Se guardan las conversaciones?
No, Sinte-Voz no almacena ninguna conversación por defecto.

### ¿Son seguras las traducciones?
Las traducciones usan servicios de Google, que tienen sus propias políticas de privacidad.

### ¿Necesito una cuenta?
No, Sinte-Voz no requiere registro ni cuenta.

## Contribuir

### ¿Cómo puedo ayudar?
- Reportando bugs en GitHub
- Sugiriendo mejoras
- Contribuyendo código
- Mejorando la documentación
- Traduciendo la interfaz

### ¿Dónde reporto problemas?
Usa el sistema de issues en GitHub: [Issues](https://github.com/JoseLVillaronga/sinte-voz/issues)

### ¿Puedo modificar el código?
Sí, el código es open source bajo licencia MIT. Por favor, comparte tus mejoras con la comunidad.
