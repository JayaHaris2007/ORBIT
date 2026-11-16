const defaultBase = typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000';
const API_BASE_URL = (import.meta.env.VITE_SPIDEY_API_BASE_URL || defaultBase).replace(/\/$/, '');
const ORBIT_TOKEN = (import.meta.env.VITE_ORBIT_TOKEN || '').trim();

export const apiRequest = async (path, options = {}) => {
    const headers = {
        'Content-Type': 'application/json',
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
        throw new Error(payload.detail || payload.error || `S.P.I.D.E.Y request failed (${response.status}).`);
    }
    return payload;
};

export const apiStreamRequest = async (path, options = {}, onEvent) => {
    const headers = {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
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
        throw new Error(payload.detail || payload.error || `S.P.I.D.E.Y request failed (${response.status}).`);
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
