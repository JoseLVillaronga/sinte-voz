// Esperar a que el DOM esté completamente cargado
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded');

    // Elementos del DOM
    const elements = {
        messageInput: document.getElementById('message-input'),
        sendBtn: document.getElementById('send-btn'),
        chatMessages: document.getElementById('chat-messages'),
        sourceLang: document.getElementById('sourceLang'),
        targetLang: document.getElementById('targetLang'),
        inputDevice: document.getElementById('inputDevice'),
        virtualMic: document.getElementById('virtualMic'),
        monitorBtn: document.getElementById('monitor-btn'),
        monitorStatus: document.getElementById('monitor-status')
    };

    // Verificar que todos los elementos existen
    console.log('Checking elements...');
    for (const [key, element] of Object.entries(elements)) {
        console.log(`${key}: ${element ? 'Found' : 'Missing'}`);
        if (!element) {
            console.error(`Missing element: ${key}`);
            return; // Detener la ejecución si falta algún elemento
        }
    }

    // Configurar Socket.IO
    console.log('Configuring Socket.IO...');
    const socket = io({
        path: '/socket.io/',
        transports: ['websocket', 'polling']
    });

    // Variables globales
    let selectedInputDevice = null;
    let isMonitoring = false;

    // Cargar dispositivos de audio
    async function loadAudioDevices() {
        try {
            console.log('Loading audio devices...');
            const response = await fetch('/audio_devices');
            const data = await response.json();
            console.log('Devices:', data);
            
            if (data.devices) {
                elements.inputDevice.innerHTML = '<option value="">Seleccione un dispositivo...</option>';
                data.devices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.id;
                    option.textContent = device.name + (device.state === 'RUNNING' ? ' (Activo)' : '');
                    elements.inputDevice.appendChild(option);
                });
            } else if (data.error) {
                console.error('Error loading devices:', data.error);
                elements.inputDevice.innerHTML = '<option value="">Error al cargar dispositivos</option>';
            }
            
            selectedInputDevice = elements.inputDevice.value;
            console.log('Selected device:', selectedInputDevice);
            
        } catch (error) {
            console.error('Error loading audio devices:', error);
        }
    }

    // Event listeners básicos
    elements.inputDevice.addEventListener('change', (e) => {
        selectedInputDevice = e.target.value;
        console.log('Selected device:', selectedInputDevice);
    });

    elements.sendBtn.addEventListener('click', () => {
        const text = elements.messageInput.value.trim();
        if (text) {
            socket.emit('text_to_speech', {
                text: text,
                source_lang: elements.sourceLang.value,
                target_lang: elements.targetLang.value
            });
            addMessage(text, 'sent');
            elements.messageInput.value = '';
        }
    });

    elements.messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            elements.sendBtn.click();
        }
    });

    elements.monitorBtn.addEventListener('click', () => {
        if (!isMonitoring) {
            if (!selectedInputDevice) {
                console.error('No device selected');
                return;
            }
            console.log('Starting monitor with device:', selectedInputDevice);
            socket.emit('start_monitor', {
                device_id: selectedInputDevice,
                source_lang: elements.targetLang.value,
                target_lang: elements.sourceLang.value
            });
        } else {
            console.log('Stopping monitor');
            socket.emit('stop_monitor');
        }
        isMonitoring = !isMonitoring;
        updateMonitoringStatus();
    });

    // Funciones de utilidad
    function updateMonitoringStatus() {
        elements.monitorStatus.textContent = isMonitoring ? 'Activo' : 'Inactivo';
        elements.monitorStatus.className = `badge ${isMonitoring ? 'bg-success' : 'bg-secondary'}`;
        elements.monitorBtn.textContent = isMonitoring ? 'Detener Monitoreo' : 'Iniciar Monitoreo';
        elements.inputDevice.disabled = isMonitoring;
    }

    function addMessage(text, type, timestamps = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        
        // Crear contenedor de texto
        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.textContent = text;
        messageDiv.appendChild(textDiv);
        
        // Agregar timestamps si están disponibles
        if (timestamps) {
            const timeDiv = document.createElement('div');
            timeDiv.className = 'message-time';
            const start = new Date(timestamps.start * 1000).toISOString().substr(11, 8);
            const end = new Date(timestamps.end * 1000).toISOString().substr(11, 8);
            timeDiv.textContent = `${start} - ${end}`;
            messageDiv.appendChild(timeDiv);
        }
        
        elements.chatMessages.appendChild(messageDiv);
        elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
    }

    // Socket events
    socket.on('connect', () => {
        console.log('Connected to server');
        loadAudioDevices();
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from server');
        isMonitoring = false;
        updateMonitoringStatus();
    });

    socket.on('monitor_status', (data) => {
        console.log('Monitor status:', data);
        if (data.status === 'started') {
            isMonitoring = true;
            addMessage('Monitoreo iniciado', 'system');
        } else if (data.status === 'stopped') {
            isMonitoring = false;
            addMessage('Monitoreo detenido', 'system');
        }
        updateMonitoringStatus();
    });

    socket.on('received_message', (data) => {
        if (data.text) {
            const timestamps = data.start_time && data.end_time ? {
                start: data.start_time,
                end: data.end_time
            } : null;
            addMessage(data.text, 'received', timestamps);
        }
    });

    socket.on('error', (data) => {
        console.error('Server error:', data.message);
        addMessage(`Error: ${data.message}`, 'error');
        if (data.fatal) {
            isMonitoring = false;
            updateMonitoringStatus();
        }
    });
});
