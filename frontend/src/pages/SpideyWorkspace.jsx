import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { AnimatePresence, motion } from 'framer-motion';
import { format } from 'date-fns';
import { apiRequest, apiStreamRequest } from '../services/api';
import { useAppData } from '../context/AppDataContext';
import { useAuth, useTheme } from '../context/AuthContext';
import { useSpideyBrain } from '../context/SpideyBrainContext';
import { cleanAssistantText } from '../utils/textUtils';
import { useVoice } from '../hooks/useVoice';
import { useVoiceSession } from '../hooks/useVoiceSession';
import SpeakToggle from '../components/voice/SpeakToggle';
import LiveButton from '../components/voice/LiveButton';
import LiveOverlay from '../components/voice/LiveOverlay';
import StopButton from '../components/voice/StopButton';
import OrbitAgentView from '../components/OrbitAgentView';
import SpideyAsciiCanvas from '../components/ascii/SpideyAsciiCanvas';
import SectionCanvasCard from '../components/workspace/SectionCanvasCard';
import { SECTION_META } from '../components/workspace/sectionMeta';

const ACTIVE_CHAT_KEY = 'spidey_active_chat_id';
const LEGACY_ACTIVE_CHAT_KEY = 'jarvis_active_chat_id';

const QUICK_HINTS = [
    "What's pending today?",
    'Open my learning',
    'Check my habits',
    'Summarize my day',
];

const SLASH_COMMANDS = [
    { cmd: '/tasks', desc: 'Open Tasks', section: 'tasks' },
    { cmd: '/habits', desc: 'Open Habits', section: 'habits' },
    { cmd: '/learning', desc: 'Open Learning', section: 'learning' },
    { cmd: '/reminders', desc: 'Open Reminders & Memory', section: 'reminders' },
    { cmd: '/analytics', desc: 'Open Analytics', section: 'analytics' },
    { cmd: '/settings', desc: 'Open Settings', section: 'settings' },
    { cmd: '/live', desc: 'Toggle Live Voice Mode (Ctrl+Space)', action: 'live' },
    { cmd: '/orbit', desc: 'Open ORBIT007 Live Agent', action: 'orbit' },
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

const formatWhen = (value) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : format(date, 'MMM d');
};

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

    // Quiet slide-over chat history drawer (starts closed for pure calm canvas)
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [chatSearch, setChatSearch] = useState('');

    // Active section opens as a calm floating pop-up modal
    const activeSection = ROUTE_TO_SECTION[location.pathname] ?? null;
    const [orbitMode, setOrbitMode] = useState(false);

    // Chat state
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
    const textareaRef = useRef(null);
    const toastTimerRef = useRef(null);

    const voice = useVoice();

    const openSection = useCallback((sectionKey) => {
        const normalized = sectionKey ? normalizeSectionKey(sectionKey) : null;
        if (normalized === undefined) return;
        setOrbitMode(false);
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
        setOrbitMode(false);
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

    // Ctrl+Space toggles Live Mode anywhere (even inside the composer) + Esc dismisses overlays
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
                if (orbitMode) {
                    setOrbitMode(false);
                    return;
                }
                if (activeSection) {
                    openSection(null);
                    return;
                }
                if (drawerOpen) {
                    setDrawerOpen(false);
                    return;
                }
            }
        };

        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [activeSection, chatId, drawerOpen, liveOpen, loading, openSection, orbitMode, stopLiveMode, toggleLiveMode]);

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
            setOrbitMode(false);
            setDrawerOpen(false);
            openSection(null);
            await openChat(chat.id);
        } catch (requestError) {
            setError(requestError.message);
        }
    }, [openChat, openSection]);

    const selectChat = (id) => {
        setConfirmingId('');
        setOrbitMode(false);
        setDrawerOpen(false);
        openSection(null);
        if (id !== chatId) openChat(id);
    };

    const deleteChat = async (id) => {
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
    };

    const executeSlashCommand = useCallback((item) => {
        setPrompt('');
        if (item.action === 'live') {
            toggleLiveMode();
            return;
        }
        if (item.action === 'orbit') {
            window.dispatchEvent(new CustomEvent('spidey:audio_stop'));
            setOrbitMode(true);
            return;
        }
        if (item.action === 'new_chat') {
            startChat();
            return;
        }
        openSection(item.section);
    }, [openSection, startChat, toggleLiveMode]);

    const submitPrompt = async (rawValue) => {
        const value = rawValue.trim();
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
    };
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

    const filteredChats = useMemo(() => {
        const q = chatSearch.trim().toLowerCase();
        if (!q) return chats;
        return chats.filter((c) => (c.title || 'New session').toLowerCase().includes(q));
    }, [chats, chatSearch]);

    const slashSuggestions = useMemo(() => {
        const trimmed = prompt.trim().toLowerCase();
        if (!trimmed.startsWith('/')) return [];
        return SLASH_COMMANDS.filter((item) => item.cmd.startsWith(trimmed) || item.desc.toLowerCase().includes(trimmed.slice(1)));
    }, [prompt]);

    const isHero = messages.length === 0 && !loading;
    const brainState = brain?.brainState || 'idle';

    const voiceCaption = useMemo(() => {
        if (voiceSession.state === 'connecting') return 'Connecting live mode…';
        if (voiceSession.state === 'listening') return voiceSession.isMuted ? 'Live mode muted' : 'Listening live…';
        if (voiceSession.state === 'transcribing') return 'Transcribing…';
        if (voiceSession.state === 'thinking' || brainState === 'thinking') return 'Thinking…';
        if (brainState === 'streaming') return 'Responding…';
        if (voiceSession.state === 'speaking' || voice.isSpeaking) return 'Speaking…';
        return 'Ctrl+Space for Live Mode · type / for commands';
    }, [voiceSession.state, voiceSession.isMuted, brainState, voice.isSpeaking]);

    const handleSendSubmit = (e) => {
        e.preventDefault();
        submitPrompt(prompt);
    };

    const handlePromptChange = (e) => {
        setPrompt(e.target.value);
    };

    const handleComposerKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (slashSuggestions.length === 1 && prompt.trim().startsWith('/')) {
                executeSlashCommand(slashSuggestions[0]);
                return;
            }
            submitPrompt(prompt);
            return;
        }
        if (!e.ctrlKey && !e.metaKey && !e.altKey) {
            if (e.key.length === 1 || e.key === 'Backspace') {
                window.dispatchEvent(
                    new CustomEvent('spidey:keystroke', {
                        detail: { key: e.key, isDelete: e.key === 'Backspace' },
                    })
                );
            }
        }
    };

    return (
        <div className={`app-theme-${theme} relative flex h-dvh w-screen flex-col overflow-hidden bg-[#050505] text-[#F2EFE9]`}>
            {/* FULL-SCREEN INTERACTIVE TOPOGRAPHIC ASCII BACKGROUND (Mouse + Typing Reactive) */}
            <SpideyAsciiCanvas />
            {/* Soft radial vignette for serene contrast and effortless readability */}
            <div
                aria-hidden="true"
                className="pointer-events-none fixed inset-0 z-[1] bg-[radial-gradient(ellipse_at_center,transparent_25%,rgba(5,5,5,0.62)_100%)]"
            />

            {/* Larger crisp floating corner history toggle — ZERO top navbar */}
            <button
                type="button"
                onClick={() => setDrawerOpen(true)}
                aria-label="Open chat history"
                title="Conversations"
                className="fixed left-4 top-4 z-20 flex h-10 w-10 items-center justify-center border border-[#F2EFE9]/14 bg-[#070606]/78 text-[#CFC9BF] backdrop-blur-sm transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9]"
            >
                <span className="flex flex-col gap-[4.5px]">
                    <span className="block h-[1.5px] w-4 bg-current" />
                    <span className="block h-[1.5px] w-4 bg-current" />
                    <span className="block h-[1.5px] w-3 bg-current" />
                </span>
            </button>

            {/* Subtle floating ORBIT brand mark in top-right corner */}
            {!liveOpen && (
                <div className="pointer-events-none fixed right-5 top-4 z-20 flex items-center gap-2.5 select-none">
                    <img
                        src="/logo.png"
                        alt="ORBIT"
                        className="h-7 w-7 rounded-full object-cover"
                    />
                    <span className="font-mono text-xs font-semibold tracking-[0.26em] text-[#F2EFE9]/90">
                        ORBIT
                    </span>
                </div>
            )}

            {/* Slide-Over Chat History Drawer (Hidden until needed) */}
            <AnimatePresence>
                {drawerOpen && (
                    <>
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            onClick={() => setDrawerOpen(false)}
                            className="fixed inset-0 z-40 bg-black/70 backdrop-blur-[2px]"
                        />
                        <motion.aside
                            initial={{ x: '-100%' }}
                            animate={{ x: 0 }}
                            exit={{ x: '-100%' }}
                            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                            className="fixed inset-y-0 left-0 z-50 flex w-[272px] flex-col border-r border-[#F2EFE9]/12 bg-[#080807]"
                        >
                            <div className="flex items-center justify-between px-5 py-4">
                                <div className="flex items-center gap-2.5">
                                    <img
                                        src="/logo.png"
                                        alt="ORBIT"
                                        className="h-5 w-5 rounded-full object-cover"
                                    />
                                    <span className="font-mono text-xs font-semibold tracking-[0.22em] text-[#F2EFE9]">
                                        ORBIT
                                    </span>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => setDrawerOpen(false)}
                                    className="font-mono text-xs text-[#7D756C] hover:text-[#F2EFE9]"
                                >
                                    [×]
                                </button>
                            </div>

                            <div className="space-y-2.5 px-4 pb-3">
                                <button
                                    type="button"
                                    onClick={startChat}
                                    className="w-full border border-[#D95D24]/70 bg-[#D95D24]/12 py-2 font-mono text-xs text-[#F2EFE9] transition-colors hover:bg-[#D95D24] hover:text-[#060606]"
                                >
                                    + New chat
                                </button>
                                <input
                                    type="text"
                                    value={chatSearch}
                                    onChange={(e) => setChatSearch(e.target.value)}
                                    placeholder="Search chats…"
                                    className="w-full border border-[#F2EFE9]/12 bg-[#060606] px-3 py-1.5 font-mono text-xs text-[#F2EFE9] outline-none placeholder:text-[#5C564F] focus:border-[#D95D24]"
                                />
                            </div>

                            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
                                <div className="space-y-0.5">
                                    {filteredChats.map((chat) => {
                                        const isActive = chat.id === chatId;
                                        const confirming = confirmingId === chat.id;
                                        return (
                                            <div
                                                key={chat.id}
                                                className={`group flex items-center gap-1 px-2.5 py-2 transition-colors ${
                                                    isActive
                                                        ? 'border-l-2 border-[#D95D24] bg-[#140E0A] text-[#F2EFE9]'
                                                        : 'text-[#8E867D] hover:bg-[#0F0E0D] hover:text-[#F2EFE9]'
                                                }`}
                                            >
                                                <button
                                                    type="button"
                                                    onClick={() => selectChat(chat.id)}
                                                    className="min-w-0 flex-1 text-left"
                                                >
                                                    <div className="truncate text-xs">{chat.title || 'New chat'}</div>
                                                    <div className="mt-0.5 font-mono text-[10px] text-[#5C564F]">
                                                        {formatWhen(chat.updated_at)}
                                                    </div>
                                                </button>
                                                {confirming ? (
                                                    <div className="flex shrink-0 items-center gap-1 font-mono text-[10px]">
                                                        <button
                                                            type="button"
                                                            onClick={() => deleteChat(chat.id)}
                                                            className="bg-[#D95D24] px-1.5 py-0.5 text-[#060606]"
                                                        >
                                                            yes
                                                        </button>
                                                        <button
                                                            type="button"
                                                            onClick={() => setConfirmingId('')}
                                                            className="px-1.5 py-0.5 text-[#8E867D]"
                                                        >
                                                            no
                                                        </button>
                                                    </div>
                                                ) : (
                                                    <button
                                                        type="button"
                                                        onClick={() => setConfirmingId(chat.id)}
                                                        className="px-1 font-mono text-[10px] text-[#5C564F] opacity-0 transition-opacity hover:text-[#D95D24] group-hover:opacity-100"
                                                    >
                                                        ×
                                                    </button>
                                                )}
                                            </div>
                                        );
                                    })}
                                    {!filteredChats.length && (
                                        <p className="px-2 py-6 text-center font-mono text-[11px] text-[#5C564F]">
                                            No chats found
                                        </p>
                                    )}
                                </div>
                            </div>

                            <div className="flex items-center justify-between border-t border-[#F2EFE9]/10 px-4 py-3 font-mono text-[11px] text-[#7D756C]">
                                <span className="truncate">{currentUser?.displayName || 'Local'}</span>
                                <span className={online ? 'text-[#D95D24]' : 'text-[#5C564F]'}>
                                    {online ? '● online' : '○ offline'}
                                </span>
                            </div>
                        </motion.aside>
                    </>
                )}
            </AnimatePresence>

            {/* PURE CALM FOREGROUND OVER FULL-SCREEN INTERACTIVE ASCII BACKGROUND */}
            <main
                className={`relative z-10 flex min-h-0 flex-1 flex-col items-center overflow-hidden transition-opacity duration-200 ${
                    liveOpen && !activeSection && !orbitMode ? 'pointer-events-none opacity-0' : 'opacity-100'
                }`}
            >
                {isHero ? (
                    /* Serene Hero Stage Floating Effortlessly Over the Living ASCII Terrain */
                    <div className="flex min-h-0 w-full flex-1 flex-col items-center justify-center px-6 pb-8">
                        <div className="text-center">
                            <img
                                src="/logo.png"
                                alt="ORBIT"
                                className="mx-auto mb-3.5 h-12 w-12 rounded-full object-cover"
                            />
                            <h1 className="font-mono text-2xl font-medium tracking-[0.42em] text-[#F2EFE9] sm:text-3xl">
                                ORBIT
                            </h1>
                            <p
                                className={`mt-3 font-mono text-xs transition-colors ${
                                    liveOpen || voiceSession.state !== 'idle'
                                        ? 'text-[#FF944D]'
                                        : 'text-[#A8A096]'
                                }`}
                            >
                                {voiceSession.transcript && voiceSession.state !== 'idle'
                                    ? `“${voiceSession.transcript}”`
                                    : voiceCaption}
                            </p>
                        </div>

                        {/* Quiet, Minimal Prompt Hints */}
                        <div className="mt-8 flex max-w-xl flex-wrap items-center justify-center gap-2.5">
                            {QUICK_HINTS.map((hint) => (
                                <button
                                    key={hint}
                                    type="button"
                                    onClick={() => submitPrompt(hint)}
                                    disabled={loading || !chatId}
                                    className="border border-[#F2EFE9]/14 bg-[#070606]/78 px-3.5 py-1.5 text-xs text-[#CFC9BF] backdrop-blur-[2px] transition-colors hover:border-[#D95D24] hover:bg-[#120B07]/90 hover:text-[#F2EFE9] disabled:opacity-35"
                                >
                                    {hint}
                                </button>
                            ))}
                        </div>
                    </div>
                ) : (
                    /* Calm Conversation Stream Floating Over the Interactive ASCII Background */
                    <div className="min-h-0 w-full flex-1 overflow-y-auto px-5 pb-4 pt-12 sm:px-8">
                        <div className="mx-auto max-w-2xl space-y-5">
                            {messages.slice(-40).map((item, index) => {
                                const isUser = item.role === 'user';
                                return (
                                    <motion.div
                                        key={`${item.role}-${item.id || index}`}
                                        initial={{ opacity: 0, y: 6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ duration: 0.16 }}
                                        className={isUser ? 'flex justify-end' : 'flex justify-start'}
                                    >
                                        <div className={`max-w-[88%] ${isUser ? 'text-right' : 'w-full'}`}>
                                            {isUser ? (
                                                <div
                                                    className={`inline-block border border-[#D95D24]/45 bg-[#120B07]/85 px-4 py-2.5 text-left text-[14px] leading-relaxed text-[#F2EFE9] backdrop-blur-[3px] ${
                                                        item.pending ? 'opacity-65' : ''
                                                    }`}
                                                >
                                                    <span className="whitespace-pre-wrap">{item.content}</span>
                                                    {item.failed && (
                                                        <p className="mt-1 font-mono text-[10px] text-[#D95D24]">
                                                            Could not send — try again
                                                        </p>
                                                    )}
                                                </div>
                                            ) : (
                                                <div className="border-l-2 border-[#D95D24]/60 bg-[#070606]/78 px-4 py-3 backdrop-blur-[3px]">
                                                    <div className="assistant-message text-[14.5px] leading-[1.7] text-[#F2EFE9]">
                                                        <ReactMarkdown>{cleanAssistantText(item.content)}</ReactMarkdown>
                                                        {item.streaming && <span className="ascii-cursor ml-1" />}
                                                    </div>

                                                    {Array.isArray(item.relatedSections) && item.relatedSections.length > 0 && (
                                                        <div className="mt-3 flex flex-wrap gap-2">
                                                            {item.relatedSections.map((secKey) => {
                                                                const secMeta = SECTION_META[secKey];
                                                                if (!secMeta) return null;
                                                                return (
                                                                    <button
                                                                        key={secKey}
                                                                        type="button"
                                                                        onClick={() => openSection(secKey)}
                                                                        className="border border-[#D95D24]/55 bg-[#120B07]/90 px-3 py-1 font-mono text-[11px] text-[#FF944D] transition-colors hover:bg-[#D95D24] hover:text-[#060606]"
                                                                    >
                                                                        Open {secMeta.label} →
                                                                    </button>
                                                                );
                                                            })}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </motion.div>
                                );
                            })}

                            {loading && !messages.some((m) => m.streaming) && (
                                <div className="inline-block border-l-2 border-[#D95D24] bg-[#070606]/78 px-4 py-2 font-mono text-xs text-[#CFC9BF] backdrop-blur-[3px]">
                                    Thinking<span className="ascii-cursor ml-1.5" />
                                </div>
                            )}
                            <div ref={conversationEndRef} />
                        </div>
                    </div>
                )}

                {/* SINGLE CLEAN BOTTOM CHATBAR — Triggers Satisfying Ripples on Every Keystroke */}
                <div className="relative z-20 w-full shrink-0 px-4 pb-5 pt-2 sm:px-6 sm:pb-7">
                    <div className="relative mx-auto w-full max-w-2xl">
                        {/* Quiet Slash Command Popover */}
                        <AnimatePresence>
                            {slashSuggestions.length > 0 && (
                                <motion.div
                                    initial={{ opacity: 0, y: 6 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: 4 }}
                                    className="ascii-frame absolute bottom-full left-0 right-0 z-30 mb-2 bg-[#090807]/95 p-1.5 shadow-2xl backdrop-blur-md"
                                >
                                    {slashSuggestions.map((item) => (
                                        <button
                                            key={item.cmd}
                                            type="button"
                                            onClick={() => {
                                                executeSlashCommand(item);
                                                textareaRef.current?.focus();
                                            }}
                                            className="flex w-full items-center justify-between px-3 py-2 text-left text-xs transition-colors hover:bg-[#D95D24]/16"
                                        >
                                            <span className="font-mono font-medium text-[#D95D24]">{item.cmd}</span>
                                            <span className="text-[#8E867D]">{item.desc}</span>
                                        </button>
                                    ))}
                                </motion.div>
                            )}
                        </AnimatePresence>

                        <form
                            onSubmit={handleSendSubmit}
                            className="flex items-center gap-2 border border-[#F2EFE9]/16 bg-[#090807]/85 px-3.5 py-2 backdrop-blur-md transition-colors focus-within:border-[#D95D24]"
                        >
                            <textarea
                                ref={textareaRef}
                                value={prompt}
                                onChange={handlePromptChange}
                                onKeyDown={handleComposerKeyDown}
                                rows={1}
                                maxLength={2000}
                                placeholder="Ask ORBIT anything… or type /"
                                className="max-h-28 min-h-[34px] flex-1 resize-none bg-transparent py-1.5 text-[14px] leading-relaxed text-[#F2EFE9] outline-none placeholder:text-[#7D756C]"
                                disabled={!chatId}
                            />

                            <SpeakToggle
                                speakEnabled={voice.speakEnabled}
                                engineReady={voice.engineReady}
                                onToggle={voice.toggleSpeak}
                                error={voice.error}
                            />

                            <StopButton
                                state={isVoiceActive ? 'speaking' : 'idle'}
                                onStop={handleVoiceStop}
                            />

                            <LiveButton
                                active={liveOpen || voiceSession.isLiveActive}
                                state={voiceSession.state}
                                onClick={toggleLiveMode}
                                disabled={!chatId || loading}
                            />

                            <button
                                type="submit"
                                disabled={loading || !prompt.trim() || !chatId}
                                className="h-9 shrink-0 border border-[#D95D24] bg-[#D95D24] px-4 font-mono text-xs font-semibold text-[#060606] transition-colors hover:bg-[#E86B30] disabled:opacity-30"
                                aria-label="Send message"
                            >
                                Send
                            </button>
                        </form>

                        {(error || voiceSession.error) && (
                            <p className="mt-2 text-center font-mono text-[11px] text-[#D95D24]">
                                {error || voiceSession.error}
                            </p>
                        )}
                    </div>
                </div>
            </main>

            {/* CALM FLOATING POP-UP OVERLAY FOR ANY SECTION OPENED VIA CHAT */}
            <AnimatePresence>
                {activeSection && !orbitMode && (
                    <div className="fixed inset-0 z-30 flex items-center justify-center p-3 sm:p-6">
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            onClick={() => openSection(null)}
                            className="fixed inset-0 bg-black/75 backdrop-blur-[3px]"
                        />
                        <div className="relative z-10 flex max-h-[86dvh] w-full max-w-4xl flex-col">
                            {/* Subtle reply toast if S.P.I.D.E.Y speaks while pop-up is open */}
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

            {/* LIVE MODE OVERLAY (Full-screen transparent ASCII HUD over living 3D terrain) */}
            <AnimatePresence>
                {liveOpen && !activeSection && !orbitMode && (
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
                )}
            </AnimatePresence>

            {/* Discreet floating Live pill if user opened a section pop-up during Live Mode */}
            <AnimatePresence>
                {liveOpen && (activeSection || orbitMode) && (
                    <motion.div
                        initial={{ opacity: 0, y: -8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -6 }}
                        className="fixed right-4 top-4 z-40 flex items-center gap-2 border border-[#D95D24] bg-[#0B0807]/92 px-3 py-1.5 font-mono text-[11px] backdrop-blur-md"
                    >
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#D95D24]" />
                        <span className="uppercase tracking-[0.12em] text-[#FFD4A8]">
                            live · {voiceSession.isMuted ? 'muted' : voiceSession.state}
                        </span>
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

            {/* ORBIT007 POP-UP OVERLAY (opened via /orbit) */}
            <AnimatePresence>
                {orbitMode && (
                    <div className="fixed inset-0 z-30 flex items-center justify-center p-3 sm:p-6">
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            onClick={() => setOrbitMode(false)}
                            className="fixed inset-0 bg-black/75 backdrop-blur-[3px]"
                        />
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 6 }}
                            className="ascii-frame relative z-10 flex h-[82dvh] w-full max-w-3xl flex-col bg-[#080807]"
                        >
                            <div className="flex items-center justify-between border-b border-[#F2EFE9]/10 px-5 py-3">
                                <span className="font-mono text-xs uppercase tracking-[0.16em] text-[#D95D24]">
                                    ORBIT007 Live Agent
                                </span>
                                <button
                                    type="button"
                                    onClick={() => setOrbitMode(false)}
                                    className="font-mono text-xs text-[#8E867D] hover:text-[#F2EFE9]"
                                >
                                    Close ×
                                </button>
                            </div>
                            <div className="min-h-0 flex-1">
                                <OrbitAgentView activeChatId={chatId} />
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
}
