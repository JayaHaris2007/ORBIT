import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { apiRequest, apiStreamRequest } from '../services/api';
import { useAppData } from '../context/AppDataContext';
import { useAuth, useTheme } from '../context/AuthContext';
import { useSpideyBrain } from '../context/SpideyBrainContext';
import { cleanAssistantText } from '../utils/textUtils';
import { useVoice } from '../hooks/useVoice';
import { useVoiceSession } from '../hooks/useVoiceSession';
import SpideyAsciiCanvas from '../components/ascii/SpideyAsciiCanvas';
import SectionCanvasCard from '../components/workspace/SectionCanvasCard';
import TopNavbar from '../components/workspace/TopNavbar';
import ChatHistoryDrawer from '../components/workspace/ChatHistoryDrawer';
import ConversationStream from '../components/workspace/ConversationStream';
import ComposerBar from '../components/workspace/ComposerBar';

const LiveOverlay = lazy(() => import('../components/voice/LiveOverlay'));

const ACTIVE_CHAT_KEY = 'spidey_active_chat_id';
const LEGACY_ACTIVE_CHAT_KEY = 'jarvis_active_chat_id';

const SLASH_COMMANDS = [
    { cmd: '/tasks', desc: 'Open Tasks', section: 'tasks' },
    { cmd: '/habits', desc: 'Open Habits', section: 'habits' },
    { cmd: '/learning', desc: 'Open Learning', section: 'learning' },
    { cmd: '/reminders', desc: 'Open Reminders & Memory', section: 'reminders' },
    { cmd: '/analytics', desc: 'Open Analytics', section: 'analytics' },
    { cmd: '/settings', desc: 'Open Settings', section: 'settings' },
    { cmd: '/live', desc: 'Toggle Live Voice Mode (Ctrl+Space)', action: 'live' },
    { cmd: '/new', desc: 'Start a fresh conversation', action: 'new_chat' },
    { cmd: '/chat', desc: 'Close pop-up & return to chat', section: null },
];

const ROUTE_TO_SECTION = {
    '/': null,
    '/dashboard': null,
    '/chat': null,
    '/tasks': 'tasks',
    '/todos': 'tasks',
    '/habits': 'habits',
    '/reminders': 'reminders',
    '/memories': 'reminders',
    '/notes': 'reminders',
    '/learning': 'learning',
    '/analytics': 'analytics',
    '/settings': 'settings',
};

const SECTION_TO_ROUTE = {
    tasks: '/todos',
    habits: '/habits',
    reminders: '/reminders',
    learning: '/learning',
    analytics: '/analytics',
    settings: '/settings',
};

function normalizeSectionKey(raw) {
    if (!raw) return null;
    const key = String(raw).toLowerCase().replace(/^\//, '').trim();
    if (key === 'tasks' || key === 'todos' || key === 'todo') return 'tasks';
    if (key === 'habits' || key === 'habit') return 'habits';
    if (key === 'reminders' || key === 'reminder' || key === 'memories' || key === 'memory' || key === 'notes') return 'reminders';
    if (key === 'learning' || key === 'roadmaps' || key === 'study') return 'learning';
    if (key === 'analytics' || key === 'stats' || key === 'telemetry') return 'analytics';
    if (key === 'settings' || key === 'config') return 'settings';
    if (key === 'chat' || key === 'dashboard') return null;
    return undefined;
}

function detectTopicSection(text) {
    const t = String(text || '').toLowerCase().trim();
    if (!t) return undefined;

    if (/\b(?:back\s+to\s+chat|go\s+to\s+chat|open\s+chat|show\s+chat|chat\s+only|close\s+(?:this|card|panel|section|popup|pop-up))\b/.test(t)) {
        return null;
    }
    if (/\b(?:analytics?|telemetry|heatmap|weekly\s+stats?|productivity\s+score|momentum)\b/.test(t)) {
        return 'analytics';
    }
    if (/\b(?:learn\w*|roadmaps?|stud(?:y|ying)|topics?|lessons?|modules?)\b/.test(t)) {
        return 'learning';
    }
    if (/\b(?:habits?|streaks?|daily\s+routine)\b/.test(t)) {
        return 'habits';
    }
    if (/\b(?:reminders?|remind\s+me|memor(?:y|ies)|remember\s+that|notes?|what\s+do\s+you\s+(?:know|remember)\s+about\s+me)\b/.test(t)) {
        return 'reminders';
    }
    if (/\b(?:settings?|preferences?|change\s+theme|api\s+key|gemini\s+key)\b/.test(t)) {
        return 'settings';
    }
    if (/\b(?:tasks?|to-?dos?|to\s+dos?|what'?s\s+pending\s+today)\b/.test(t)) {
        return 'tasks';
    }
    return undefined;
}

function isExplicitOpenIntent(text) {
    const t = String(text || '').toLowerCase().trim();
    return /^(?:open|go\s+to|switch\s+to|navigate\s+to|take\s+me\s+to|bring\s+up|close)\b/.test(t)
        || /^show(?:\s+me)?\s+(?:my\s+|the\s+)?(?:settings?|analytics?|stats?|telemetry)\b/.test(t);
}

const isTypingElement = (el) => {
    if (!el) return false;
    const tag = el.tagName;
    return (
        tag === 'INPUT'
        || tag === 'TEXTAREA'
        || tag === 'SELECT'
        || el.isContentEditable
        || Boolean(el.closest?.('[contenteditable="true"]'))
    );
};

export default function SpideyWorkspace() {
    const { currentUser } = useAuth();
    const { theme } = useTheme();
    const { revision, refresh } = useAppData();
    const brain = useSpideyBrain();
    const location = useLocation();
    const navigate = useNavigate();

    const [drawerOpen, setDrawerOpen] = useState(false);
    const [chatSearch, setChatSearch] = useState('');

    const activeSection = ROUTE_TO_SECTION[location.pathname] ?? null;

    const [online, setOnline] = useState(false);
    const [chats, setChats] = useState([]);
    const [confirmingId, setConfirmingId] = useState('');
    const [chatId, setChatId] = useState('');
    const [messages, setMessages] = useState([]);
    const [prompt, setPrompt] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [sectionReplyToast, setSectionReplyToast] = useState(null);
    const [liveOpen, setLiveOpen] = useState(false);
    const [liveTurns, setLiveTurns] = useState([]);

    const lastNotificationId = useRef(0);
    const conversationEndRef = useRef(null);
    const activeChatRef = useRef('');
    const requestSeq = useRef(0);
    const submitPromptRef = useRef(null);
    const toastTimerRef = useRef(null);

    const voice = useVoice();

    const openSection = useCallback((sectionKey) => {
        const normalized = sectionKey ? normalizeSectionKey(sectionKey) : null;
        if (normalized === undefined) return;
        const targetRoute = normalized ? SECTION_TO_ROUTE[normalized] : '/';
        if (targetRoute && window.location.pathname !== targetRoute) {
            navigate(targetRoute, { replace: false });
        }
    }, [navigate]);

    const showSectionToast = useCallback((text) => {
        if (!text) return;
        clearTimeout(toastTimerRef.current);
        setSectionReplyToast(cleanAssistantText(text));
        toastTimerRef.current = setTimeout(() => {
            setSectionReplyToast(null);
        }, 7500);
    }, []);

    const refreshChats = useCallback(async () => {
        try {
            const data = await apiRequest('/api/chats');
            setChats(data.chats || []);
        } catch { /* ignore */ }
    }, []);

    const applyUiActions = useCallback((actions, userPrompt = '', navigateHint = null, provider = '') => {
        let navigatedSection = undefined;
        const touchedSections = [];
        const touchedSet = new Set();

        if (Array.isArray(actions)) {
            for (const action of actions) {
                if (!action || !action.type) continue;
                if (action.type === 'refresh') {
                    const secs = Array.isArray(action.sections) ? action.sections : [];
                    secs.forEach((s) => {
                        const norm = normalizeSectionKey(s);
                        if (norm && !touchedSet.has(norm)) {
                            touchedSet.add(norm);
                            touchedSections.push(norm);
                        }
                    });
                    window.dispatchEvent(new CustomEvent('orbit:refresh', { detail: { sections: secs } }));
                } else if (action.type === 'navigate') {
                    const target = normalizeSectionKey(action.page || action.route);
                    if (target !== undefined) {
                        navigatedSection = target;
                        if (target && !touchedSet.has(target)) {
                            touchedSet.add(target);
                            touchedSections.push(target);
                        }
                    }
                } else {
                    window.dispatchEvent(new CustomEvent('orbit:ui_action', { detail: action }));
                }
            }
        }

        const explicitNav = provider === 'local-navigate' || isExplicitOpenIntent(userPrompt);
        let targetSection = undefined;
        if (explicitNav) {
            targetSection = navigatedSection;
            if (targetSection === undefined && navigateHint) {
                const normHint = normalizeSectionKey(navigateHint);
                if (normHint !== undefined) targetSection = normHint;
            }
            if (targetSection === undefined) {
                targetSection = detectTopicSection(userPrompt);
            }
            if (targetSection !== undefined) {
                openSection(targetSection);
            }
        }

        return { touchedSections, targetSection };
    }, [openSection]);

    const handleSpeechTranscript = useCallback((text) => {
        if (!text || !text.trim()) return;
        const trimmed = text.trim();
        const turnId = `voice-user-${Date.now()}`;
        setMessages((current) => [
            ...current,
            { id: turnId, role: 'user', content: trimmed },
        ]);
        setLiveTurns((current) => [...current.slice(-19), { id: turnId, role: 'user', content: trimmed }]);
    }, []);

    const handleSpeechReply = useCallback((replyText, data) => {
        if (data?.chat_id && activeChatRef.current && data.chat_id !== activeChatRef.current) return;
        if (Array.isArray(data?.messages)) {
            setMessages(data.messages);
        } else if (replyText) {
            setMessages((current) => [
                ...current,
                { id: `voice-assistant-${Date.now()}`, role: 'assistant', content: replyText },
            ]);
        }
        if (replyText) {
            setLiveTurns((current) => [
                ...current.slice(-19),
                { id: `voice-assistant-${Date.now()}`, role: 'assistant', content: replyText },
            ]);
        }
        const { targetSection } = applyUiActions(
            data?.ui_actions,
            data?.transcript || '',
            data?.navigate || null,
            data?.provider || ''
        );
        if (replyText && (targetSection !== undefined ? targetSection !== null : activeSection !== null)) {
            showSectionToast(replyText);
        }
        refreshChats();
        refresh();
    }, [activeSection, applyUiActions, refresh, refreshChats, showSectionToast]);

    const voiceSession = useVoiceSession({
        onTranscript: handleSpeechTranscript,
        onReply: handleSpeechReply,
        audioQueue: voice.audioQueue,
    });

    useEffect(() => {
        if (chatId) voiceSession.updateChatId(chatId);
    }, [chatId, voiceSession]);

    const startLiveMode = useCallback(() => {
        if (!chatId || loading) return;
        window.dispatchEvent(new CustomEvent('spidey:audio_stop'));
        setDrawerOpen(false);
        openSection(null);
        setLiveTurns([]);
        setLiveOpen(true);
        brain?.triggerPulse?.(1.1);
        voiceSession.startSession('live', chatId);
    }, [brain, chatId, loading, openSection, voiceSession]);

    const stopLiveMode = useCallback(() => {
        setLiveOpen(false);
        voice.stop();
        voiceSession.stopSession();
    }, [voice, voiceSession]);

    const toggleLiveMode = useCallback(() => {
        if (liveOpen || voiceSession.state !== 'idle') {
            stopLiveMode();
        } else {
            startLiveMode();
        }
    }, [liveOpen, startLiveMode, stopLiveMode, voiceSession.state]);

    const isVoiceActive = voice.isSpeaking || voiceSession.state !== 'idle';
    const handleVoiceStop = useCallback(() => {
        setLiveOpen(false);
        voice.stop();
        voiceSession.stopSession();
    }, [voice, voiceSession]);

    useEffect(() => {
        const onKeyDown = (e) => {
            if (
                e.code === 'Space'
                && e.ctrlKey
                && !e.repeat
                && !e.metaKey
                && !e.altKey
                && chatId
                && !loading
            ) {
                e.preventDefault();
                toggleLiveMode();
                return;
            }
            if (e.key === 'Escape' && !isTypingElement(document.activeElement)) {
                const nestedDialogs = document.querySelectorAll('[role="dialog"]');
                if (nestedDialogs.length > 0) return;
                if (liveOpen) {
                    stopLiveMode();
                    return;
                }
                if (activeSection) {
                    openSection(null);
                    return;
                }
                if (drawerOpen) {
                    setDrawerOpen(false);
                }
            }
        };

        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [activeSection, chatId, drawerOpen, liveOpen, loading, openSection, stopLiveMode, toggleLiveMode]);

    useEffect(() => {
        const handleOrbitNav = (e) => {
            const target = normalizeSectionKey(e.detail?.route || e.detail?.page);
            if (target !== undefined) openSection(target);
        };
        window.addEventListener('orbit:navigate', handleOrbitNav);
        return () => window.removeEventListener('orbit:navigate', handleOrbitNav);
    }, [openSection]);

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
                apiRequest(`/api/notifications/${id}?after_id=0`),
            ]);
            if (requestSeq.current !== seq) return;
            const histMessages = history.messages || [];
            const notifications = notificationData.notifications || [];
            lastNotificationId.current = notifications.length
                ? notifications[notifications.length - 1].id
                : 0;
            const merged = [
                ...histMessages,
                ...notifications.map((item) => ({
                    id: `notif-${item.id}`,
                    role: 'assistant',
                    content: item.content,
                    created_at: item.created_at,
                    notification: true,
                })),
            ].sort((a, b) => {
                const ta = a.created_at ? Date.parse(a.created_at) : 0;
                const tb = b.created_at ? Date.parse(b.created_at) : 0;
                return ta - tb;
            });
            setMessages(merged);
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
                    apiRequest('/api/chats'),
                ]);
                if (cancelled) return;
                setOnline(health.status === 'ok');

                const savedChatId = localStorage.getItem(ACTIVE_CHAT_KEY) ?? localStorage.getItem(LEGACY_ACTIVE_CHAT_KEY);
                const savedChats = chatData.chats || [];
                const chat = savedChats.find((item) => item.id === savedChatId) || savedChats[0];
                if (!chat) {
                    const created = await apiRequest('/api/chats', { method: 'POST' });
                    if (cancelled) return;
                    setChats([created]);
                    await openChat(created.id);
                    return;
                }
                setChats(savedChats);
                await openChat(chat.id);
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

    useEffect(() => {
        if (!chatId) return undefined;
        const interval = window.setInterval(async () => {
            try {
                const data = await apiRequest(`/api/notifications/${chatId}?after_id=${lastNotificationId.current}`);
                if (activeChatRef.current !== chatId) return;
                if (!data.notifications?.length) return;
                lastNotificationId.current = data.notifications[data.notifications.length - 1].id;
                setMessages((current) => [
                    ...current,
                    ...data.notifications.map((item) => ({
                        id: `notif-${item.id}`,
                        role: 'assistant',
                        content: item.content,
                        notification: true,
                    })),
                ]);
                const latestNotif = data.notifications[data.notifications.length - 1];
                if (latestNotif?.content) {
                    showSectionToast(latestNotif.content);
                    if (voice.speakEnabled && voiceSession.state === 'idle') {
                        voice.speak(latestNotif.content);
                    }
                }
                refresh();
            } catch { /* ignore */ }
        }, 5000);
        return () => window.clearInterval(interval);
    }, [chatId, refresh, showSectionToast, voice, voiceSession.state]);

    useEffect(() => {
        if (!chatId) return undefined;
        const triggerCheckin = async () => {
            try {
                await apiRequest('/api/proactive/check-in', {
                    method: 'POST',
                    body: JSON.stringify({ chat_id: chatId, cooldown_minutes: 30 }),
                });
            } catch { /* ignore */ }
        };
        const initialTimer = window.setTimeout(triggerCheckin, 90 * 1000);
        const periodicTimer = window.setInterval(triggerCheckin, 20 * 60 * 1000);
        return () => {
            window.clearTimeout(initialTimer);
            window.clearInterval(periodicTimer);
        };
    }, [chatId]);

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
            .catch(() => {});
    }, [revision]);

    const startChat = useCallback(async () => {
        try {
            const chat = await apiRequest('/api/chats', { method: 'POST' });
            setChats((current) => [chat, ...current]);
            setPrompt('');
            setDrawerOpen(false);
            openSection(null);
            await openChat(chat.id);
        } catch (requestError) {
            setError(requestError.message);
        }
    }, [openChat, openSection]);

    const selectChat = useCallback((id) => {
        setConfirmingId('');
        setDrawerOpen(false);
        openSection(null);
        if (id !== chatId) openChat(id);
    }, [chatId, openChat, openSection]);

    const deleteChat = useCallback(async (id) => {
        try {
            await apiRequest(`/api/chats/${id}`, { method: 'DELETE' });
            setConfirmingId('');
            window.dispatchEvent(new CustomEvent('orbit:chat_deleted', { detail: { deletedId: id } }));
            const remaining = chats.filter((c) => c.id !== id);
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
    }, [chatId, chats, openChat]);

    const executeSlashCommand = useCallback((item) => {
        setPrompt('');
        if (item.action === 'live') {
            toggleLiveMode();
            return;
        }
        if (item.action === 'new_chat') {
            startChat();
            return;
        }
        openSection(item.section);
    }, [openSection, startChat, toggleLiveMode]);

    const submitPrompt = useCallback(async (rawValue) => {
        const value = String(rawValue || '').trim();
        if (!value || loading || !chatId) return;

        window.dispatchEvent(new CustomEvent('spidey:submit_wave'));

        const slashMatch = SLASH_COMMANDS.find((c) => c.cmd === value.toLowerCase());
        if (slashMatch) {
            executeSlashCommand(slashMatch);
            return;
        }

        const optimisticId = `pending-${Date.now()}`;
        const streamingId = `streaming-${optimisticId}`;
        setMessages((current) => [
            ...current,
            { id: optimisticId, role: 'user', content: value, pending: true },
        ]);
        setLoading(true);
        brain?.setBrainState('thinking');
        brain?.triggerPulse?.(0.95);
        setPrompt('');
        setError('');

        try {
            let finalData = null;
            await apiStreamRequest('/api/generate/stream', {
                method: 'POST',
                body: JSON.stringify({ prompt: value, chat_id: chatId }),
            }, (evt) => {
                if (activeChatRef.current !== chatId || !evt || !evt.type) return;
                if (evt.type === 'token' && evt.text) {
                    brain?.setBrainState('streaming');
                    brain?.triggerPulse?.(0.45);
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

            if (activeChatRef.current !== chatId || !finalData) return;
            const data = finalData;
            const { touchedSections, targetSection } = applyUiActions(
                data.ui_actions,
                value,
                data.navigate || null,
                data.provider || ''
            );

            setMessages((current) => {
                const existingNotifs = current.filter((m) => m.notification);
                const serverMessages = (data.messages || []).map((msg, idx, arr) => (
                    idx === arr.length - 1 && msg.role === 'assistant' && touchedSections.length > 0
                        ? { ...msg, relatedSections: touchedSections }
                        : msg
                ));
                if (!existingNotifs.length) return serverMessages;
                return [...serverMessages, ...existingNotifs].sort((a, b) => {
                    const ta = a.created_at ? Date.parse(a.created_at) : 0;
                    const tb = b.created_at ? Date.parse(b.created_at) : 0;
                    return ta - tb;
                });
            });

            const effectiveSection = targetSection !== undefined ? targetSection : activeSection;
            if (effectiveSection && data.response) {
                showSectionToast(data.response);
            }

            if ((data.spoken_response || data.response) && voice.speakEnabled && voiceSession.state === 'idle') {
                voice.speak(data.spoken_response || data.response, {
                    alreadySummarized: Boolean(data.spoken_response),
                });
            } else {
                brain?.setBrainState('idle');
            }
            refreshChats();
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
    }, [activeSection, applyUiActions, brain, chatId, executeSlashCommand, loading, refresh, refreshChats, showSectionToast, voice, voiceSession.state]);

    useEffect(() => {
        submitPromptRef.current = submitPrompt;
    });

    useEffect(() => {
        const onExternalPrompt = (event) => {
            const incoming = event?.detail?.prompt;
            if (!incoming) return;
            submitPromptRef.current?.(incoming);
        };
        const onToggleVoice = () => {
            toggleLiveMode();
        };
        window.addEventListener('spidey:prompt', onExternalPrompt);
        window.addEventListener('spidey:open_live', onToggleVoice);
        window.addEventListener('spidey:open_listen', onToggleVoice);
        return () => {
            window.removeEventListener('spidey:prompt', onExternalPrompt);
            window.removeEventListener('spidey:open_live', onToggleVoice);
            window.removeEventListener('spidey:open_listen', onToggleVoice);
        };
    }, [toggleLiveMode]);

    const isHero = messages.length === 0 && !loading;
    const brainState = brain?.brainState || 'idle';
    const isFullLiveOverlay = liveOpen && !activeSection;

    const voiceCaption = useMemo(() => {
        if (voiceSession.state === 'connecting') return 'Connecting live mode…';
        if (voiceSession.state === 'listening') return voiceSession.isMuted ? 'Live mode muted' : 'Listening live…';
        if (voiceSession.state === 'transcribing') return 'Transcribing…';
        if (voiceSession.state === 'thinking' || brainState === 'thinking') return 'Thinking…';
        if (brainState === 'streaming') return 'Responding…';
        if (voiceSession.state === 'speaking' || voice.isSpeaking) return 'Speaking…';
        return 'Ctrl+Space for Live Mode · type / for commands';
    }, [voiceSession.state, voiceSession.isMuted, brainState, voice.isSpeaking]);

    return (
        <div className={`app-theme-${theme} relative flex h-dvh w-screen flex-col overflow-hidden bg-[#050505] text-[#F2EFE9]`}>
            {/* FULL-SCREEN INTERACTIVE TOPOGRAPHIC ASCII BACKGROUND (Paused automatically during full LiveOverlay) */}
            <SpideyAsciiCanvas paused={isFullLiveOverlay} />
            <div
                aria-hidden="true"
                className="pointer-events-none fixed inset-0 z-[1] bg-[radial-gradient(ellipse_at_center,transparent_25%,rgba(5,5,5,0.62)_100%)]"
            />

            {/* TOP NAVBAR WITH CORE WORKSPACE SECTIONS + MUTE & LIVE CONTROLS */}
            <TopNavbar
                activeSection={activeSection}
                liveOpen={liveOpen}
                voiceState={voiceSession.state}
                isMicMuted={voiceSession.isMuted}
                onToggleMicMute={voiceSession.toggleMute}
                speakEnabled={voice.speakEnabled}
                engineReady={voice.engineReady}
                ttsError={voice.error}
                onToggleSpeak={voice.toggleSpeak}
                onOpenDrawer={() => setDrawerOpen(true)}
                onSelectSection={openSection}
                onToggleLive={toggleLiveMode}
                chatId={chatId}
                loading={loading}
                online={online}
            />

            <ChatHistoryDrawer
                open={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                chats={chats}
                chatId={chatId}
                chatSearch={chatSearch}
                onSearchChange={setChatSearch}
                confirmingId={confirmingId}
                onConfirmingChange={setConfirmingId}
                onStartChat={startChat}
                onSelectChat={selectChat}
                onDeleteChat={deleteChat}
                displayName={currentUser?.displayName}
                online={online}
            />

            {/* PURE CALM FOREGROUND OVER FULL-SCREEN INTERACTIVE ASCII BACKGROUND */}
            <main
                className={`relative z-10 flex min-h-0 flex-1 flex-col items-center overflow-hidden transition-opacity duration-200 ${
                    isFullLiveOverlay ? 'pointer-events-none opacity-0' : 'opacity-100'
                }`}
            >
                <ConversationStream
                    isHero={isHero}
                    messages={messages}
                    loading={loading}
                    chatId={chatId}
                    liveOpen={liveOpen}
                    voiceState={voiceSession.state}
                    voiceTranscript={voiceSession.transcript}
                    voiceCaption={voiceCaption}
                    onSubmitPrompt={submitPrompt}
                    onOpenSection={openSection}
                    conversationEndRef={conversationEndRef}
                />

                <ComposerBar
                    prompt={prompt}
                    onPromptChange={setPrompt}
                    onSubmitPrompt={submitPrompt}
                    slashCommands={SLASH_COMMANDS}
                    onExecuteSlashCommand={executeSlashCommand}
                    chatId={chatId}
                    loading={loading}
                    error={error}
                    voiceError={voiceSession.error}
                    speakEnabled={voice.speakEnabled}
                    engineReady={voice.engineReady}
                    onToggleSpeak={voice.toggleSpeak}
                    ttsError={voice.error}
                    isMicMuted={voiceSession.isMuted}
                    onToggleMicMute={voiceSession.toggleMute}
                    isVoiceActive={isVoiceActive}
                    onVoiceStop={handleVoiceStop}
                    liveActive={liveOpen || voiceSession.isLiveActive}
                    voiceState={voiceSession.state}
                    onToggleLive={toggleLiveMode}
                />
            </main>

            {/* FLOATING POP-UP OVERLAY BELOW TOP NAVBAR FOR ANY SECTION */}
            <AnimatePresence>
                {activeSection && (
                    <div className="fixed inset-x-0 bottom-0 top-12 z-30 flex items-center justify-center p-3 sm:p-6">
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            onClick={() => openSection(null)}
                            className="fixed inset-x-0 bottom-0 top-12 bg-black/75 backdrop-blur-[3px]"
                        />
                        <div className="relative z-10 flex max-h-[82dvh] w-full max-w-4xl flex-col">
                            <AnimatePresence>
                                {sectionReplyToast && (
                                    <motion.div
                                        initial={{ opacity: 0, y: -6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: -4 }}
                                        className="mb-2.5 flex items-start justify-between gap-3 border border-[#D95D24]/50 bg-[#0B0A09] px-4 py-2.5 text-xs text-[#F2EFE9]"
                                    >
                                        <p className="line-clamp-2 flex-1 leading-relaxed">{sectionReplyToast}</p>
                                        <button
                                            type="button"
                                            onClick={() => setSectionReplyToast(null)}
                                            className="font-mono text-[11px] text-[#8E867D] hover:text-[#F2EFE9]"
                                        >
                                            ×
                                        </button>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            <SectionCanvasCard
                                key={activeSection}
                                sectionId={activeSection}
                                onClose={() => openSection(null)}
                                onAskSpidey={(q) => {
                                    openSection(null);
                                    submitPrompt(q);
                                }}
                            />
                        </div>
                    </div>
                )}
            </AnimatePresence>

            {/* LIVE MODE OVERLAY */}
            <AnimatePresence>
                {isFullLiveOverlay && (
                    <Suspense fallback={null}>
                        <LiveOverlay
                            state={voiceSession.state}
                            isMuted={voiceSession.isMuted}
                            transcript={voiceSession.transcript}
                            reply={voiceSession.reply}
                            turns={liveTurns}
                            timing={voiceSession.timing}
                            error={voiceSession.error}
                            onToggleMute={voiceSession.toggleMute}
                            onCommit={voiceSession.commitUtterance}
                            onInterrupt={voiceSession.interrupt}
                            onRetry={() => voiceSession.startSession('live', chatId)}
                            onClose={stopLiveMode}
                        />
                    </Suspense>
                )}
            </AnimatePresence>

            {/* Discreet floating Live pill if user opened a section pop-up during Live Mode */}
            <AnimatePresence>
                {liveOpen && activeSection && (
                    <motion.div
                        initial={{ opacity: 0, y: -8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -6 }}
                        className="fixed right-4 top-14 z-40 flex items-center gap-2 border border-[#D95D24] bg-[#0B0807]/92 px-3 py-1.5 font-mono text-[11px] backdrop-blur-md"
                    >
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#D95D24]" />
                        <span className="uppercase tracking-[0.12em] text-[#FFD4A8]">
                            live · {voiceSession.isMuted ? 'muted' : voiceSession.state}
                        </span>
                        <button
                            type="button"
                            onClick={voiceSession.toggleMute}
                            className="border border-[#F2EFE9]/16 px-2 py-0.5 text-[10px] uppercase text-[#CFC9BF] hover:border-[#D95D24] hover:text-[#F2EFE9]"
                        >
                            {voiceSession.isMuted ? 'unmute' : 'mute'}
                        </button>
                        <button
                            type="button"
                            onClick={() => openSection(null)}
                            className="border border-[#F2EFE9]/16 px-2 py-0.5 text-[10px] uppercase text-[#CFC9BF] hover:border-[#D95D24] hover:text-[#F2EFE9]"
                        >
                            view
                        </button>
                        <button
                            type="button"
                            onClick={stopLiveMode}
                            className="border border-[#D95D24]/70 bg-[#D95D24] px-2 py-0.5 text-[10px] font-semibold uppercase text-[#060606] hover:bg-[#E86B30]"
                        >
                            end
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
