const defaultBase = typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000';
const API_BASE_URL = (import.meta.env.VITE_SPIDEY_API_BASE_URL || defaultBase).replace(/\/$/, '');
const ORBIT_TOKEN = (import.meta.env.VITE_ORBIT_TOKEN || '').trim();

export const FRONTEND_CLIENT_ID = (
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `tab-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
);

export const sendFrontendPresence = (active, chatId = null, { keepalive = false } = {}) => {
    const headers = {
        'Content-Type': 'application/json',
        'X-Orbit-Client-Id': FRONTEND_CLIENT_ID,
    };
    if (ORBIT_TOKEN) {
        headers['x-orbit-token'] = ORBIT_TOKEN;
    }
    const payload = {
        active: Boolean(active),
        client_id: FRONTEND_CLIENT_ID,
        ...(chatId ? { chat_id: chatId } : {}),
    };
    try {
        return fetch(`${API_BASE_URL}/api/frontend/presence`, {
            method: 'POST',
            headers,
            body: JSON.stringify(payload),
            keepalive: Boolean(keepalive),
        }).catch(() => {});
    } catch {
        return Promise.resolve();
    }
};

export const GEMINI_KEY_STORAGE = 'spidey_gemini_api_key';
export const GEMINI_MODEL_STORAGE = 'spidey_gemini_model';
export const OLLAMA_MODEL_STORAGE = 'spidey_ollama_model';
export const DEFAULT_GEMINI_MODEL = 'gemini-3.5-flash';

const DEPRECATED_GEMINI_MODELS = new Set(['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash']);

export const getOllamaModelConfig = () => {
    try {
        return (localStorage.getItem(OLLAMA_MODEL_STORAGE) || '').trim();
    } catch {
        return '';
    }
};

export const getGeminiConfig = () => {
    try {
        const apiKey = (localStorage.getItem(GEMINI_KEY_STORAGE) || '').trim();
        let model = (localStorage.getItem(GEMINI_MODEL_STORAGE) || DEFAULT_GEMINI_MODEL).trim() || DEFAULT_GEMINI_MODEL;
        if (DEPRECATED_GEMINI_MODELS.has(model) || (model === 'gemini-4-hydrogen' && !localStorage.getItem('spidey_gemini_model_v35'))) {
            model = DEFAULT_GEMINI_MODEL;
            localStorage.setItem(GEMINI_MODEL_STORAGE, model);
            localStorage.setItem('spidey_gemini_model_v35', '1');
        }
        return { apiKey, model };
    } catch {
        return { apiKey: '', model: DEFAULT_GEMINI_MODEL };
    }
};

export const getGeminiHeaders = () => {
    const headers = {};
    const ollamaModel = getOllamaModelConfig();
    if (ollamaModel) {
        headers['X-Ollama-Model'] = ollamaModel;
    }
    const { apiKey, model } = getGeminiConfig();
    if (apiKey) {
        headers['X-Gemini-Api-Key'] = apiKey;
        headers['X-Gemini-Model'] = model;
    }
    return headers;
};

export const apiRequest = async (path, options = {}) => {
    const headers = {
        'Content-Type': 'application/json',
        'X-Orbit-Client-Id': FRONTEND_CLIENT_ID,
        ...getGeminiHeaders(),
        ...(options.headers || {})
    };
    if (ORBIT_TOKEN) {
        headers['x-orbit-token'] = ORBIT_TOKEN;
    }
    const response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(payload.detail || payload.error || `ORBIT request failed (${response.status}).`);
    }
    return payload;
};

export const apiStreamRequest = async (path, options = {}, onEvent) => {
    const headers = {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...getGeminiHeaders(),
        ...(options.headers || {})
    };
    if (ORBIT_TOKEN) {
        headers['x-orbit-token'] = ORBIT_TOKEN;
    }
    const response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers
    });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || payload.error || `ORBIT request failed (${response.status}).`);
    }
    if (!response.body) {
        throw new Error('Streaming is not supported by this browser.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    const processChunk = (rawBlock) => {
        const lines = rawBlock.split(/\r?\n/);
        for (const line of lines) {
            if (!line.startsWith('data:')) continue;
            const jsonText = line.slice(5).trim();
            if (!jsonText) continue;
            try {
                const evt = JSON.parse(jsonText);
                onEvent?.(evt);
            } catch {
                // Ignore malformed SSE event line
            }
        }
    };

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split(/\r?\n\r?\n/);
        buffer = parts.pop() || '';
        for (const part of parts) {
            if (part.trim()) processChunk(part);
        }
    }
    if (buffer.trim()) {
        processChunk(buffer);
    }
};

export { API_BASE_URL, ORBIT_TOKEN };
