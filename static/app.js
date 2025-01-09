// Configurar Socket.IO
const socket = io({
    path: '/socket.io/',
    transports: ['websocket', 'polling']
});

let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let selectedInputDevice = null;
let selectedOutputDevice = null;

// Elementos del DOM
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const voiceBtn = document.getElementById('voice-btn');
const chatMessages = document.getElementById('chat-messages');
const sourceLang = document.getElementById('sourceLang');
const targetLang = document.getElementById('targetLang');
const inputDeviceSelect = document.getElementById('inputDevice');
const outputDeviceSelect = document.getElementById('outputDevice');
const virtualMicSpan = document.getElementById('virtualMic');

// Cargar dispositivos de audio
async function loadAudioDevices() {
    try {
        const response = await fetch('/audio-devices');
        const devices = await response.json();
        
        // Limpiar opciones actuales
        inputDeviceSelect.innerHTML = '';
        outputDeviceSelect.innerHTML = '';
        
        // Agregar dispositivos de entrada
        devices.input_devices.forEach(device => {
            const option = document.createElement('option');
            option.value = device.id;
            option.text = device.name;
            inputDeviceSelect.appendChild(option);
        });
        
        // Agregar dispositivos de salida
        devices.output_devices.forEach(device => {
            const option = document.createElement('option');
            option.value = device.id;
            option.text = device.name;
            outputDeviceSelect.appendChild(option);
        });
        
        // Mostrar micrófono virtual
        if (devices.virtual_mic && devices.virtual_mic.description) {
            virtualMicSpan.textContent = `${devices.virtual_mic.source_name} (${devices.virtual_mic.description})`;
        } else {
            virtualMicSpan.textContent = 'No encontrado - Asegúrate de que el módulo virtual-source está cargado';
        }
        
        // Guardar selecciones
        selectedInputDevice = inputDeviceSelect.value;
        selectedOutputDevice = outputDeviceSelect.value;
        
    } catch (error) {
        console.error('Error loading audio devices:', error);
    }
}

// Cargar dispositivos al inicio
loadAudioDevices();

// Eventos de cambio de dispositivo
inputDeviceSelect.addEventListener('change', (e) => {
    selectedInputDevice = e.target.value;
});

outputDeviceSelect.addEventListener('change', (e) => {
    selectedOutputDevice = e.target.value;
});

// Manejar mensajes del servidor
socket.on('connect', () => {
    console.log('Conectado al servidor');
});

socket.on('disconnect', () => {
    console.log('Desconectado del servidor');
});

socket.on('speech_to_text_response', (data) => {
    if (data.text) {
        addMessage(data.text, 'received');
    }
});

socket.on('text_to_speech_response', async (data) => {
    try {
        const audio = new Audio(data.audio_url);
        await audio.play();
    } catch (error) {
        console.error('Error playing audio:', error);
    }
});

socket.on('error', (data) => {
    console.error('Error:', data.message);
});

// Eventos de botones
sendBtn.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

voiceBtn.addEventListener('click', toggleRecording);

// Funciones
function sendMessage() {
    const text = messageInput.value.trim();
    if (text) {
        socket.emit('text_to_speech', {
            text: text,
            source_lang: sourceLang.value,
            target_lang: targetLang.value
        });
        addMessage(text, 'sent');
        messageInput.value = '';
    }
}

function addMessage(text, type) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', type);
    messageDiv.textContent = text;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function toggleRecording() {
    if (!isRecording) {
        try {
            const constraints = {
                audio: {
                    deviceId: selectedInputDevice ? { exact: selectedInputDevice } : undefined
                }
            };
            
            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];

            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const reader = new FileReader();
                reader.readAsDataURL(audioBlob);
                reader.onloadend = () => {
                    const base64Audio = reader.result.split(',')[1];
                    socket.emit('speech_to_text', {
                        audio: base64Audio,
                        source_lang: sourceLang.value,
                        target_lang: targetLang.value
                    });
                };
            };

            mediaRecorder.start();
            isRecording = true;
            voiceBtn.classList.add('recording');
        } catch (err) {
            console.error('Error accessing microphone:', err);
        }
    } else {
        mediaRecorder.stop();
        isRecording = false;
        voiceBtn.classList.remove('recording');
    }
}
