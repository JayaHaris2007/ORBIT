import { useState, useEffect, useRef, useCallback } from 'react';
import { emitBrainAudioLevel, emitBrainPulse, emitBrainState } from '../context/SpideyBrainContext';
import { getGeminiConfig, getGeminiHeaders } from '../services/api';

const ORBIT_TOKEN = (import.meta.env.VITE_ORBIT_TOKEN || '').trim();
const getAuthHeaders = (extra = {}) => ({
  ...getGeminiHeaders(),
  ...extra,
  ...(ORBIT_TOKEN ? { 'x-orbit-token': ORBIT_TOKEN } : {}),
});

export function useOrbitAgent(activeChatIdProp) {
  const [messages, setMessages] = useState([]);
  const [reminders, setReminders] = useState([]);
  const [connected, setConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const wsRef = useRef(null);
  const audioRef = useRef(null);
  const audioCtxRef = useRef(null);
  const mediaStreamRef = useRef(null);

  // Helper to read current active chat id
  const getActiveChatId = useCallback(() => {
    if (activeChatIdProp && typeof activeChatIdProp === 'string' && activeChatIdProp.trim()) {
      return activeChatIdProp.trim();
    }
    try {
      const stored = localStorage.getItem('spidey_active_chat_id') || localStorage.getItem('jarvis_active_chat_id');
      if (stored && typeof stored === 'string' && stored.trim()) {
        return stored.trim();
      }
    } catch { /* ignore */ }
    return 'default';
  }, [activeChatIdProp]);

  const [activeChatId, setActiveChatId] = useState(getActiveChatId);
  const activeChatIdRef = useRef(activeChatId);

  useEffect(() => {
    const current = getActiveChatId();
    setActiveChatId(current);
    activeChatIdRef.current = current;
  }, [getActiveChatId]);

  // Sync activeChatId with storage, chat deletion, or data reset events
  useEffect(() => {
    const handleStorageOrReset = (e) => {
      const deletedId = e?.detail?.deletedId;
      if (deletedId && activeChatIdRef.current === deletedId) {
        try {
          localStorage.removeItem('spidey_active_chat_id');
          localStorage.removeItem('jarvis_active_chat_id');
        } catch { /* ignore */ }
        setActiveChatId('default');
        activeChatIdRef.current = 'default';
        return;
      }
      const updated = getActiveChatId();
      setActiveChatId(updated);
      activeChatIdRef.current = updated;
    };

    window.addEventListener('storage', handleStorageOrReset);
    window.addEventListener('orbit:chat_deleted', handleStorageOrReset);
    window.addEventListener('orbit:data_reset', handleStorageOrReset);

    return () => {
      window.removeEventListener('storage', handleStorageOrReset);
      window.removeEventListener('orbit:chat_deleted', handleStorageOrReset);
      window.removeEventListener('orbit:data_reset', handleStorageOrReset);
    };
  }, [getActiveChatId]);

  // Switch chat over WebSocket and rehydrate history when activeChatId changes
  useEffect(() => {
    activeChatIdRef.current = activeChatId;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'set_chat', chat_id: activeChatId }));
    }
    fetch(`/api/history?session_id=${encodeURIComponent(activeChatId)}`, { headers: getAuthHeaders() })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.messages) setMessages(data.messages);
      })
      .catch((err) => console.warn('Failed to fetch history for chat:', err));
  }, [activeChatId]);

  // Sync Gemini API config changes from Settings over live WebSocket
  useEffect(() => {
    const handleGeminiConfigChanged = () => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        const { apiKey, model } = getGeminiConfig();
        wsRef.current.send(JSON.stringify({
          type: 'set_gemini_config',
          gemini_api_key: apiKey || null,
          gemini_model: model,
        }));
      }
    };
    window.addEventListener('spidey:gemini_config_changed', handleGeminiConfigChanged);
    return () => window.removeEventListener('spidey:gemini_config_changed', handleGeminiConfigChanged);
  }, []);

  const isSpeakEnabled = () => {
    try {
      return localStorage.getItem('spidey_speak_enabled') === '1';
    } catch {
      return false;
    }
  };

  const playAudio = useCallback((audioUrl) => {
    if (!audioUrl) return;
    if (!isSpeakEnabled()) return;

    // Discard any currently active speech globally
    window.dispatchEvent(new CustomEvent('spidey:audio_stop'));

    if (!audioRef.current) {
      audioRef.current = new Audio();
    }
    audioRef.current.pause();
    audioRef.current.currentTime = 0;
    audioRef.current.src = audioUrl;
    audioRef.current.play().catch((err) => {
      console.warn('Audio playback blocked or failed:', err);
    });
  }, []);

  // Listen for global stop requests
  useEffect(() => {
    const onStop = () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
      }
    };
    window.addEventListener('spidey:audio_stop', onStop);
    return () => window.removeEventListener('spidey:audio_stop', onStop);
  }, []);

  // Initial DB hydration via REST
  const fetchInitialData = useCallback(async () => {
    try {
      const currentCid = activeChatIdRef.current || 'default';
      const [remRes, histRes] = await Promise.all([
        fetch('/api/reminders', { headers: getAuthHeaders() }),
        fetch(`/api/history?session_id=${encodeURIComponent(currentCid)}`, { headers: getAuthHeaders() }),
      ]);
      if (remRes.ok) {
        const remData = await remRes.json();
        setReminders(remData.reminders || []);
      }
      if (histRes.ok) {
        const histData = await histRes.json();
        setMessages(histData.messages || []);
      }
    } catch (err) {
      console.error('Failed to fetch initial DB state:', err);
    }
  }, []);

  // WebSocket connection with auto-reconnect (leak-free)
  useEffect(() => {
    fetchInitialData();

    let reconnectTimer = null;
    let isTornDown = false;

    const connectWs = () => {
      if (isTornDown) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const tokenQuery = ORBIT_TOKEN ? `?token=${encodeURIComponent(ORBIT_TOKEN)}` : '';
      const wsUrl = `${protocol}//${window.location.host}/ws${tokenQuery}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      let pingTimer = null;
      ws.onopen = () => {
        if (isTornDown) {
          ws.close();
          return;
        }
        setConnected(true);
        // Send set_chat right after socket opens with current active chat id
        const currentCid = activeChatIdRef.current || 'default';
        ws.send(JSON.stringify({ type: 'set_chat', chat_id: currentCid }));

        // Sync saved Gemini API Studio config over WebSocket if present
        const { apiKey, model } = getGeminiConfig();
        if (apiKey) {
          ws.send(JSON.stringify({ type: 'set_gemini_config', gemini_api_key: apiKey, gemini_model: model }));
        }

        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        if (isTornDown) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'connected') {
            if (data.reminders) setReminders(data.reminders);
            if (data.history) setMessages(data.history);
          } else if (data.type === 'chat_set') {
            if (data.history) setMessages(data.history);
          } else if (data.type === 'status') {
            if (data.state === 'thinking') {
              setIsLoading(true);
              emitBrainState('thinking');
            }
          } else if (data.type === 'pong') {
            // Keep-alive pong
          } else if (data.type === 'transcript') {
            setMessages((prev) => [...prev, { role: 'user', content: data.text }]);
            emitBrainPulse(0.8);
          } else if (data.type === 'token') {
            if (data.text) {
              emitBrainState('streaming');
              emitBrainPulse(0.45);
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.role === 'assistant' && last.streaming) {
                  updated[updated.length - 1] = { ...last, content: last.content + data.text };
                } else {
                  updated.push({ role: 'assistant', content: data.text, streaming: true });
                }
                return updated;
              });
            }
          } else if (data.type === 'stream_reset') {
            setMessages((prev) => prev.filter((m, idx) => !(idx === prev.length - 1 && m.streaming)));
          } else if (data.type === 'stream_done') {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.streaming) {
                updated[updated.length - 1] = { ...last, streaming: false };
              }
              return updated;
            });
          } else if (data.type === 'reminder_alert') {
            const currentCid = activeChatIdRef.current || 'default';
            // Only append in-chat reminder text when alert chat_id matches active chat
            if (data.text && (!data.chat_id || data.chat_id === currentCid)) {
              setMessages((prev) => [...prev, { role: 'assistant', content: `⏰ Reminder: ${data.text}` }]);
            }
            if (data.reminders) setReminders(data.reminders);
            if (data.audio_url && isSpeakEnabled()) playAudio(data.audio_url);
            window.dispatchEvent(new CustomEvent('orbit:reminder_alert', { detail: data }));
          } else if (data.type === 'agent_response') {
            setIsLoading(false);
            emitBrainState('idle');
            if (data.history) {
              setMessages(data.history);
            } else if (data.text) {
              setMessages((prev) => [...prev, { role: 'assistant', content: data.text }]);
            }
            if (data.reminders) setReminders(data.reminders);
            if (data.audio_url && isSpeakEnabled()) playAudio(data.audio_url);
            if (Array.isArray(data.ui_actions)) {
              for (const action of data.ui_actions) {
                if (!action || !action.type) continue;
                if (action.type === 'refresh') {
                  window.dispatchEvent(new CustomEvent('orbit:refresh', { detail: { sections: action.sections || [] } }));
                } else if (action.type === 'navigate') {
                  const targetRoute = action.route || (action.page ? `/${action.page}` : null);
                  const allowed = ['/dashboard', '/habits', '/todos', '/reminders', '/learning', '/analytics', '/settings'];
                  if (targetRoute && allowed.includes(targetRoute)) {
                    window.dispatchEvent(new CustomEvent('orbit:navigate', { detail: { route: targetRoute, page: action.page } }));
                  }
                } else {
                  window.dispatchEvent(new CustomEvent('orbit:ui_action', { detail: action }));
                }
              }
            }
          } else if (data.type === 'error') {
            setIsLoading(false);
            emitBrainState('idle');
            console.error('Agent error:', data.error);
          }
        } catch (e) {
          console.error('Invalid WS JSON:', e);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (pingTimer) clearInterval(pingTimer);
        if (!isTornDown) {
          reconnectTimer = setTimeout(connectWs, 3000);
        }
      };
    };

    connectWs();
    return () => {
      isTornDown = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
      }
    };
  }, [fetchInitialData, playAudio]);

  // Send chat message (WS primary, REST fallback)
  const sendMessage = useCallback(async (text) => {
    if (!text.trim()) return;
    setIsLoading(true);
    setMessages((prev) => [...prev, { role: 'user', content: text }]);

    const currentCid = activeChatIdRef.current || 'default';
    const { apiKey, model } = getGeminiConfig();

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        message: text,
        chat_id: currentCid,
        ...(apiKey ? { gemini_api_key: apiKey, gemini_model: model } : {}),
      }));
      return;
    }

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ message: text, session_id: currentCid, chat_id: currentCid }),
      });
      const data = await res.json();
      if (data.history) setMessages(data.history);
      if (data.reminders) setReminders(data.reminders);
      if (data.audio_url) playAudio(data.audio_url);
    } catch (err) {
      console.error('Chat request failed:', err);
    } finally {
      setIsLoading(false);
    }
  }, [playAudio]);

  // Start/Stop Microphone PCM Capture via public/audio-worklet/pcm-capture.js
  const startVoiceCapture = useCallback(async () => {
    if (isRecording) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      audioCtxRef.current = audioCtx;

      await audioCtx.audioWorklet.addModule('/audio-worklet/pcm-capture.js');
      const source = audioCtx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(audioCtx, 'pcm-capture-processor');

      workletNode.port.onmessage = (event) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(event.data);
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
            emitBrainAudioLevel(Math.min(1, Math.sqrt(sumSq / Math.max(1, count)) * 4.5));
          }
        }
      };

      source.connect(workletNode);
      workletNode.connect(audioCtx.destination);
      setIsRecording(true);
      emitBrainState('listening');
    } catch (err) {
      console.error('Microphone capture error:', err);
    }
  }, [isRecording]);

  const stopVoiceCapture = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: 'end_audio' }));
      } catch { /* ignore */ }
    }
    setIsRecording(false);
    emitBrainAudioLevel(0);
    emitBrainState('idle');
  }, []);

  // Reminder CRUD helpers
  const addReminder = useCallback(async (title, remind_at) => {
    const currentCid = activeChatIdRef.current || 'default';
    const res = await fetch('/api/reminders', {
      method: 'POST',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ title, remind_at, chat_id: currentCid }),
    });
    if (res.ok) {
      const data = await res.json();
      setReminders(data.reminders || []);
    }
  }, []);

  const completeReminder = useCallback(async (id, completed = true, remind_at = undefined) => {
    const body = { completed: Boolean(completed) };
    if (remind_at) body.remind_at = remind_at;
    const res = await fetch(`/api/reminders/${id}`, {
      method: 'PATCH',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    if (res.ok) {
      const data = await res.json();
      setReminders(data.reminders || []);
      return { ok: true, data };
    } else {
      const errData = await res.json().catch(() => ({}));
      const msg = errData.detail || 'Failed to update reminder';
      console.warn('completeReminder failed:', msg);
      return { ok: false, error: msg };
    }
  }, []);

  const toggleReminder = completeReminder;

  const deleteReminder = useCallback(async (id) => {
    const res = await fetch(`/api/reminders/${id}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    if (res.ok) {
      const data = await res.json();
      setReminders(data.reminders || []);
    }
  }, []);

  return {
    messages,
    reminders,
    connected,
    isLoading,
    isRecording,
    sendMessage,
    startVoiceCapture,
    stopVoiceCapture,
    addReminder,
    completeReminder,
    toggleReminder,
    deleteReminder,
  };
}

export default useOrbitAgent;
