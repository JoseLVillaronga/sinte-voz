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
            const response = await fetch('/audio-devices');
            const devices = await response.json();
            console.log('Devices:', devices);
            
            elements.inputDevice.innerHTML = '';
            devices.input_devices.forEach(device => {
                const option = document.createElement('option');
                option.value = device.id;
                option.text = device.name;
                elements.inputDevice.appendChild(option);
            });
            
            if (devices.virtual_mic && devices.virtual_mic.description) {
                elements.virtualMic.textContent = `${devices.virtual_mic.source_name} (${devices.virtual_mic.description})`;
            } else {
                elements.virtualMic.textContent = 'No encontrado';
            }
            
            selectedInputDevice = elements.inputDevice.value;
            
        } catch (error) {
            console.error('Error loading audio devices:', error);
        }
    }

    // Event listeners básicos
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
            socket.emit('start_usb_monitor', {
                device_id: selectedInputDevice,
                source_lang: elements.targetLang.value,
                target_lang: elements.sourceLang.value
            });
        } else {
            socket.emit('stop_usb_monitor');
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

    function addMessage(text, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        messageDiv.textContent = text;
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

    socket.on('received_message', (data) => {
        if (data.text) {
            addMessage(data.text, 'received');
        }
    });

    socket.on('error', (data) => {
        console.error('Server error:', data.message);
        addMessage(`Error: ${data.message}`, 'error');
    });
});
