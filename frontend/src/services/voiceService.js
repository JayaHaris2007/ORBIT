import { API_BASE_URL, apiRequest } from './api';

export class AudioQueue {
    constructor() {
        this.ctx = null;
        this.analyser = null;
        this.freqData = null;
        this.queue = [];
        this.playing = null;
        this.lastEndedAt = 0;
        this.epoch = 0;
        this.onIdle = null;
        this.onPlay = null;
        this.idleListeners = new Set();
    }

    addIdleListener(fn) {
        this.idleListeners.add(fn);
        return () => this.idleListeners.delete(fn);
    }

    isPlaybackActive(tailMs = 500) {
        if (this.playing || this.queue.length > 0) return true;
        if (this.lastEndedAt > 0 && typeof performance !== 'undefined') {
            return (performance.now() - this.lastEndedAt) < tailMs;
        }
        return false;
    }

    ensureContext() {
        if (typeof window === 'undefined') return null;
        if (!this.ctx) {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (AudioCtx) {
                this.ctx = new AudioCtx();
                try {
                    this.analyser = this.ctx.createAnalyser();
                    this.analyser.fftSize = 64;
                    this.analyser.smoothingTimeConstant = 0.7;
                    this.analyser.connect(this.ctx.destination);
                    this.freqData = new Uint8Array(this.analyser.frequencyBinCount);
                } catch {
                    this.analyser = null;
                }
            }
        }
        if (this.ctx && this.ctx.state === 'suspended') {
            this.ctx.resume().catch(() => {});
        }
        return this.ctx;
    }

    getOutputLevel() {
        if (!this.playing || !this.analyser || !this.freqData) return 0;
        try {
            this.analyser.getByteFrequencyData(this.freqData);
            let sum = 0;
            for (let i = 0; i < this.freqData.length; i++) {
                sum += this.freqData[i];
            }
            return Math.min(1, (sum / (this.freqData.length * 255)) * 2.2);
        } catch {
            return 0;
        }
    }

    async push(arrayBuffer, epoch) {
        if (epoch !== this.epoch) return; // Stale audio from a stopped turn
        this.ensureContext();
        if (!this.ctx) return;
        if (this.ctx.state === 'suspended') {
            await this.ctx.resume().catch(() => {});
        }
        try {
            const buf = await this.ctx.decodeAudioData(arrayBuffer.slice(0));
            if (epoch !== this.epoch) return;
            this.queue.push(buf);
            if (!this.playing) this._next();
        } catch (err) {
            console.error('Audio decode error:', err);
        }
    }

    _next() {
        const buf = this.queue.shift();
        if (!buf) {
            this.playing = null;
            this.lastEndedAt = typeof performance !== 'undefined' ? performance.now() : Date.now();
            this.onIdle?.();
            for (const fn of this.idleListeners) fn();
            return;
        }
        const src = this.ctx.createBufferSource();
        src.buffer = buf;
        if (this.analyser) {
            src.connect(this.analyser);
        } else {
            src.connect(this.ctx.destination);
        }
        src.onended = () => this._next();
        this.playing = src;
        this.onPlay?.();
        src.start();
    }

    setCallbacks(onPlay, onIdle) {
        this.onPlay = onPlay;
        this.onIdle = onIdle;
    }

    stop() {
        this.epoch++;
        this.queue = [];
        try {
            this.playing?.stop();
        } catch { /* ignore */ }
        this.playing = null;
        this.onIdle?.();
    }
}

let _sharedAudioQueue = null;
export function getSharedAudioQueue() {
    if (typeof window === 'undefined') return null;
    if (!_sharedAudioQueue) {
        _sharedAudioQueue = new AudioQueue();
    }
    return _sharedAudioQueue;
}

export async function fetchVoiceSettings() {
    return apiRequest('/api/voice/settings');
}

export async function updateVoiceSettings(payload) {
    return apiRequest('/api/voice/settings', {
        method: 'PUT',
        body: JSON.stringify(payload),
    });
}

export async function fetchTTSAudio(text, signal = null) {
    const token = (import.meta.env.VITE_ORBIT_TOKEN || '').trim();
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['x-orbit-token'] = token;

    const res = await fetch(`${API_BASE_URL}/api/voice/tts`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ text }),
        signal,
    });
    if (!res.ok) {
        const errorText = await res.text().catch(() => 'Unknown error');
        throw new Error(`TTS failed (${res.status}): ${errorText}`);
    }
    return res.arrayBuffer();
}

export async function stopVoiceTurn(sessionId = 'default') {
    return apiRequest('/api/voice/stop', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId }),
    });
}

export function summarizeForSpeechClient(text, maxItems = 4, maxProseChars = 260) {
    if (!text || !text.trim()) return '';
    const withoutThink = text.replace(/<think>[\s\S]*?<\/think>/gi, ' ').trim();
    const hasCodeBlock = /```[\s\S]*?```/.test(withoutThink);
    const withoutCode = withoutThink.replace(/```[\s\S]*?```/g, ' ').trim();
    const rawLines = withoutCode.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (!rawLines.length) return text.trim();

    const sectionHeaderRe = /^(?:#{1,6}\s*)?([A-Za-z][A-Za-z0-9\s/&-]{0,30}):\s*$/;
    const pastLabels = ['past', 'completed', 'archived', 'previous', 'ended', 'closed', 'done'];
    const bulletRe = /^([-*+•]|\d+[.)])\s+/;
    const dashSplitRe = /\s+(?:—|–|--|-)\s+/;

    const introLines = [];
    const outroLines = [];
    const primaryItems = [];
    const pastItems = [];
    let currentSection = 'primary';
    let seenListOrSection = false;

    const extractHeadline = (line) => {
        let cleaned = line.replace(bulletRe, '').replace(/(\*\*|__|\*|_)/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').trim();
        const parts = cleaned.split(dashSplitRe);
        let head = (parts[0] || '').trim();
        if (head.includes(':')) {
            const [left, right] = head.split(':', 2);
            if (left.trim().length >= 2 && left.trim().length <= 50 && right && right.trim()) {
                head = left.trim();
            }
        }
        head = head.replace(/\s*\([^)]{1,40}\)\s*$/, '').trim();
        return head.replace(/[.,;:\-—–\s]+$/, '');
    };

    const joinNatural = (items) => {
        if (!items.length) return '';
        if (items.length === 1) return items[0];
        if (items.length === 2) return `${items[0]} and ${items[1]}`;
        return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`;
    };

    for (const ln of rawLines) {
        const plainLn = ln.replace(/(\*\*|__|\*|_)/g, '');
        const secMatch = plainLn.match(sectionHeaderRe);
        if (secMatch) {
            seenListOrSection = true;
            const label = secMatch[1].trim().toLowerCase();
            currentSection = pastLabels.some((w) => label.includes(w)) ? 'past' : 'primary';
            continue;
        }
        const isBullet = bulletRe.test(ln);
        const isDashItem = ln.split(dashSplitRe).length >= 2;
        if (isBullet || isDashItem) {
            seenListOrSection = true;
            const headline = extractHeadline(ln);
            if (headline) {
                if (currentSection === 'past') pastItems.push(headline);
                else primaryItems.push(headline);
            }
            continue;
        }
        if (!seenListOrSection) introLines.push(ln);
        else outroLines.push(ln);
    }

    const chosenItems = primaryItems.length ? primaryItems : pastItems;
    if (chosenItems.length >= 2 || (chosenItems.length === 1 && (pastItems.length > 0 || rawLines.length >= 3))) {
        const displayItems = chosenItems.slice(0, maxItems);
        const extraCount = chosenItems.length - displayItems.length;
        let joined = joinNatural(displayItems);
        if (extraCount > 0) joined = `${joined}, and ${extraCount} more`;

        const spokenParts = [];
        if (introLines.length) {
            const intro = introLines[0].replace(/[:.\s]+$/, '');
            spokenParts.push(`${intro}: ${joined}.`);
        } else {
            spokenParts.push(`The main ones are ${joined}.`);
        }
        if (outroLines.length) {
            const lastOutro = outroLines[outroLines.length - 1];
            if (lastOutro.includes('?') || lastOutro.length <= 90) {
                spokenParts.push(lastOutro);
            }
        }
        return spokenParts.join(' ');
    }

    if (withoutCode.length <= maxProseChars && !hasCodeBlock) {
        return withoutCode;
    }

    const sentenceChunks = withoutCode.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);
    if (!sentenceChunks.length) return withoutCode;
    let summary = sentenceChunks.slice(0, 2);
    if (summary.join(' ').length > maxProseChars) summary = sentenceChunks.slice(0, 1);
    if (hasCodeBlock) {
        summary.push("I've put the code and details in the chat.");
    } else if (sentenceChunks.length > summary.length) {
        const lastSent = sentenceChunks[sentenceChunks.length - 1];
        if (lastSent.endsWith('?') && !summary.includes(lastSent) && lastSent.length <= 100) {
            summary.push(lastSent);
        }
    }
    return summary.join(' ');
}

export function splitSentencesClient(text, maxChars = 200) {
    if (!text || !text.trim()) return [];
    const normalized = text.replace(/\s+/g, ' ').trim();
    const rawChunks = normalized.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [normalized];
    const results = [];
    for (const chunk of rawChunks) {
        const trimmed = chunk.trim();
        if (!trimmed) continue;
        if (trimmed.length <= maxChars) {
            results.push(trimmed);
        } else {
            const words = trimmed.split(' ');
            let current = '';
            for (const word of words) {
                if ((current + ' ' + word).trim().length <= maxChars) {
                    current = (current + ' ' + word).trim();
                } else {
                    if (current) results.push(current);
                    current = word;
                }
            }
            if (current) results.push(current);
        }
    }
    return results;
}
