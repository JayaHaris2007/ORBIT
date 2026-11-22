import { useCallback, useEffect, useRef, useState } from 'react';
import { emitBrainAudioLevel, emitBrainState } from '../context/SpideyBrainContext';
import { API_BASE_URL } from '../services/api';
import { AudioQueue, stopVoiceTurn } from '../services/voiceService';

export function useVoiceSession({ onTranscript = null, onReply = null, audioQueue = null }) {
    const [state, setState] = useState('idle'); // idle | listening | transcribing | thinking | speaking
    const [transcript, setTranscript] = useState('');
    const [reply, setReply] = useState('');
    const [error, setError] = useState(null);
    const [mode, setMode] = useState('live');
    const [timing, setTiming] = useState({ speechEnd: 0, transcript: 0, firstSentence: 0, firstAudio: 0, total: 0 });

    const modeRef = useRef('live');
    const wsRef = useRef(null);
    const micStreamRef = useRef(null);
    const audioContextRef = useRef(null);
    const workletNodeRef = useRef(null);
    const queueRef = useRef(audioQueue || new AudioQueue());
    const timingRef = useRef({ speechEnd: 0, transcript: 0, firstSentence: 0, firstAudio: 0 });
    const nextExpectedAudioSeqRef = useRef(null);

    const getWsUrl = () => {
        const token = (import.meta.env.VITE_ORBIT_TOKEN || '').trim();
        const tokenQuery = token ? `?token=${encodeURIComponent(token)}` : '';
        if (import.meta.env.VITE_SPIDEY_API_BASE_URL) {
            const base = import.meta.env.VITE_SPIDEY_API_BASE_URL.replace(/^http/, 'ws').replace(/\/$/, '');
            return `${base}/ws/voice${tokenQuery}`;
        }
        if (typeof window !== 'undefined') {
            const host = window.location.hostname || '127.0.0.1';
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            if (window.location.port === '3000') {
                return `${protocol}//${host}:8000/ws/voice${tokenQuery}`;
            }
            return `${protocol}//${window.location.host}/ws/voice${tokenQuery}`;
        }
        return `ws://127.0.0.1:8000/ws/voice${tokenQuery}`;
    };

    const cleanupAudioCapture = useCallback(() => {
        if (workletNodeRef.current) {
            try {
                workletNodeRef.current.disconnect();
                workletNodeRef.current.port.close();
            } catch { /* ignore */ }
            workletNodeRef.current = null;
        }
        if (micStreamRef.current) {
            micStreamRef.current.getTracks().forEach((track) => track.stop());
            micStreamRef.current = null;
        }
        if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
            try {
                audioContextRef.current.close();
            } catch { /* ignore */ }
            audioContextRef.current = null;
        }
    }, []);

    const stopSession = useCallback(() => {
        cleanupAudioCapture();
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            try {
                wsRef.current.send(JSON.stringify({ type: 'stop' }));
                wsRef.current.close();
            } catch { /* ignore */ }
        }
        wsRef.current = null;
        queueRef.current.stop();
        stopVoiceTurn().catch(() => {});
        setState('idle');
        emitBrainAudioLevel(0);
        emitBrainState('idle');
        setTranscript('');
    }, [cleanupAudioCapture]);

    const interrupt = useCallback(() => {
        queueRef.current.stop();
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'interrupt' }));
        }
    }, []);

    const commitUtterance = useCallback(() => {
        cleanupAudioCapture();
        emitBrainAudioLevel(0);
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            try {
                wsRef.current.send(JSON.stringify({ type: 'commit' }));
            } catch { /* ignore */ }
        }
    }, [cleanupAudioCapture]);

    const updateChatId = useCallback((chatId) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN && chatId) {
            try {
                wsRef.current.send(JSON.stringify({ type: 'set_chat', chat_id: chatId }));
            } catch { /* ignore */ }
        }
    }, []);

    const startSession = useCallback(
        async (sessionMode = 'live', chatId = null) => {
            stopSession();
            setMode(sessionMode);
            modeRef.current = sessionMode;
            setError(null);
            setTranscript('');
            setReply('');
            timingRef.current = { speechEnd: 0, transcript: 0, firstSentence: 0, firstAudio: 0 };

            try {
                // 1. Get mic permission with echo cancellation
                const stream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true,
                        channelCount: 1
                    }
                });
                micStreamRef.current = stream;

                // 2. Setup AudioContext (prefer 16 kHz if supported)
                let audioCtx;
                try {
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
                } catch {
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                }
                audioContextRef.current = audioCtx;

                // 3. Load AudioWorklet
                await audioCtx.audioWorklet.addModule('/audio-worklet/pcm-capture.js');
                const source = audioCtx.createMediaStreamSource(stream);
                const workletNode = new AudioWorkletNode(audioCtx, 'pcm-capture-processor');
                workletNodeRef.current = workletNode;
                source.connect(workletNode);

                // 4. Connect WebSocket
                const ws = new WebSocket(getWsUrl());
                ws.binaryType = 'arraybuffer';
                wsRef.current = ws;

                ws.onopen = () => {
                    ws.send(JSON.stringify({ type: 'start', mode: sessionMode, chat_id: chatId }));
                    setState('listening');
                    emitBrainState('listening');
                };

                workletNode.port.onmessage = (event) => {
                    // Gate mic capture while browser TTS speakers are playing (+500ms echo tail)
                    // so Spidey never hears its own voice or cuts itself off mid-sentence.
                    if (queueRef.current?.isPlaybackActive?.(500)) {
                        emitBrainAudioLevel(0);
                        return;
                    }
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send(event.data); // Binary PCM frame (100 ms)
                    }
                    if (event.data instanceof ArrayBuffer) {
                        const samples = new Int16Array(event.data);
                        if (samples.length) {
                            let sumSq = 0;
                            const step = Math.max(1, Math.floor(samples.length / 64));
                            let count = 0;
                            for (let i = 0; i < samples.length; i += step) {
                                const norm = samples[i] / 32768;
                                sumSq += norm * norm;
                                count++;
                            }
                            const rms = Math.sqrt(sumSq / Math.max(1, count));
                            emitBrainAudioLevel(Math.min(1, rms * 4.5));
                        }
                    }
                };

                ws.onmessage = async (event) => {
                    if (typeof event.data === 'string') {
                        try {
                            const data = JSON.parse(event.data);
                            if (data.type === 'state') {
                                const stillSpeakingLocally =
                                    (data.value === 'listening' || data.value === 'idle')
                                    && queueRef.current?.isPlaybackActive?.(0);
                                setState(stillSpeakingLocally ? 'speaking' : data.value);
                                emitBrainState(stillSpeakingLocally ? 'speaking' : data.value);
                                if (data.value === 'transcribing') {
                                    timingRef.current.speechEnd = performance.now();
                                }
                                if (data.value === 'idle' && sessionMode === 'ptt') {
                                    cleanupAudioCapture();
                                    emitBrainAudioLevel(0);
                                    try {
                                        ws.close();
                                    } catch { /* ignore */ }
                                }
                            } else if (data.type === 'transcript') {
                                setTranscript(data.text);
                                const now = performance.now();
                                timingRef.current.transcript = now;
                                onTranscript?.(data.text);
                            } else if (data.type === 'reply') {
                                setReply(data.text);
                                timingRef.current.firstSentence = performance.now();
                                onReply?.(data.text, data);
                            } else if (data.type === 'audio') {
                                nextExpectedAudioSeqRef.current = data;
                            } else if (data.type === 'error') {
                                setError(data.message);
                            }
                        } catch (err) {
                            console.error('WS JSON parse error:', err);
                        }
                    } else if (event.data instanceof ArrayBuffer) {
                        // Binary WAV frame received
                        nextExpectedAudioSeqRef.current = null;
                        if (!timingRef.current.firstAudio && timingRef.current.speechEnd) {
                            const now = performance.now();
                            timingRef.current.firstAudio = now;
                            const t = timingRef.current;
                            setTiming({
                                speechEnd: t.speechEnd,
                                transcript: Math.round(t.transcript - t.speechEnd),
                                firstSentence: Math.round(t.firstSentence - t.transcript),
                                firstAudio: Math.round(t.firstAudio - t.firstSentence),
                                total: Math.round(t.firstAudio - t.speechEnd)
                            });
                        }
                        queueRef.current.push(event.data, queueRef.current.epoch);
                    }
                };

                ws.onerror = (err) => {
                    console.error('Voice WebSocket error:', err);
                    setError('Voice WebSocket connection error. Please ensure the S.P.I.D.E.Y server is running.');
                    cleanupAudioCapture();
                    setState('idle');
                    emitBrainAudioLevel(0);
                    emitBrainState('idle');
                };

                ws.onclose = () => {
                    cleanupAudioCapture();
                    setState('idle');
                    emitBrainAudioLevel(0);
                    emitBrainState('idle');
                };
            } catch (err) {
                console.error('Failed to initialize mic/voice session:', err);
                setError(err.message || 'Microphone access denied or unavailable.');
                cleanupAudioCapture();
                setState('idle');
            }
        },
        [cleanupAudioCapture, stopSession, onTranscript, onReply]
    );

    useEffect(() => {
        const q = queueRef.current;
        if (!q?.addIdleListener) return undefined;
        return q.addIdleListener(() => {
            const wsOpen = wsRef.current && wsRef.current.readyState === WebSocket.OPEN;
            if (wsOpen && modeRef.current === 'live') {
                setState('listening');
                emitBrainState('listening');
            } else {
                setState((prev) => (prev === 'speaking' ? 'idle' : prev));
            }
        });
    }, []);

    useEffect(() => {
        return () => {
            stopSession();
        };
    }, [stopSession]);

    return {
        state,
        transcript,
        reply,
        error,
        mode,
        timing,
        startSession,
        stopSession,
        commitUtterance,
        interrupt,
        updateChatId,
        isIdle: state === 'idle'
    };
}

