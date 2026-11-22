import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { AnimatePresence, motion } from 'framer-motion';
import { format } from 'date-fns';
import {
    Check,
    MessageSquare,
    MessageSquarePlus,
    PanelLeftClose,
    PanelLeftOpen,
    Radio,
    Search,
    Send,
    Settings as SettingsIcon,
    Sparkles,
    Trash2,
    X,
} from 'lucide-react';
import { apiRequest, apiStreamRequest } from '../services/api';
import { useAppData } from '../context/AppDataContext';
import { useAuth, useTheme } from '../context/AuthContext';
import { useSpideyBrain } from '../context/SpideyBrainContext';
import { cleanAssistantText } from '../utils/textUtils';
import { useVoice } from '../hooks/useVoice';
import { useVoiceSession } from '../hooks/useVoiceSession';
import SpeakToggle from '../components/voice/SpeakToggle';
import ListenButton from '../components/voice/ListenButton';
import StopButton from '../components/voice/StopButton';
import OrbitAgentView from '../components/OrbitAgentView';
import SpiderMark from '../components/brand/SpiderMark';
import SpideyNeuralCoreCanvas from '../components/three/SpideyNeuralCoreCanvas';
import SpideyRoamerOverlay from '../components/three/SpideyRoamerOverlay';
import SectionCanvasCard from '../components/workspace/SectionCanvasCard';
import { SECTION_META, SECTION_ORDER } from '../components/workspace/sectionMeta';

const ACTIVE_CHAT_KEY = 'spidey_active_chat_id';
const LEGACY_ACTIVE_CHAT_KEY = 'jarvis_active_chat_id';
const SIDEBAR_OPEN_KEY = 'spidey_focus_sidebar_open';

const STARTER_PROMPTS = [
    { label: "What's pending today?", sectionHint: 'tasks' },
    { label: 'Check my habits', sectionHint: 'habits' },
    { label: 'Next in learning', sectionHint: 'learning' },
    { label: 'Summarize my day', sectionHint: null },
];

const SLASH_COMMANDS = [
    { cmd: '/tasks', label: 'Tasks', desc: 'Open focused Tasks card', section: 'tasks' },
    { cmd: '/habits', label: 'Habits', desc: 'Open focused Habits card', section: 'habits' },
    { cmd: '/reminders', label: 'Reminders & Memory', desc: 'Open Reminders & Memory card', section: 'reminders' },
    { cmd: '/learning', label: 'Learning', desc: 'Open Learning Roadmaps card', section: 'learning' },
    { cmd: '/analytics', label: 'Analytics', desc: 'Open Productivity Telemetry card', section: 'analytics' },
    { cmd: '/settings', label: 'Settings', desc: 'Open Settings & API config card', section: 'settings' },
    { cmd: '/chat', label: 'Chat', desc: 'Return to pure S.P.I.D.E.Y chat', section: null },
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

function detectExplicitCardIntent(text) {
    const t = String(text || '').toLowerCase().trim();
    if (!t) return undefined;
    if (/^(show|open|view|check|pull up|display)\b/.test(t) || /\b(in my|my)\s+(tasks|todos|to-do|habits|reminders|memories|learning|roadmaps|analytics|settings)\b/.test(t)) {
        if (/\b(task|tasks|todo|todos|to-do|pending)\b/.test(t)) return 'tasks';
        if (/\b(habit|habits|streak|streaks)\b/.test(t)) return 'habits';
        if (/\b(reminder|reminders|memory|memories)\b/.test(t)) return 'reminders';
        if (/\b(learning|roadmap|roadmaps|study|topics)\b/.test(t)) return 'learning';
        if (/\b(analytics|telemetry|progress|heatmap|stats)\b/.test(t)) return 'analytics';
        if (/\b(setting|settings|preferences|theme|api key)\b/.test(t)) return 'settings';
    }
    return undefined;
}

const formatWhen = (value) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : format(date, 'MMM d, h:mm a');
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

    // Sidebar state (collapsible slim drawer just like Hedwig)
    const [sidebarOpen, setSidebarOpen] = useState(() => {
        try {
            const saved = localStorage.getItem(SIDEBAR_OPEN_KEY);
            if (saved !== null) return saved === '1';
            return typeof window !== 'undefined' ? window.innerWidth >= 1024 : true;
        } catch {
            return true;
        }
    });
    const [chatSearch, setChatSearch] = useState('');

    // Active section card derived directly from the URL route (null = pure chat / hero)
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
    const [spacePttHeld, setSpacePttHeld] = useState(false);

    const lastNotificationId = useRef(0);
    const conversationEndRef = useRef(null);
    const activeChatRef = useRef('');
    const requestSeq = useRef(0);
    const submitPromptRef = useRef(null);
    const spacePttHeldRef = useRef(false);
    const textareaRef = useRef(null);
    const toastTimerRef = useRef(null);

    const voice = useVoice();

    // Sync sidebar preference
    useEffect(() => {
        try {
            localStorage.setItem(SIDEBAR_OPEN_KEY, sidebarOpen ? '1' : '0');
        } catch { /* ignore */ }
    }, [sidebarOpen]);

    const openSection = useCallback((sectionKey) => {
        const normalized = sectionKey ? normalizeSectionKey(sectionKey) : null;
        if (normalized === undefined) return;
        setOrbitMode(false);
        const targetRoute = normalized ? SECTION_TO_ROUTE[normalized] : '/';
        if (targetRoute && location.pathname !== targetRoute) {
            navigate(targetRoute, { replace: false });
        }
    }, [location.pathname, navigate]);

    const showSectionToast = useCallback((text) => {
        if (!text) return;
        clearTimeout(toastTimerRef.current);
        setSectionReplyToast(cleanAssistantText(text));
        toastTimerRef.current = setTimeout(() => {
            setSectionReplyToast(null);
        }, 9000);
    }, []);

    const refreshChats = useCallback(async () => {
        try {
            const data = await apiRequest('/api/chats');
            setChats(data.chats || []);
        } catch { /* ignore */ }
    }, []);

    const applyUiActions = useCallback((actions, userPrompt = '') => {
        let navigatedSection = undefined;
        const touchedSections = new Set();

        if (Array.isArray(actions)) {
            for (const action of actions) {
                if (!action || !action.type) continue;
                if (action.type === 'refresh') {
                    const secs = Array.isArray(action.sections) ? action.sections : [];
                    secs.forEach((s) => {
                        const norm = normalizeSectionKey(s);
                        if (norm) touchedSections.add(norm);
                    });
                    window.dispatchEvent(new CustomEvent('orbit:refresh', { detail: { sections: secs } }));
                } else if (action.type === 'navigate') {
                    const target = normalizeSectionKey(action.page || action.route);
                    if (target !== undefined) {
                        navigatedSection = target;
                    }
                } else {
                    window.dispatchEvent(new CustomEvent('orbit:ui_action', { detail: action }));
                }
            }
        }

        if (navigatedSection !== undefined) {
            openSection(navigatedSection);
        } else {
            const explicit = detectExplicitCardIntent(userPrompt);
            if (explicit) {
                openSection(explicit);
            }
        }

        return [...touchedSections];
    }, [openSection]);

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
        const hasNavAction = Array.isArray(data?.ui_actions) && data.ui_actions.some((a) => a?.type === 'navigate');
        if (data?.navigate && !hasNavAction) {
            const navTarget = normalizeSectionKey(data.navigate);
            if (navTarget !== undefined) openSection(navTarget);
        }
        applyUiActions(data?.ui_actions, data?.transcript || '');
        if (replyText) {
            showSectionToast(replyText);
        }
        refreshChats();
        refresh();
    }, [applyUiActions, openSection, refresh, refreshChats, showSectionToast]);

    const voiceSession = useVoiceSession({
        onTranscript: handleSpeechTranscript,
        onReply: handleSpeechReply,
        audioQueue: voice.audioQueue,
    });

    useEffect(() => {
        if (chatId) {
            voiceSession.updateChatId(chatId);
        }
    }, [chatId, voiceSession]);

    const isVoiceActive = voice.isSpeaking || voiceSession.state !== 'idle';
    const handleVoiceStop = useCallback(() => {
        spacePttHeldRef.current = false;
        setSpacePttHeld(false);
        voice.stop();
        voiceSession.stopSession();
    }, [voice, voiceSession]);

    // Hold Spacebar to Talk (like Hedwig) + Esc to close active section card
    useEffect(() => {
        const onKeyDown = (e) => {
            if (e.key === 'Escape' && activeSection && !isTypingElement(document.activeElement)) {
                // Only close section card if no nested modal overlay is open
                const hasModal = document.querySelector('[role="dialog"]');
                if (!hasModal) {
                    openSection(null);
                }
                return;
            }
            if (
                e.code === 'Space'
                && !e.repeat
                && !e.ctrlKey
                && !e.metaKey
                && !e.altKey
                && !isTypingElement(document.activeElement)
                && document.activeElement?.tagName !== 'BUTTON'
                && chatId
                && !loading
                && !orbitMode
            ) {
                e.preventDefault();
                if (!spacePttHeldRef.current) {
                    spacePttHeldRef.current = true;
                    setSpacePttHeld(true);
                    window.dispatchEvent(new CustomEvent('spidey:audio_stop'));
                    brain?.triggerPulse?.(1.1);
                    voiceSession.startSession('ptt', chatId);
                }
            }
        };

        const releaseSpacePtt = () => {
            if (!spacePttHeldRef.current) return;
            spacePttHeldRef.current = false;
            setSpacePttHeld(false);
            voiceSession.commitUtterance();
        };

        const onKeyUp = (e) => {
            if (e.code === 'Space' && spacePttHeldRef.current) {
                e.preventDefault();
                releaseSpacePtt();
            }
        };

        window.addEventListener('keydown', onKeyDown);
        window.addEventListener('keyup', onKeyUp);
        window.addEventListener('blur', releaseSpacePtt);
        return () => {
            window.removeEventListener('keydown', onKeyDown);
            window.removeEventListener('keyup', onKeyUp);
            window.removeEventListener('blur', releaseSpacePtt);
        };
    }, [activeSection, brain, chatId, loading, openSection, orbitMode, voiceSession]);

    // Listen to orbit:navigate events from ORBIT007
    useEffect(() => {
        const handleOrbitNav = (e) => {
            const target = normalizeSectionKey(e.detail?.route || e.detail?.page);
            if (target !== undefined) openSection(target);
        };
        window.addEventListener('orbit:navigate', handleOrbitNav);
        return () => window.removeEventListener('orbit:navigate', handleOrbitNav);
    }, [openSection]);

    // Load conversation history + notifications
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

    // Initial workspace load
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

    // Notification polling
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

    // Periodic proactive check-in
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

    // Data reset listener
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

    const startChat = async () => {
        try {
            const chat = await apiRequest('/api/chats', { method: 'POST' });
            setChats((current) => [chat, ...current]);
            setPrompt('');
            setOrbitMode(false);
            openSection(null);
            await openChat(chat.id);
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const selectChat = (id) => {
        setConfirmingId('');
        setOrbitMode(false);
        openSection(null);
        if (id !== chatId) openChat(id);
        if (window.innerWidth < 1024) setSidebarOpen(false);
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

    const submitPrompt = async (rawValue) => {
        const value = rawValue.trim();
        if (!value || loading || !chatId) return;

        // Instant slash command handling (/tasks, /habits, /learning, etc.)
        const slashMatch = SLASH_COMMANDS.find((c) => c.cmd === value.toLowerCase());
        if (slashMatch) {
            setPrompt('');
            openSection(slashMatch.section);
            return;
        }

        const optimisticId = `pending-${Date.now()}`;
        const streamingId = `streaming-${optimisticId}`;
        setMessages((current) => [
            ...current,
            {
                id: optimisticId,
                role: 'user',
                content: value,
                pending: true,
            },
        ]);
        setLoading(true);
        brain?.setBrainState('thinking');
        brain?.triggerPulse?.(0.8);
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
                    brain?.triggerPulse?.(0.4);
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
            const touchedSections = applyUiActions(data.ui_actions, value);
            const hasNavAction = Array.isArray(data.ui_actions) && data.ui_actions.some((a) => a?.type === 'navigate');
            if (data.navigate && !hasNavAction) {
                const navTarget = normalizeSectionKey(data.navigate);
                if (navTarget !== undefined) openSection(navTarget);
            }

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

            if (activeSection && data.response) {
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

    // External prompt & voice events
    useEffect(() => {
        const onExternalPrompt = (event) => {
            const incoming = event?.detail?.prompt;
            if (!incoming) return;
            submitPromptRef.current?.(incoming);
        };
        const onToggleVoice = () => {
            if (!chatId || loading) return;
            window.dispatchEvent(new CustomEvent('spidey:audio_stop'));
            if (voiceSession.state !== 'idle') {
                voiceSession.stopSession();
            } else {
                voiceSession.startSession('live', chatId);
            }
        };
        window.addEventListener('spidey:prompt', onExternalPrompt);
        window.addEventListener('spidey:open_live', onToggleVoice);
        window.addEventListener('spidey:open_listen', onToggleVoice);
        return () => {
            window.removeEventListener('spidey:prompt', onExternalPrompt);
            window.removeEventListener('spidey:open_live', onToggleVoice);
            window.removeEventListener('spidey:open_listen', onToggleVoice);
        };
    }, [chatId, loading, voiceSession]);

    const filteredChats = useMemo(() => {
        const q = chatSearch.trim().toLowerCase();
        if (!q) return chats;
        return chats.filter((c) => (c.title || 'New conversation').toLowerCase().includes(q));
    }, [chats, chatSearch]);

    const slashSuggestions = useMemo(() => {
        const trimmed = prompt.trim().toLowerCase();
        if (!trimmed.startsWith('/')) return [];
        return SLASH_COMMANDS.filter((item) => item.cmd.startsWith(trimmed) || item.label.toLowerCase().includes(trimmed.slice(1)));
    }, [prompt]);

    const isHero = !activeSection && !orbitMode && messages.length === 0 && !loading;

    const brainState = brain?.brainState || 'idle';
    const voiceCaption = useMemo(() => {
        if (spacePttHeld || (voiceSession.state === 'listening' && voiceSession.mode === 'ptt')) {
            return 'Listening... release Space to send';
        }
        if (voiceSession.state === 'listening') return 'Listening live... speak anytime';
        if (voiceSession.state === 'transcribing') return 'Transcribing voice...';
        if (voiceSession.state === 'thinking' || brainState === 'thinking') return 'Thinking...';
        if (brainState === 'streaming') return 'Streaming response...';
        if (voiceSession.state === 'speaking' || voice.isSpeaking) return 'Speaking...';
        return 'Hold Space to talk · or type below';
    }, [spacePttHeld, voiceSession.state, voiceSession.mode, brainState, voice.isSpeaking]);

    const handleSendSubmit = (e) => {
        e.preventDefault();
        submitPrompt(prompt);
    };

    const handleComposerKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (slashSuggestions.length === 1 && prompt.trim().startsWith('/')) {
                setPrompt('');
                openSection(slashSuggestions[0].section);
                return;
            }
            submitPrompt(prompt);
        }
    };

    return (
        <div className={`app-theme-${theme} relative flex h-dvh w-screen overflow-hidden bg-[#111111] text-[#F2EFE9] font-sans`}>
            <div aria-hidden="true" className="spidey-paper-grain" />

            {/* Mobile backdrop when left drawer is open */}
            <AnimatePresence>
                {sidebarOpen && (
                    <motion.button
                        type="button"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={() => setSidebarOpen(false)}
                        aria-label="Close sidebar"
                        className="fixed inset-0 z-30 bg-black/65 backdrop-blur-[2px] lg:hidden"
                    />
                )}
            </AnimatePresence>

            {/* Collapsible Minimal Left Sidebar (Hedwig-style dark rail) */}
            <aside
                className={`fixed inset-y-0 left-0 z-40 flex w-[256px] shrink-0 flex-col border-r border-[#F2EFE9]/10 bg-[#0E0E0E]/95 backdrop-blur-xl transition-transform duration-200 lg:static lg:z-20 ${
                    sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:hidden'
                }`}
            >
                {/* Brand + Collapse */}
                <div className="flex items-center justify-between gap-2 border-b border-[#F2EFE9]/10 px-4 py-3.5">
                    <button
                        type="button"
                        onClick={() => {
                            setOrbitMode(false);
                            openSection(null);
                        }}
                        className="flex min-w-0 items-center gap-2.5 text-left"
                    >
                        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-[#F2EFE9]/15 bg-[#151515]">
                            <SpiderMark size={24} state={brainState} animateEntrance={false} />
                        </div>
                        <div className="min-w-0">
                            <span className="block truncate text-xs font-bold tracking-[0.22em] text-[#F2EFE9]">
                                S.P.I.D.E.Y
                            </span>
                            <span className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.14em] text-[#9C968E]">
                                <span className={`h-1.5 w-1.5 rounded-full ${online ? 'bg-[#D95D24]' : 'bg-[#9C968E]/40'}`} />
                                {online ? 'Neural Ready' : 'Connecting'}
                            </span>
                        </div>
                    </button>
                    <button
                        type="button"
                        onClick={() => setSidebarOpen(false)}
                        className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-[#F2EFE9]/10 bg-[#151515] text-[#9C968E] hover:border-[#D95D24]/60 hover:text-[#F2EFE9]"
                        title="Collapse sidebar"
                        aria-label="Collapse sidebar"
                    >
                        <PanelLeftClose size={14} />
                    </button>
                </div>

                {/* New Chat + Search */}
                <div className="space-y-2 border-b border-[#F2EFE9]/10 p-3">
                    <button
                        type="button"
                        onClick={startChat}
                        className="flex w-full items-center justify-center gap-2 rounded-xl border border-[#D95D24]/50 bg-[#D95D24]/15 px-3 py-2 text-xs font-semibold text-[#F2EFE9] transition-colors hover:border-[#D95D24] hover:bg-[#D95D24] hover:text-[#111111]"
                    >
                        <MessageSquarePlus size={14} />
                        <span>New Chat</span>
                    </button>
                    <div className="relative">
                        <Search size={12} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9C968E]/70" />
                        <input
                            type="text"
                            value={chatSearch}
                            onChange={(e) => setChatSearch(e.target.value)}
                            placeholder="Filter chats..."
                            className="w-full rounded-lg border border-[#F2EFE9]/10 bg-[#141414] py-1.5 pl-7 pr-2.5 text-xs text-[#F2EFE9] outline-none placeholder:text-[#9C968E]/60 focus:border-[#D95D24]/60"
                        />
                    </div>
                </div>

                {/* Chat History */}
                <div className="min-h-0 flex-1 overflow-y-auto px-2.5 py-2">
                    <div className="mb-1.5 px-2 font-mono text-[9px] font-semibold uppercase tracking-[0.18em] text-[#9C968E]/70">
                        Conversations
                    </div>
                    <div className="space-y-0.5">
                        {filteredChats.map((chat) => {
                            const isActive = chat.id === chatId && !activeSection && !orbitMode;
                            const confirming = confirmingId === chat.id;
                            return (
                                <div
                                    key={chat.id}
                                    className={`group flex items-center gap-1 rounded-lg border transition-colors ${
                                        isActive
                                            ? 'border-[#D95D24]/45 bg-[#1B1511]'
                                            : 'border-transparent hover:bg-[#161616]'
                                    }`}
                                >
                                    <button
                                        type="button"
                                        onClick={() => selectChat(chat.id)}
                                        className={`min-w-0 flex-1 px-2.5 py-2 text-left ${
                                            isActive ? 'text-[#F2EFE9]' : 'text-[#9C968E] hover:text-[#F2EFE9]'
                                        }`}
                                    >
                                        <span className="flex items-center gap-1.5">
                                            <span className="block truncate text-xs font-medium">
                                                {chat.title || 'New conversation'}
                                            </span>
                                            {chat.id === chatId && (
                                                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#D95D24]" />
                                            )}
                                        </span>
                                        <span className="mt-0.5 block font-mono text-[9px] text-[#9C968E]/60">
                                            {formatWhen(chat.updated_at)}
                                        </span>
                                    </button>
                                    {confirming ? (
                                        <div className="flex shrink-0 items-center gap-1 pr-1.5">
                                            <button
                                                type="button"
                                                onClick={() => deleteChat(chat.id)}
                                                className="grid h-6 w-6 place-items-center rounded border border-[#D95D24] bg-[#D95D24] text-[#111111]"
                                                title="Confirm delete"
                                            >
                                                <Check size={12} />
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => setConfirmingId('')}
                                                className="grid h-6 w-6 place-items-center rounded border border-[#F2EFE9]/15 bg-[#111111] text-[#9C968E]"
                                                title="Cancel"
                                            >
                                                <X size={12} />
                                            </button>
                                        </div>
                                    ) : (
                                        <button
                                            type="button"
                                            onClick={() => setConfirmingId(chat.id)}
                                            className="mr-1 grid h-6 w-6 shrink-0 place-items-center rounded text-[#9C968E] opacity-0 transition-opacity hover:text-[#D95D24] group-hover:opacity-100 focus-visible:opacity-100"
                                            title="Delete chat"
                                            aria-label={`Delete ${chat.title || 'conversation'}`}
                                        >
                                            <Trash2 size={12} />
                                        </button>
                                    )}
                                </div>
                            );
                        })}
                        {!filteredChats.length && (
                            <p className="px-2 py-4 text-center font-mono text-[10px] text-[#9C968E]/70">
                                No matching chats.
                            </p>
                        )}
                    </div>
                </div>

                {/* User Footer */}
                <div className="flex items-center justify-between gap-2 border-t border-[#F2EFE9]/10 px-3.5 py-3">
                    <div className="flex min-w-0 items-center gap-2.5">
                        <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-[#D95D24]/40 bg-[#1B1511] font-mono text-[10px] font-bold text-[#E07A48]">
                            {(currentUser?.displayName || 'S').slice(0, 1).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                            <p className="truncate text-xs font-medium text-[#F2EFE9]">
                                {currentUser?.displayName || 'Shadow Hunter'}
                            </p>
                            <p className="truncate font-mono text-[9px] uppercase tracking-[0.12em] text-[#9C968E]">
                                Local Runtime
                            </p>
                        </div>
                    </div>
                    <button
                        type="button"
                        onClick={() => openSection(activeSection === 'settings' ? null : 'settings')}
                        className="grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-[#F2EFE9]/10 bg-[#151515] text-[#9C968E] hover:border-[#D95D24]/60 hover:text-[#F2EFE9]"
                        title="Settings"
                        aria-label="Open Settings"
                    >
                        <SettingsIcon size={13} />
                    </button>
                </div>
            </aside>

            {/* Single Focused Main Window */}
            <main className="relative z-10 flex min-w-0 flex-1 flex-col overflow-hidden">
                {/* Minimal Clean Top Bar */}
                <header
                    data-spidey-anchor="navbar"
                    className="flex shrink-0 items-center justify-between gap-2 border-b border-[#F2EFE9]/8 bg-[#111111]/85 px-3 py-2.5 backdrop-blur-md sm:px-5"
                >
                    <div className="flex min-w-0 items-center gap-2">
                        {!sidebarOpen && (
                            <button
                                type="button"
                                onClick={() => setSidebarOpen(true)}
                                className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-[#F2EFE9]/12 bg-[#161616] text-[#9C968E] hover:border-[#D95D24]/60 hover:text-[#F2EFE9]"
                                title="Open sidebar"
                                aria-label="Open sidebar"
                            >
                                <PanelLeftOpen size={14} />
                            </button>
                        )}

                        {/* Clean Single-Row Section Pill Switcher */}
                        <div className="flex items-center gap-1 overflow-x-auto no-scrollbar">
                            <button
                                type="button"
                                onClick={() => {
                                    setOrbitMode(false);
                                    openSection(null);
                                }}
                                className={`flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                                    !activeSection && !orbitMode
                                        ? 'border-[#D95D24]/60 bg-[#D95D24]/15 text-[#F2EFE9]'
                                        : 'border-transparent text-[#9C968E] hover:border-[#F2EFE9]/12 hover:bg-[#171614] hover:text-[#F2EFE9]'
                                }`}
                            >
                                <MessageSquare size={12} className={!activeSection && !orbitMode ? 'text-[#D95D24]' : ''} />
                                <span>Chat</span>
                            </button>
                            {SECTION_ORDER.map((secId) => {
                                const meta = SECTION_META[secId];
                                const Icon = meta.icon;
                                const isActive = activeSection === secId && !orbitMode;
                                return (
                                    <button
                                        key={secId}
                                        type="button"
                                        onClick={() => openSection(isActive ? null : secId)}
                                        className={`flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                                            isActive
                                                ? 'border-[#D95D24]/60 bg-[#D95D24]/15 text-[#F2EFE9]'
                                                : 'border-transparent text-[#9C968E] hover:border-[#F2EFE9]/12 hover:bg-[#171614] hover:text-[#F2EFE9]'
                                        }`}
                                        title={meta.label}
                                    >
                                        <Icon size={12} className={isActive ? 'text-[#D95D24]' : ''} />
                                        <span className="hidden md:inline">
                                            {secId === 'reminders' ? 'Reminders' : meta.label}
                                        </span>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Minimal Right Controls (Speak, ORBIT007, New Chat) */}
                    <div className="flex shrink-0 items-center gap-1.5">
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
                                setOrbitMode((v) => !v);
                            }}
                            className={`flex items-center gap-1 rounded-lg border px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.1em] transition-colors ${
                                orbitMode
                                    ? 'border-[#D95D24] bg-[#D95D24] text-[#111111]'
                                    : 'border-[#F2EFE9]/12 bg-[#161616] text-[#9C968E] hover:border-[#D95D24]/60 hover:text-[#F2EFE9]'
                            }`}
                            title="Toggle ORBIT007 Live Agent Mode"
                        >
                            <Radio size={11} />
                            <span className="hidden sm:inline">ORBIT007</span>
                        </button>
                        {!sidebarOpen && (
                            <button
                                type="button"
                                onClick={startChat}
                                className="grid h-7 w-7 place-items-center rounded-lg border border-[#F2EFE9]/12 bg-[#161616] text-[#9C968E] hover:border-[#D95D24]/60 hover:text-[#F2EFE9]"
                                title="Start new chat"
                                aria-label="Start new chat"
                            >
                                <MessageSquarePlus size={13} />
                            </button>
                        )}
                    </div>
                </header>

                {/* Dynamic Center Stage */}
                <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
                    {/* 1. Content Region (only takes vertical space when NOT in Hero idle mode) */}
                    {!isHero && (
                        <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-3 pt-3 sm:px-6 sm:pt-4">
                            {orbitMode ? (
                                <div className="mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col overflow-hidden rounded-2xl border border-[#F2EFE9]/12 bg-[#151515]">
                                    <div className="flex items-center justify-between border-b border-[#F2EFE9]/10 px-4 py-2.5">
                                        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-[#D95D24]">
                                            ORBIT007 Live Agent
                                        </span>
                                        <button
                                            type="button"
                                            onClick={() => setOrbitMode(false)}
                                            className="rounded-lg border border-[#F2EFE9]/12 px-2 py-1 font-mono text-[10px] text-[#9C968E] hover:border-[#D95D24] hover:text-[#F2EFE9]"
                                        >
                                            Exit
                                        </button>
                                    </div>
                                    <div className="min-h-0 flex-1">
                                        <OrbitAgentView activeChatId={chatId} />
                                    </div>
                                </div>
                            ) : activeSection ? (
                                <AnimatePresence mode="wait">
                                    <SectionCanvasCard
                                        key={activeSection}
                                        sectionId={activeSection}
                                        onClose={() => openSection(null)}
                                        onAskSpidey={(q) => submitPrompt(q)}
                                    />
                                </AnimatePresence>
                            ) : (
                                /* Focused Centered Chat Stream */
                                <div className="mx-auto min-h-0 w-full max-w-3xl flex-1 space-y-4 overflow-y-auto px-1 pb-4 pt-2 sm:px-2">
                                    {messages.slice(-40).map((item, index) => {
                                        const isUser = item.role === 'user';
                                        return (
                                            <motion.div
                                                key={`${item.role}-${item.id || index}`}
                                                initial={{ opacity: 0, y: 8 }}
                                                animate={{ opacity: 1, y: 0 }}
                                                transition={{ duration: 0.18 }}
                                                className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
                                            >
                                                {!isUser && (
                                                    <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-[#F2EFE9]/12 bg-[#161616]">
                                                        <SpiderMark size={18} state="idle" animateEntrance={false} />
                                                    </div>
                                                )}
                                                <div className={`max-w-[85%] space-y-2 ${isUser ? 'items-end' : 'items-start'}`}>
                                                    <div
                                                        className={`rounded-2xl px-4 py-3 text-[13px] leading-relaxed ${
                                                            item.failed
                                                                ? 'border border-[#D95D24] bg-[#24130D] text-[#F2EFE9]'
                                                                : isUser
                                                                ? 'border border-[#D95D24]/45 bg-[#1D1510] text-[#F2EFE9]'
                                                                : 'border border-[#F2EFE9]/10 bg-[#161616] text-[#F2EFE9]'
                                                        } ${item.pending ? 'opacity-70' : ''}`}
                                                    >
                                                        {!isUser ? (
                                                            <div className="assistant-message">
                                                                <ReactMarkdown>{cleanAssistantText(item.content)}</ReactMarkdown>
                                                                {item.streaming && (
                                                                    <span className="ml-1 inline-block h-3.5 w-1.5 rounded-sm bg-[#D95D24] align-middle animate-pulse" />
                                                                )}
                                                            </div>
                                                        ) : (
                                                            <span className="whitespace-pre-wrap">{item.content}</span>
                                                        )}
                                                        {item.failed && (
                                                            <p className="mt-1.5 font-mono text-[10px] text-[#D95D24]">
                                                                Not sent — try again
                                                            </p>
                                                        )}
                                                    </div>

                                                    {/* Quick contextual section opener chips when AI touched a module */}
                                                    {!isUser && Array.isArray(item.relatedSections) && item.relatedSections.length > 0 && (
                                                        <div className="flex flex-wrap gap-1.5">
                                                            {item.relatedSections.map((secKey) => {
                                                                const secMeta = SECTION_META[secKey];
                                                                if (!secMeta) return null;
                                                                const SecIcon = secMeta.icon;
                                                                return (
                                                                    <button
                                                                        key={secKey}
                                                                        type="button"
                                                                        onClick={() => openSection(secKey)}
                                                                        className="inline-flex items-center gap-1.5 rounded-full border border-[#D95D24]/35 bg-[#1A1410] px-2.5 py-1 font-mono text-[10px] text-[#E07A48] transition-colors hover:border-[#D95D24] hover:bg-[#D95D24]/20 hover:text-[#F2EFE9]"
                                                                    >
                                                                        <SecIcon size={11} />
                                                                        <span>Open {secMeta.label}</span>
                                                                    </button>
                                                                );
                                                            })}
                                                        </div>
                                                    )}
                                                </div>
                                            </motion.div>
                                        );
                                    })}

                                    {loading && !messages.some((m) => m.streaming) && (
                                        <div className="flex items-center gap-3">
                                            <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-[#D95D24]/30 bg-[#161616]">
                                                <SpiderMark size={18} state="thinking" animateEntrance={false} />
                                            </div>
                                            <div className="flex items-center gap-2 rounded-2xl border border-[#F2EFE9]/10 bg-[#161616] px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[#D95D24]">
                                                <span className="h-1.5 w-1.5 rounded-full bg-[#D95D24] animate-pulse" />
                                                <span>S.P.I.D.E.Y thinking...</span>
                                            </div>
                                        </div>
                                    )}
                                    <div ref={conversationEndRef} />
                                </div>
                            )}
                        </div>
                    )}

                    {/* 2. Single Persistent Unified 3D Core (Hero Center when idle -> Compact Floating Dock above composer when active) */}
                    {!orbitMode && (
                        <div
                            className={`flex flex-col items-center justify-center transition-all duration-300 ${
                                isHero ? 'flex-1 px-4 py-6' : 'shrink-0 px-4 pt-2 pb-1'
                            }`}
                        >
                            {/* Hero Brand Header (only in idle hero state — exact Hedwig calm aesthetic) */}
                            {isHero && (
                                <motion.div
                                    initial={{ opacity: 0, y: -8 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="mb-2 flex flex-col items-center text-center"
                                >
                                    <div className="flex items-center gap-2.5">
                                        <SpiderMark size={30} state={brainState} />
                                        <h1 className="text-2xl font-semibold tracking-[0.22em] text-[#F2EFE9] sm:text-3xl">
                                            S.P.I.D.E.Y
                                        </h1>
                                    </div>
                                    <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.24em] text-[#9C968E]">
                                        Neural Focus Workspace
                                    </p>
                                </motion.div>
                            )}

                            {/* Floating Toast Reply when chatting while inside a Section Card */}
                            <AnimatePresence>
                                {!isHero && activeSection && sectionReplyToast && (
                                    <motion.div
                                        initial={{ opacity: 0, y: 8 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: 6 }}
                                        className="mb-2 flex max-w-xl items-start gap-2.5 rounded-xl border border-[#D95D24]/35 bg-[#181412]/95 px-3.5 py-2 text-xs text-[#F2EFE9] shadow-lg backdrop-blur-md"
                                    >
                                        <Sparkles size={13} className="mt-0.5 shrink-0 text-[#D95D24]" />
                                        <p className="line-clamp-2 flex-1 leading-relaxed">{sectionReplyToast}</p>
                                        <button
                                            type="button"
                                            onClick={() => setSectionReplyToast(null)}
                                            className="text-[#9C968E] hover:text-[#F2EFE9]"
                                            aria-label="Dismiss reply preview"
                                        >
                                            <X size={12} />
                                        </button>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            {/* The ONE persistent 3D Spidey + Neural Link Core */}
                            <div
                                className={`relative flex items-center justify-center transition-all duration-300 ${
                                    isHero
                                        ? 'flex-col'
                                        : 'flex-row gap-3'
                                }`}
                            >
                                <div
                                    className={`relative rounded-full transition-all duration-300 ease-out ${
                                        isHero
                                            ? 'h-[260px] w-[260px] sm:h-[310px] sm:w-[310px]'
                                            : 'h-[66px] w-[66px]'
                                    } ${
                                        isVoiceActive || brainState === 'listening'
                                            ? 'ring-1 ring-[#D95D24]/50 shadow-[0_0_40px_rgba(217,93,36,0.22)]'
                                            : ''
                                    }`}
                                >
                                    <SpideyNeuralCoreCanvas
                                        variant={isHero ? 'hero' : 'docked'}
                                        className="h-full w-full"
                                        onClick={() => {
                                            brain?.triggerPulse?.(1.3);
                                            if (voiceSession.state !== 'idle') {
                                                voiceSession.stopSession();
                                            }
                                        }}
                                    />
                                </div>

                                {/* Voice / Neural Status Caption */}
                                <div className={isHero ? 'mt-2 text-center' : 'max-w-[260px] text-left sm:max-w-md'}>
                                    <p
                                        className={`font-mono text-[11px] transition-colors ${
                                            spacePttHeld || voiceSession.state !== 'idle' || loading
                                                ? 'text-[#E07A48]'
                                                : 'text-[#9C968E]/80'
                                        }`}
                                    >
                                        {voiceSession.transcript && voiceSession.state !== 'idle'
                                            ? `“${voiceSession.transcript}”`
                                            : voiceCaption}
                                    </p>
                                </div>
                            </div>

                            {/* Hero Starter Prompts (clean minimal pills) */}
                            {isHero && (
                                <div className="mt-5 flex max-w-xl flex-wrap items-center justify-center gap-2">
                                    {STARTER_PROMPTS.map((starter) => (
                                        <button
                                            key={starter.label}
                                            type="button"
                                            onClick={() => submitPrompt(starter.label)}
                                            disabled={loading || !chatId}
                                            className="rounded-full border border-[#F2EFE9]/12 bg-[#161616]/90 px-3.5 py-1.5 text-xs text-[#D5CFC6] transition-all hover:border-[#D95D24]/70 hover:bg-[#1E1612] hover:text-[#F2EFE9] disabled:opacity-40"
                                        >
                                            {starter.label}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* 3. Bottom Floating Composer Bar */}
                    {!orbitMode && (
                        <div className="relative shrink-0 px-3 pb-3 pt-1 sm:px-6 sm:pb-5">
                            <div className="relative mx-auto w-full max-w-2xl">
                                {/* Slash Command Popover */}
                                <AnimatePresence>
                                    {slashSuggestions.length > 0 && (
                                        <motion.div
                                            initial={{ opacity: 0, y: 6 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            exit={{ opacity: 0, y: 4 }}
                                            className="absolute bottom-full left-0 right-0 mb-2 overflow-hidden rounded-xl border border-[#F2EFE9]/14 bg-[#161616]/98 p-1.5 shadow-2xl backdrop-blur-xl"
                                        >
                                            {slashSuggestions.map((item) => (
                                                <button
                                                    key={item.cmd}
                                                    type="button"
                                                    onClick={() => {
                                                        setPrompt('');
                                                        openSection(item.section);
                                                        textareaRef.current?.focus();
                                                    }}
                                                    className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs transition-colors hover:bg-[#D95D24]/15"
                                                >
                                                    <span className="font-mono font-semibold text-[#E07A48]">{item.cmd}</span>
                                                    <span className="text-[#9C968E]">{item.desc}</span>
                                                </button>
                                            ))}
                                        </motion.div>
                                    )}
                                </AnimatePresence>

                                <form
                                    data-spidey-anchor="composer"
                                    onSubmit={handleSendSubmit}
                                    className="flex items-end gap-2 rounded-2xl border border-[#F2EFE9]/14 bg-[#161616]/95 p-2 shadow-[0_12px_40px_rgba(0,0,0,0.45)] backdrop-blur-xl transition-colors focus-within:border-[#D95D24]/70"
                                >
                                    <textarea
                                        ref={textareaRef}
                                        value={prompt}
                                        onChange={(e) => setPrompt(e.target.value)}
                                        onKeyDown={handleComposerKeyDown}
                                        rows={1}
                                        maxLength={2000}
                                        placeholder={
                                            activeSection
                                                ? `Ask S.P.I.D.E.Y about ${SECTION_META[activeSection]?.label || 'this'} or type /chat...`
                                                : 'Ask S.P.I.D.E.Y anything... or type /tasks, /habits'
                                        }
                                        className="max-h-28 min-h-[38px] flex-1 resize-none bg-transparent px-3 py-2 text-[13px] leading-relaxed text-[#F2EFE9] outline-none placeholder:text-[#9C968E]/60"
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
                                        className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-[#D95D24] bg-[#D95D24] text-[#111111] transition-colors hover:bg-[#C44E19] disabled:opacity-35"
                                        aria-label="Send message"
                                    >
                                        <Send size={15} />
                                    </button>
                                </form>

                                {(error || voiceSession.error) && (
                                    <p className="mt-2 px-2 text-center text-xs text-[#D95D24]">
                                        {error || voiceSession.error}
                                    </p>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </main>

            {/* Free-Roaming 3D Spidey Companion (crawls on composer, hangs on navbar, animates while speaking) */}
            <SpideyRoamerOverlay />
        </div>
    );
}
