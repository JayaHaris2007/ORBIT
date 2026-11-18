import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { format } from 'date-fns';
import { Check, ChevronDown, ChevronLeft, ChevronUp, History, MessageSquarePlus, PanelRightClose, Send, Trash2, X } from 'lucide-react';
import { apiRequest, apiStreamRequest } from '../services/api';
import { useAppData } from '../context/AppDataContext';
import { useSpideyBrain } from '../context/SpideyBrainContext';
import { cleanAssistantText } from '../utils/textUtils';
import { useVoice } from '../hooks/useVoice';
import { useVoiceSession } from '../hooks/useVoiceSession';
import SpeakToggle from './voice/SpeakToggle';
import ListenButton from './voice/ListenButton';
import StopButton from './voice/StopButton';
import OrbitAgentView from './OrbitAgentView';
import NeuralBrainCanvas from './three/NeuralBrainCanvas';
import SpiderMark from './brand/SpiderMark';

const ACTIVE_CHAT_KEY = 'spidey_active_chat_id';
const MINIMIZED_KEY = 'spidey_panel_minimized';
// Older builds stored the panel state under the previous name.
const LEGACY_ACTIVE_CHAT_KEY = 'jarvis_active_chat_id';
const LEGACY_MINIMIZED_KEY = 'jarvis_panel_minimized';

const readStored = (key, legacyKey) => localStorage.getItem(key) ?? localStorage.getItem(legacyKey);

// One-tap openers for an empty conversation.
const STARTER_PROMPTS = [
    'What do you know about me?',
    "What's pending today?",
    'Check my habits'
];

const formatWhen = (value) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : format(date, 'MMM d, h:mm a');
};

const AssistantSidebar = () => {
    const { revision, refresh } = useAppData();
    const navigate = useNavigate();
    const location = useLocation();
    // The panel is docked on wide screens; the toggle only matters below xl.
    const [open, setOpen] = useState(false);
    const [online, setOnline] = useState(false);
    const [chats, setChats] = useState([]);
    const [historyOpen, setHistoryOpen] = useState(false);
    const [confirmingId, setConfirmingId] = useState('');
    const [minimized, setMinimized] = useState(() => readStored(MINIMIZED_KEY, LEGACY_MINIMIZED_KEY) === '1');
    const [chatId, setChatId] = useState('');
    const [messages, setMessages] = useState([]);
    const [prompt, setPrompt] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const lastNotificationId = useRef(0);
    const conversationEndRef = useRef(null);
    const activeChatRef = useRef('');
    const requestSeq = useRef(0);

    const voice = useVoice();
    const brain = useSpideyBrain();
    const [orbitMode, setOrbitMode] = useState(false);
    const [coreExpanded, setCoreExpanded] = useState(true);
    const submitPromptRef = useRef(null);

    // Map a page key from the backend to a real app route; unknown pages do nothing.
    const goToPage = useCallback((page) => {
        if (!page) return;
        if (page === 'chat') {
            setOpen(true);
            return;
        }
        const routes = {
            dashboard: '/dashboard',
            habits: '/habits',
            tasks: '/todos',
            todos: '/todos',
            reminders: '/reminders',
            memories: '/reminders',
            learning: '/learning',
            analytics: '/analytics',
            settings: '/settings',
        };
        const route = routes[page];
        if (route && location.pathname !== route) navigate(route);
    }, [navigate, location.pathname]);

    const applyUiActions = useCallback((actions, contextText = '') => {
        if (!Array.isArray(actions)) return;
        const refreshSections = [];
        for (const action of actions) {
            if (!action || !action.type) continue;
            if (action.type === 'refresh') {
                const secs = Array.isArray(action.sections) ? action.sections : [];
                refreshSections.push(...secs);
                window.dispatchEvent(new CustomEvent('orbit:refresh', { detail: { sections: secs } }));
            } else if (action.type === 'navigate') {
                const targetRoute = action.route || (action.page ? `/${action.page}` : null);
                const allowed = ['/dashboard', '/habits', '/todos', '/reminders', '/learning', '/analytics', '/settings'];
                if (targetRoute && allowed.includes(targetRoute) && location.pathname !== targetRoute) {
                    navigate(targetRoute);
                } else if (action.page) {
                    goToPage(action.page);
                }
            } else {
                window.dispatchEvent(new CustomEvent('orbit:ui_action', { detail: action }));
            }
        }
        if (refreshSections.length > 0) {
            window.dispatchEvent(new CustomEvent('spidey:crawler_action', {
                detail: {
                    sections: [...new Set(refreshSections)],
                    text: contextText,
                },
            }));
        }
    }, [goToPage, location.pathname, navigate]);

    const refreshChats = useCallback(async () => {
        try {
            const data = await apiRequest('/api/chats');
            setChats(data.chats || []);
        } catch {
            // The conversation still works; the list catches up on the next poll.
        }
    }, []);

    const handleSpeechTranscript = useCallback((text) => {
        if (!text || !text.trim()) return;
        setMessages((current) => [
            ...current,
            {
                id: `voice-user-${Date.now()}`,
                role: 'user',
                content: text.trim(),
            },
        ]);
    }, []);

    const handleSpeechReply = useCallback((replyText, data) => {
        if (data?.chat_id && activeChatRef.current && data.chat_id !== activeChatRef.current) {
            return;
        }
        if (Array.isArray(data?.messages)) {
            setMessages(data.messages);
        } else if (replyText) {
            setMessages((current) => [
                ...current,
                {
                    id: `voice-assistant-${Date.now()}`,
                    role: 'assistant',
                    content: replyText,
                },
            ]);
        }
        if (data?.navigate) goToPage(data.navigate);
        if (data?.ui_actions) applyUiActions(data.ui_actions, `${replyText || ''} ${data?.response || ''}`);
        refreshChats();
        refresh();
    }, [applyUiActions, goToPage, refresh, refreshChats]);

    const voiceSession = useVoiceSession({
        onTranscript: handleSpeechTranscript,
        onReply: handleSpeechReply,
        audioQueue: voice.audioQueue
    });

    useEffect(() => {
        if (chatId) {
            voiceSession.updateChatId(chatId);
        }
    }, [chatId, voiceSession]);

    const isVoiceActive = voice.isSpeaking || voiceSession.state !== 'idle';
    const handleVoiceStop = useCallback(() => {
        voice.stop();
        voiceSession.stopSession();
    }, [voice, voiceSession]);

    useEffect(() => {
        const handleOrbitNav = (e) => {
            const targetRoute = e.detail?.route;
            const allowed = ['/dashboard', '/habits', '/todos', '/reminders', '/learning', '/analytics', '/settings'];
            if (targetRoute && allowed.includes(targetRoute) && location.pathname !== targetRoute) {
                navigate(targetRoute);
            }
        };
        window.addEventListener('orbit:navigate', handleOrbitNav);
        return () => window.removeEventListener('orbit:navigate', handleOrbitNav);
    }, [navigate, location.pathname]);

    // Load one conversation and make it the active one.
    const openChat = useCallback(async (id) => {
        const seq = requestSeq.current + 1;
        requestSeq.current = seq;
        activeChatRef.current = id;
        localStorage.setItem(ACTIVE_CHAT_KEY, id);
        setChatId(id);
        setMessages([]);
        setError('');
        lastNotificationId.current = 0;
        try {
            const [history, notificationData] = await Promise.all([
                apiRequest(`/api/history/${id}`),
                apiRequest(`/api/notifications/${id}?after_id=0`)
            ]);
            if (requestSeq.current !== seq) return;
            setMessages(history.messages || []);
            const notifications = notificationData.notifications || [];
            lastNotificationId.current = notifications.length
                ? notifications[notifications.length - 1].id
                : 0;
        } catch (requestError) {
            if (requestSeq.current === seq) setError(requestError.message);
        }
    }, []);

    useEffect(() => {
        let cancelled = false;
        const loadWorkspace = async () => {
            try {
                const [health, chatData] = await Promise.all([
                    apiRequest('/api/health'),
                    apiRequest('/api/chats')
                ]);
                if (cancelled) return;
                setOnline(health.status === 'ok');

                const savedChatId = readStored(ACTIVE_CHAT_KEY, LEGACY_ACTIVE_CHAT_KEY);
                const savedChats = chatData.chats || [];
                const chat = savedChats.find((item) => item.id === savedChatId) || savedChats[0];
                if (!chat) {
                    const created = await apiRequest('/api/chats', { method: 'POST' });
                    if (cancelled) return;
                    setChats([created]);
                    openChat(created.id);
                    return;
                }
                setChats(savedChats);
                openChat(chat.id);
            } catch (requestError) {
                if (!cancelled) {
                    setOnline(false);
                    setError(requestError.message);
                }
            }
        };
        loadWorkspace();
        return () => { cancelled = true; };
    }, [openChat]);

    useEffect(() => {
        conversationEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, loading]);

    // The collapsed state lives on <html> so the page layout can drop the reserved width.
    useEffect(() => {
        document.documentElement.classList.toggle('spidey-minimized', minimized);
        localStorage.setItem(MINIMIZED_KEY, minimized ? '1' : '0');
    }, [minimized]);

    useEffect(() => {
        if (!chatId) return undefined;
        const interval = window.setInterval(async () => {
            try {
                const data = await apiRequest(`/api/notifications/${chatId}?after_id=${lastNotificationId.current}`);
                if (activeChatRef.current !== chatId) return;
                if (!data.notifications?.length) return;
                lastNotificationId.current = data.notifications[data.notifications.length - 1].id;
                setMessages((current) => [...current, ...data.notifications.map((item) => ({
                    role: 'assistant', content: item.content, notification: true
                }))]);
                const latestNotif = data.notifications[data.notifications.length - 1];
                if (latestNotif?.content && voice.speakEnabled && voiceSession.state === 'idle') {
                    voice.speak(latestNotif.content);
                }
                // A fired reminder may have changed reminders or tasks on the server.
                refresh();
            } catch {
                // Keep the shared panel quiet during a temporary polling failure.
            }
        }, 5000);
        return () => window.clearInterval(interval);
    }, [chatId, refresh, voice, voiceSession.state]);

    // Periodically trigger proactive coach check-ins for pending tasks, habits, and learning.
    useEffect(() => {
        if (!chatId) return undefined;
        const triggerCheckin = async () => {
            try {
                await apiRequest('/api/proactive/check-in', {
                    method: 'POST',
                    body: JSON.stringify({ chat_id: chatId, cooldown_minutes: 30 })
                });
            } catch {
                // Ignore background check-in errors
            }
        };
        const initialTimer = window.setTimeout(triggerCheckin, 90 * 1000);
        const periodicTimer = window.setInterval(triggerCheckin, 20 * 60 * 1000);
        return () => {
            window.clearTimeout(initialTimer);
            window.clearInterval(periodicTimer);
        };
    }, [chatId]);

    // Pick up chats created or renamed elsewhere (another tab, Discord bot, or database reset).
    useEffect(() => {
        const handleDataReset = async () => {
            try {
                const data = await apiRequest('/api/chats');
                const savedChats = data.chats || [];
                if (savedChats.length) {
                    setChats(savedChats);
                    await openChat(savedChats[0].id);
                } else {
                    const created = await apiRequest('/api/chats', { method: 'POST' });
                    setChats([created]);
                    await openChat(created.id);
                }
            } catch {
                setMessages([]);
            }
        };
        window.addEventListener('orbit:data_reset', handleDataReset);
        return () => window.removeEventListener('orbit:data_reset', handleDataReset);
    }, [openChat]);

    useEffect(() => {
        if (!revision) return;
        apiRequest('/api/chats')
            .then((data) => setChats(data.chats || []))
            .catch(() => { /* keep the current list */ });
    }, [revision]);

    const startChat = async () => {
        try {
            const chat = await apiRequest('/api/chats', { method: 'POST' });
            setChats((current) => [chat, ...current]);
            setHistoryOpen(false);
            setPrompt('');
            await openChat(chat.id);
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const selectChat = (id) => {
        setHistoryOpen(false);
        setConfirmingId('');
        if (id !== chatId) openChat(id);
    };

    const deleteChat = async (id) => {
        try {
            await apiRequest(`/api/chats/${id}`, { method: 'DELETE' });
            setConfirmingId('');
            window.dispatchEvent(new CustomEvent('orbit:chat_deleted', { detail: { deletedId: id } }));
            const remaining = chats.filter((chat) => chat.id !== id);
            setChats(remaining);
            if (id !== chatId) return;
            if (remaining.length) {
                await openChat(remaining[0].id);
                return;
            }
            const created = await apiRequest('/api/chats', { method: 'POST' });
            setChats([created]);
            await openChat(created.id);
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    // Shared by the composer and the starter prompts in the empty state.
    const submitPrompt = async (rawValue) => {
        const value = rawValue.trim();
        if (!value || loading || !chatId) return;
        // Show the message immediately instead of waiting for the reply.
        const optimisticId = `pending-${Date.now()}`;
        const streamingId = `streaming-${optimisticId}`;
        setMessages((current) => [...current, {
            id: optimisticId,
            role: 'user',
            content: value,
            pending: true
        }]);
        setLoading(true);
        brain?.setBrainState('thinking');
        setPrompt('');
        setError('');
        try {
            let finalData = null;
            await apiStreamRequest('/api/generate/stream', {
                method: 'POST',
                body: JSON.stringify({ prompt: value, chat_id: chatId })
            }, (evt) => {
                if (activeChatRef.current !== chatId || !evt || !evt.type) return;
                if (evt.type === 'token' && evt.text) {
                    brain?.setBrainState('streaming');
                    brain?.triggerPulse(0.45);
                    setMessages((current) => {
                        const idx = current.findIndex((m) => m.id === streamingId);
                        if (idx !== -1) {
                            const updated = [...current];
                            updated[idx] = { ...updated[idx], content: updated[idx].content + evt.text };
                            return updated;
                        }
                        return [...current, { id: streamingId, role: 'assistant', content: evt.text, streaming: true }];
                    });
                } else if (evt.type === 'stream_reset') {
                    setMessages((current) => current.filter((m) => m.id !== streamingId));
                } else if (evt.type === 'stream_done') {
                    setMessages((current) => current.map((m) => (
                        m.id === streamingId ? { ...m, streaming: false } : m
                    )));
                } else if (evt.type === 'done') {
                    finalData = evt;
                } else if (evt.type === 'error') {
                    throw new Error(evt.error || 'Streaming failed.');
                }
            });
            // Ignore a late reply if another conversation was opened meanwhile.
            if (activeChatRef.current !== chatId || !finalData) return;
            const data = finalData;
            setMessages(data.messages || []);
            if (data.navigate) goToPage(data.navigate);
            applyUiActions(data.ui_actions, `${value} ${data.response || ''}`);
            if ((data.spoken_response || data.response) && voice.speakEnabled && voiceSession.state === 'idle') {
                voice.speak(data.spoken_response || data.response);
            } else {
                brain?.setBrainState('idle');
            }
            refreshChats();
            // The assistant may have created or completed tasks, habits, reminders or memories.
            refresh();
        } catch (requestError) {
            brain?.setBrainState('idle');
            if (activeChatRef.current !== chatId) return;
            setError(requestError.message);
            setMessages((current) => current.map((item) => (
                item.id === optimisticId ? { ...item, pending: false, failed: true } : item
            )));
        } finally {
            setLoading(false);
        }
    };
    submitPromptRef.current = submitPrompt;

    useEffect(() => {
        const onExternalPrompt = (event) => {
            const incoming = event?.detail?.prompt;
            if (!incoming) return;
            setMinimized(false);
            setOpen(true);
            submitPromptRef.current?.(incoming);
        };
        const onToggleVoiceInChat = () => {
            if (!chatId || loading) return;
            setMinimized(false);
            setOpen(true);
            window.dispatchEvent(new CustomEvent('spidey:audio_stop'));
            if (voiceSession.state !== 'idle') {
                voiceSession.stopSession();
            } else {
                voiceSession.startSession('live', chatId);
            }
        };
        window.addEventListener('spidey:prompt', onExternalPrompt);
        window.addEventListener('spidey:open_live', onToggleVoiceInChat);
        window.addEventListener('spidey:open_listen', onToggleVoiceInChat);
        return () => {
            window.removeEventListener('spidey:prompt', onExternalPrompt);
            window.removeEventListener('spidey:open_live', onToggleVoiceInChat);
            window.removeEventListener('spidey:open_listen', onToggleVoiceInChat);
        };
    }, [chatId, loading, voiceSession]);

    const sendMessage = (event) => {
        event.preventDefault();
        submitPrompt(prompt);
    };

    // Enter sends, Shift+Enter writes a new line.
    const handleKeyDown = (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
        }
    };

    return (
        <>
            <button
                type="button"
                onClick={() => {
                    // Below xl the panel is an overlay, so the tab only opens/closes it.
                    if (minimized && window.matchMedia('(min-width: 1280px)').matches) {
                        setMinimized(false);
                        return;
                    }
                    setOpen((current) => !current);
                }}
                className={`workspace-toggle group fixed right-0 top-1/2 -translate-y-1/2 z-40 flex-col items-center gap-0 border-t border-l border-b border-[#F2EFE9]/25 border-r-0 bg-[#111111] py-4 px-[10px] xl:hidden cursor-pointer transition-all duration-200 hover:border-[#D95D24] ${open ? 'hidden' : 'flex'}`}
                aria-expanded={open}
                aria-label={minimized ? 'Restore S.P.I.D.E.Y panel' : open ? 'Close S.P.I.D.E.Y panel' : 'Open S.P.I.D.E.Y panel'}
                title={minimized ? 'Restore S.P.I.D.E.Y' : 'Open S.P.I.D.E.Y'}
            >
                <ChevronLeft size={13} className="text-[#9C968E] mb-2 transition-transform duration-200 group-hover:text-[#D95D24] group-hover:-translate-x-0.5" />
                <div className="mb-3">
                    <SpiderMark size={20} state={brain?.brainState || 'idle'} animateEntrance={false} />
                </div>
                <div className="flex flex-col items-center select-none">
                    {['S','P','I','D','E','Y'].map((letter, i) => (
                        <div key={letter} className="flex flex-col items-center">
                            <span className="font-mono font-bold text-[12px] leading-none text-[#F2EFE9] group-hover:text-[#D95D24] transition-colors">
                                {letter}
                            </span>
                            {i < 5 && (
                                <span className="block w-[1px] h-[5px] my-[3px] bg-[#F2EFE9]/20" />
                            )}
                        </div>
                    ))}
                </div>
                <span className="mt-3 h-2 w-2 bg-[#D95D24]" />
            </button>
            {open && <button type="button" className="workspace-backdrop fixed inset-0 z-40 bg-black/70 xl:hidden" aria-label="Close S.P.I.D.E.Y panel" onClick={() => setOpen(false)} />}

            <aside className={`workspace-sidebar fixed right-0 top-0 z-50 flex h-[calc(100dvh-4rem)] w-full max-w-[390px] flex-col overflow-hidden border-l border-[#F2EFE9]/15 bg-[#111111] transition-transform duration-200 md:h-screen ${open ? 'workspace-sidebar-open' : ''}`}>
                <header className="flex shrink-0 items-center gap-2.5 border-b border-[#F2EFE9]/15 bg-[#141414] px-4 py-3.5">
                    <div className="grid h-9 w-9 shrink-0 place-items-center border border-[#F2EFE9]/20 bg-[#111111]">
                        <SpiderMark size={28} state={brain?.brainState || 'idle'} animateEntrance={false} />
                    </div>
                    <div className="min-w-0 flex-1">
                        <h2 className="truncate text-xs font-bold uppercase tracking-[0.2em] text-[#F2EFE9]">S.P.I.D.E.Y</h2>
                        <p className="mt-0.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9C968E]">
                            <span className={`h-1.5 w-1.5 ${online ? 'bg-[#D95D24]' : 'bg-[#9C968E]/40'}`} />
                            {online ? (brain?.brainState && brain.brainState !== 'idle' ? brain.brainState : 'Standby') : 'Connecting'}
                        </p>
                    </div>
                    <button type="button" onClick={() => setCoreExpanded((v) => !v)} className="grid h-8 w-8 shrink-0 place-items-center border border-[#F2EFE9]/15 bg-[#151515] !p-0 text-[#9C968E] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9]" title={coreExpanded ? 'Collapse 3D Neural Core' : 'Expand 3D Neural Core'} aria-label="Toggle 3D Neural Core">{coreExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</button>
                    <button type="button" onClick={() => setHistoryOpen((current) => !current)} className={`grid h-8 w-8 shrink-0 place-items-center border !p-0 transition-colors ${historyOpen ? 'border-[#D95D24] bg-[#D95D24] text-[#111111]' : 'border-[#F2EFE9]/15 bg-[#151515] text-[#9C968E] hover:border-[#D95D24] hover:text-[#F2EFE9]'}`} title="Chat history" aria-label="Toggle chat history" aria-expanded={historyOpen}><History size={14} /></button>
                    <button type="button" onClick={startChat} className="grid h-8 w-8 shrink-0 place-items-center border border-[#F2EFE9]/15 bg-[#151515] !p-0 text-[#9C968E] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9]" title="Start a new chat" aria-label="Start a new chat"><MessageSquarePlus size={14} /></button>
                    <button type="button" onClick={() => setMinimized(true)} className="hidden h-8 w-8 shrink-0 place-items-center border border-[#F2EFE9]/15 bg-[#151515] !p-0 text-[#9C968E] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9] xl:grid" title="Minimize panel" aria-label="Minimize S.P.I.D.E.Y panel"><PanelRightClose size={14} /></button>
                    <button type="button" onClick={() => setOpen(false)} className="workspace-close grid h-8 w-8 shrink-0 place-items-center border border-[#F2EFE9]/15 bg-[#151515] !p-0 text-[#9C968E] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9] xl:hidden" aria-label="Close S.P.I.D.E.Y panel"><X size={14} /></button>
                </header>

                {coreExpanded && (
                    <div className="shrink-0 border-b border-[#F2EFE9]/15 bg-[#131313] px-4 py-2">
                        <div className="flex items-center gap-3">
                            <div className="h-[78px] w-[78px] shrink-0 border border-[#F2EFE9]/10 bg-[#111111]">
                                <NeuralBrainCanvas
                                    size="compact"
                                    className="h-full w-full"
                                    onClick={() => brain?.triggerPulse?.(1.25)}
                                />
                            </div>
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-1.5">
                                    <span className="h-1.5 w-1.5 bg-[#D95D24]" />
                                    <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#D95D24]">
                                        Neural Core
                                    </span>
                                </div>
                                <p className="mt-1 truncate text-xs font-medium text-[#F2EFE9]">
                                    {brain?.brainState === 'listening'
                                        ? 'Listening to voice...'
                                        : brain?.brainState === 'thinking' || brain?.brainState === 'transcribing'
                                        ? 'Processing tools & context...'
                                        : brain?.brainState === 'streaming'
                                        ? 'Streaming response...'
                                        : brain?.brainState === 'speaking'
                                        ? 'Speaking response...'
                                        : 'Synchronized & standing by'}
                                </p>
                                <p className="mt-0.5 font-mono text-[10px] text-[#9C968E]">
                                    Click sphere to pulse
                                </p>
                            </div>
                        </div>
                    </div>
                )}

                <div className="flex shrink-0 items-center justify-between border-b border-[#F2EFE9]/10 px-4 py-2.5">
                    <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#9C968E]">Dialogue</span>
                    <div className="flex items-center gap-1.5">
                        <SpeakToggle
                            speakEnabled={voice.speakEnabled}
                            engineReady={voice.engineReady}
                            onToggle={voice.toggleSpeak}
                            error={voice.error}
                        />
                        <button
                            type="button"
                            onClick={() => {
                                window.dispatchEvent(new CustomEvent('spidey:audio_stop'));
                                setOrbitMode(!orbitMode);
                            }}
                            className={`flex items-center gap-1 border px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.1em] transition-colors ${
                                orbitMode
                                    ? 'border-[#D95D24] bg-[#D95D24] text-[#111111]'
                                    : 'border-[#F2EFE9]/15 bg-[#151515] text-[#9C968E] hover:border-[#D95D24] hover:text-[#F2EFE9]'
                            }`}
                            title="Toggle ORBIT007 Agent Mode (WebSocket, AudioWorklet & DB Sync)"
                        >
                            <span>ORBIT007</span>
                        </button>
                    </div>
                </div>

                {historyOpen && (
                    <div className="shrink-0 border-b border-[#F2EFE9]/15 bg-[#141414] p-3">
                        <div className="max-h-60 space-y-1 overflow-y-auto">
                            {chats.map((chat) => {
                                const active = chat.id === chatId;
                                const confirming = confirmingId === chat.id;
                                return (
                                    <div key={chat.id} className={`group flex items-center gap-1 border transition-colors ${active ? 'border-[#D95D24]/60 bg-[#1B1612]' : 'border-transparent hover:border-[#F2EFE9]/15'}`}>
                                        <button
                                            type="button"
                                            onClick={() => selectChat(chat.id)}
                                            className={`min-w-0 flex-1 !border-0 !bg-transparent px-2.5 py-2 text-left ${active ? 'text-[#F2EFE9]' : 'text-[#9C968E] hover:text-[#F2EFE9]'}`}
                                        >
                                            <span className="flex items-center gap-1.5">
                                                <span className="block truncate text-xs font-medium">{chat.title || 'New conversation'}</span>
                                                {active && <span className="h-1.5 w-1.5 shrink-0 bg-[#D95D24]" aria-label="Active conversation" />}
                                            </span>
                                            <span className="mt-0.5 block font-mono text-[10px] text-[#9C968E]/70">{formatWhen(chat.updated_at)}</span>
                                        </button>
                                        {confirming ? (
                                            <div className="flex shrink-0 items-center gap-1 pr-1">
                                                <button type="button" onClick={() => deleteChat(chat.id)} className="grid h-7 w-7 place-items-center border border-[#D95D24] bg-[#D95D24] !p-0 text-[#111111]" title="Delete this chat" aria-label="Confirm delete chat"><Check size={13} /></button>
                                                <button type="button" onClick={() => setConfirmingId('')} className="grid h-7 w-7 place-items-center border border-[#F2EFE9]/20 bg-[#111111] !p-0 text-[#9C968E] hover:text-[#F2EFE9]" title="Cancel" aria-label="Cancel delete"><X size={13} /></button>
                                            </div>
                                        ) : (
                                            <button type="button" onClick={() => setConfirmingId(chat.id)} className="mr-1 grid h-7 w-7 shrink-0 place-items-center !border-0 !bg-transparent !p-0 text-[#9C968E] transition-opacity hover:text-[#D95D24] focus-visible:opacity-100 xl:opacity-0 xl:group-hover:opacity-100" title="Delete chat" aria-label={`Delete ${chat.title || 'conversation'}`}><Trash2 size={13} /></button>
                                        )}
                                    </div>
                                );
                            })}
                            {!chats.length && <p className="px-2 py-3 text-center font-mono text-[11px] text-[#9C968E]">No conversations yet.</p>}
                        </div>
                    </div>
                )}

                {orbitMode ? (
                    <div className="flex-1 min-h-0 flex flex-col">
                        <OrbitAgentView activeChatId={chatId} />
                    </div>
                ) : (
                    <>
                    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
                    {!messages.length && !loading && (
                        <div className="flex h-full flex-col items-center justify-center gap-3 px-4 text-center">
                            <SpiderMark size={52} state={brain?.brainState || 'idle'} />
                            <p className="font-mono text-xs font-bold uppercase tracking-[0.18em] text-[#F2EFE9]">
                                S.P.I.D.E.Y Standing By
                            </p>
                            <p className="max-w-[260px] text-xs leading-relaxed text-[#9C968E]">
                                Ask about your tasks, habits, learning roadmaps — or what I remember.
                            </p>
                            <div className="mt-1 flex flex-wrap justify-center gap-1.5">
                                {STARTER_PROMPTS.map((starter) => (
                                    <button
                                        key={starter}
                                        type="button"
                                        onClick={() => submitPrompt(starter)}
                                        disabled={loading || !chatId}
                                        className="border border-[#F2EFE9]/15 bg-[#151515] px-2.5 py-1.5 font-mono text-[10px] text-[#F2EFE9] transition-colors hover:border-[#D95D24] hover:text-[#D95D24] disabled:opacity-40"
                                    >
                                        {starter}
                                    </button>
                                ))}
                            </div>
                            {chats.length > 1 && (
                                <button type="button" onClick={() => setHistoryOpen(true)} className="mt-1 flex items-center gap-1.5 border border-[#F2EFE9]/15 bg-[#151515] px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-[#9C968E] hover:border-[#D95D24] hover:text-[#F2EFE9]">
                                    <History size={12} /> Open a previous chat
                                </button>
                            )}
                        </div>
                    )}

                    {messages.slice(-30).map((item, index) => {
                        const isUser = item.role === 'user';
                        const surface = item.failed
                            ? 'border border-[#D95D24] bg-[#221410] text-[#F2EFE9]'
                            : isUser
                                ? 'border border-[#D95D24]/60 bg-[#1B1511] text-[#F2EFE9]'
                                : 'border border-[#F2EFE9]/12 bg-[#161616] text-[#F2EFE9]';
                        return (
                            <div
                                key={`${item.role}-${item.id || index}`}
                                className={`w-fit max-w-[88%] px-3.5 py-2.5 text-xs leading-relaxed ${isUser ? 'ml-auto' : 'mr-auto'} ${surface} ${item.pending ? 'opacity-70' : ''}`}
                            >
                                {item.role === 'assistant'
                                    ? (
                                        <div className="assistant-message">
                                            <ReactMarkdown>{cleanAssistantText(item.content)}</ReactMarkdown>
                                            {item.streaming && <span className="ml-0.5 inline-block h-3 w-1.5 bg-[#D95D24] align-middle animate-pulse" />}
                                        </div>
                                    )
                                    : item.content}
                                {item.failed && <p className="mt-1 font-mono text-[10px] text-[#D95D24]">Not sent — try again</p>}
                            </div>
                        );
                    })}

                    {loading && !messages.some((m) => m.streaming) && (
                        <div className="mr-auto flex w-fit items-center gap-2 border border-[#F2EFE9]/12 bg-[#161616] px-3.5 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[#D95D24]">
                            <span className="h-1.5 w-1.5 bg-[#D95D24] animate-pulse" />
                            <span>Processing</span>
                        </div>
                    )}

                    <div ref={conversationEndRef} />
                </div>

                <form onSubmit={sendMessage} className="shrink-0 border-t border-[#F2EFE9]/15 bg-[#141414] px-4 py-3">
                    <div className="flex items-end gap-2 border border-[#F2EFE9]/15 bg-[#111111] p-2 transition-colors focus-within:border-[#D95D24]">
                        <textarea
                            value={prompt}
                            onChange={(event) => setPrompt(event.target.value)}
                            onKeyDown={handleKeyDown}
                            rows={1}
                            maxLength={2000}
                            placeholder="Ask S.P.I.D.E.Y…"
                            className="max-h-28 min-h-[36px] flex-1 resize-none bg-transparent px-2 py-2 text-xs leading-relaxed text-[#F2EFE9] outline-none placeholder:text-[#9C968E]/60"
                            disabled={!chatId}
                        />
                        <StopButton
                            state={isVoiceActive ? 'speaking' : 'idle'}
                            onStop={handleVoiceStop}
                        />
                        <ListenButton
                            state={voiceSession.state}
                            cloudStt={voice.cloudStt}
                            onClick={() => {
                                window.dispatchEvent(new CustomEvent('spidey:audio_stop'));
                                if (voiceSession.state !== 'idle') {
                                    voiceSession.stopSession();
                                } else {
                                    voiceSession.startSession('live', chatId);
                                }
                            }}
                            disabled={!chatId || loading}
                        />
                        <button
                            type="submit"
                            disabled={loading || !prompt.trim() || !chatId}
                            className="grid h-9 w-9 shrink-0 place-items-center border border-[#D95D24] bg-[#D95D24] text-[#111111] hover:bg-[#C44E19] disabled:opacity-40"
                            aria-label="Send message"
                        >
                            <Send size={15} />
                        </button>
                    </div>
                    {voiceSession.state !== 'idle' && (
                        <div className="mt-1.5 flex items-center justify-between px-1 font-mono text-[10px] uppercase tracking-[0.14em] text-[#D95D24]">
                            <span>
                                {voiceSession.state === 'listening'
                                    ? 'Voice active in current chat · Listening...'
                                    : voiceSession.state === 'transcribing'
                                    ? 'Transcribing speech...'
                                    : voiceSession.state === 'thinking'
                                    ? 'Generating reply...'
                                    : 'Speaking reply...'}
                            </span>
                            <button
                                type="button"
                                onClick={handleVoiceStop}
                                className="!border-0 !bg-transparent !p-0 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9C968E] hover:text-[#F2EFE9]"
                            >
                                End Voice
                            </button>
                        </div>
                    )}
                    <p className="mt-2 px-1 text-[10px] text-neutral-600">Enter to send · Shift + Enter for a new line</p>
                    { (error || voiceSession.error) && <p className="mt-2 px-1 text-xs text-[#D95D24]">{error || voiceSession.error}</p> }
                </form>
                </>
                )}
            </aside>
        </>
    );
};

export default AssistantSidebar;
