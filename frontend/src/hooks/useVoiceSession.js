import { useCallback, useEffect, useRef, useState } from 'react';
import { emitBrainAudioLevel, emitBrainState } from '../context/SpideyBrainContext';
import { AudioQueue, stopVoiceTurn } from '../services/voiceService';

export function useVoiceSession({ onTranscript = null, onReply = null, audioQueue = null }) {
    const [state, setState] = useState('idle'); // idle | connecting | listening | transcribing | thinking | speaking
    const [transcript, setTranscript] = useState('');
    const [reply, setReply] = useState('');
    const [error, setError] = useState(null);
    const [mode, setMode] = useState('live');
    const [isMuted, setIsMuted] = useState(false);
    const [timing, setTiming] = useState({ speechEnd: 0, transcript: 0, firstSentence: 0, firstAudio: 0, total: 0 });

    const modeRef = useRef('live');
    const mutedRef = useRef(false);
    const sessionEpochRef = useRef(0);
    const wsRef = useRef(null);
    const onTranscriptRef = useRef(onTranscript);
    const onReplyRef = useRef(onReply);
    useEffect(() => {
        onTranscriptRef.current = onTranscript;
        onReplyRef.current = onReply;
    }, [onTranscript, onReply]);

    const micStreamRef = useRef(null);
    const audioContextRef = useRef(null);
    const workletNodeRef = useRef(null);
    const queueRef = useRef(audioQueue || new AudioQueue());
    const timingRef = useRef({ speechEnd: 0, transcript: 0, firstSentence: 0, firstAudio: 0 });
    const nextExpectedAudioSeqRef = useRef(null);

    const getWsUrl = () => {
        if (import.meta.env.VITE_SPIDEY_API_BASE_URL) {
            const base = import.meta.env.VITE_SPIDEY_API_BASE_URL.replace(/^http/, 'ws').replace(/\/$/, '');
            return `${base}/ws/voice`;
        }
        if (typeof window !== 'undefined') {
            const host = window.location.hostname || '127.0.0.1';
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            if (window.location.port === '3000') {
                return `${protocol}//${host}:8000/ws/voice`;
            }
            return `${protocol}//${window.location.host}/ws/voice`;
        }
        return 'ws://127.0.0.1:8000/ws/voice';
    };

    const getWsProtocols = () => {
        const token = (import.meta.env.VITE_ORBIT_TOKEN || '').trim();
        return token ? ['orbit-v1', `orbit-token.${token}`] : undefined;
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
        sessionEpochRef.current += 1;
        cleanupAudioCapture();
        if (wsRef.current) {
            const sock = wsRef.current;
            wsRef.current = null;
            try {
                if (sock.readyState === WebSocket.OPEN) {
                    sock.send(JSON.stringify({ type: 'stop' }));
                }
                sock.close();
            } catch { /* ignore */ }
        }
        queueRef.current.stop();
        stopVoiceTurn().catch(() => {});
        mutedRef.current = false;
        setIsMuted(false);
        setState('idle');
        emitBrainAudioLevel(0);
        emitBrainState('idle');
        setTranscript('');
        setReply('');
    }, [cleanupAudioCapture]);

    const toggleMute = useCallback(() => {
        const next = !mutedRef.current;
        mutedRef.current = next;
        setIsMuted(next);
        if (next) {
            emitBrainAudioLevel(0);
        }
    }, []);

    const interrupt = useCallback(() => {
        queueRef.current.stop();
        emitBrainAudioLevel(0);
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'interrupt' }));
            if (modeRef.current === 'live') {
                setState('listening');
                emitBrainState('listening');
            }
        }
    }, []);

    const commitUtterance = useCallback(() => {
        if (modeRef.current === 'ptt') {
            cleanupAudioCapture();
        }
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
            const epoch = sessionEpochRef.current;
            setMode(sessionMode);
            modeRef.current = sessionMode;
            mutedRef.current = false;
            setIsMuted(false);
            setError(null);
            setTranscript('');
            setReply('');
            setState('connecting');
            emitBrainState('listening');
            timingRef.current = { speechEnd: 0, transcript: 0, firstSentence: 0, firstAudio: 0 };

            try {
                // Ensure browser AudioContext for TTS playback is unlocked on user gesture
                queueRef.current?.ensureContext?.();

                // 1. Get mic permission with echo cancellation
                const stream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true,
                        channelCount: 1,
                    },
                });
                if (epoch !== sessionEpochRef.current) {
                    stream.getTracks().forEach((t) => t.stop());
                    return;
                }
                micStreamRef.current = stream;

                // 2. Setup AudioContext (prefer 16 kHz if supported)
                let audioCtx;
                try {
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
                } catch {
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                }
                if (audioCtx.state === 'suspended') {
                    await audioCtx.resume().catch(() => {});
                }
                if (epoch !== sessionEpochRef.current) {
                    audioCtx.close().catch(() => {});
                    stream.getTracks().forEach((t) => t.stop());
                    return;
                }
                audioContextRef.current = audioCtx;

                // 3. Load AudioWorklet
                await audioCtx.audioWorklet.addModule('/audio-worklet/pcm-capture.js');
                if (epoch !== sessionEpochRef.current) {
                    cleanupAudioCapture();
                    return;
                }
                const source = audioCtx.createMediaStreamSource(stream);
                const workletNode = new AudioWorkletNode(audioCtx, 'pcm-capture-processor');
                workletNodeRef.current = workletNode;
                source.connect(workletNode);

                // 4. Connect WebSocket (passes token via subprotocol so it never enters server URL logs)
                const ws = new WebSocket(getWsUrl(), getWsProtocols());
                ws.binaryType = 'arraybuffer';
                wsRef.current = ws;

                ws.onopen = () => {
                    if (epoch !== sessionEpochRef.current) {
                        ws.close();
                        return;
                    }
                    ws.send(JSON.stringify({ type: 'start', mode: sessionMode, chat_id: chatId }));
                    setState('listening');
                    emitBrainState('listening');
                };

                workletNode.port.onmessage = (event) => {
                    if (epoch !== sessionEpochRef.current) return;
                    if (mutedRef.current) {
                        emitBrainAudioLevel(0);
                        return;
                    }
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
                            emitBrainAudioLevel(Math.min(1, rms * 4.8));
                        }
                    }
                };

                ws.onmessage = async (event) => {
                    if (epoch !== sessionEpochRef.current) return;
                    if (typeof event.data === 'string') {
                        try {
                            const data = JSON.parse(event.data);
                            if (data.type === 'state') {
                                const stillSpeakingLocally =
                                    (data.value === 'listening' || data.value === 'idle')
                                    && queueRef.current?.isPlaybackActive?.(0);
                                const nextSt = stillSpeakingLocally ? 'speaking' : data.value;
                                setState(nextSt);
                                emitBrainState(nextSt);
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
                                onTranscriptRef.current?.(data.text);
                            } else if (data.type === 'reply_partial') {
                                setReply(data.text);
                                if (!timingRef.current.firstSentence && timingRef.current.transcript) {
                                    timingRef.current.firstSentence = performance.now();
                                }
                            } else if (data.type === 'reply') {
                                setReply(data.text);
                                if (!timingRef.current.firstSentence) {
                                    timingRef.current.firstSentence = performance.now();
                                }
                                onReplyRef.current?.(data.text, data);
                            } else if (data.type === 'audio') {
                                nextExpectedAudioSeqRef.current = data;
                                setState('speaking');
                                emitBrainState('speaking');
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
                                total: Math.round(t.firstAudio - t.speechEnd),
                            });
                        }
                        queueRef.current.push(event.data, queueRef.current.epoch);
                    }
                };

                ws.onerror = (err) => {
                    if (epoch !== sessionEpochRef.current) return;
                    console.error('Voice WebSocket error:', err);
                    setError('Voice WebSocket connection error. Please ensure the ORBIT server is running.');
                    cleanupAudioCapture();
                    setState('idle');
                    emitBrainAudioLevel(0);
                    emitBrainState('idle');
                };

                ws.onclose = () => {
                    if (epoch !== sessionEpochRef.current) return;
                    cleanupAudioCapture();
                    setState('idle');
                    emitBrainAudioLevel(0);
                    emitBrainState('idle');
                };
            } catch (err) {
                if (epoch !== sessionEpochRef.current) return;
                console.error('Failed to initialize mic/voice session:', err);
                setError(err.message || 'Microphone access denied or unavailable.');
                cleanupAudioCapture();
                setState('idle');
                emitBrainAudioLevel(0);
                emitBrainState('idle');
            }
        },
        [cleanupAudioCapture, stopSession]
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
        isMuted,
        timing,
        startSession,
        stopSession,
        toggleMute,
        commitUtterance,
        interrupt,
        updateChatId,
        isIdle: state === 'idle',
        isLiveActive: mode === 'live' && state !== 'idle',
    };
}
