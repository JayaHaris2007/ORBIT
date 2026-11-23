import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { apiRequest } from '../services/api';
import { useAppData } from '../context/AppDataContext';

const ACTIVE_CHAT_KEY = 'spidey_active_chat_id';
const LEGACY_ACTIVE_CHAT_KEY = 'jarvis_active_chat_id';

const byRunAt = (a, b) => new Date(a.run_at) - new Date(b.run_at);

const RemindersMemory = () => {
    const { revision } = useAppData();
    const [reminders, setReminders] = useState([]);
    const [memories, setMemories] = useState([]);
    const [reminderText, setReminderText] = useState('');
    const [reminderAt, setReminderAt] = useState('');
    const [memoryText, setMemoryText] = useState('');
    const [chatId, setChatId] = useState('');
    const [loading, setLoading] = useState(true);
    const [showCompleted, setShowCompleted] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            try {
                const reminderUrl = showCompleted ? '/api/reminders?include_completed=true' : '/api/reminders';
                const [chatData, reminderData, memoryData] = await Promise.all([
                    apiRequest('/api/chats'),
                    apiRequest(reminderUrl),
                    apiRequest('/api/memories'),
                ]);
                if (cancelled) return;
                const savedChatId = localStorage.getItem(ACTIVE_CHAT_KEY) || localStorage.getItem(LEGACY_ACTIVE_CHAT_KEY);
                const chat = chatData.chats.find((item) => item.id === savedChatId) || chatData.chats[0];
                setChatId(chat?.id || '');
                setReminders([...(reminderData.reminders || [])].sort(byRunAt));
                setMemories(memoryData.memories || []);
            } catch (requestError) {
                if (!cancelled) setError(requestError.message);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        load();
        const onAlert = () => { load(); };
        window.addEventListener('orbit:reminder_alert', onAlert);
        const pollInterval = setInterval(load, 15000);
        return () => {
            cancelled = true;
            window.removeEventListener('orbit:reminder_alert', onAlert);
            clearInterval(pollInterval);
        };
    }, [revision, showCompleted]);

    const addReminder = async (event) => {
        event.preventDefault();
        if (!reminderText.trim() || !reminderAt) return;
        try {
            const reminder = await apiRequest('/api/reminders', {
                method: 'POST',
                body: JSON.stringify({
                    text: reminderText.trim(),
                    run_at: new Date(reminderAt).toISOString(),
                    chat_id: chatId || undefined,
                }),
            });
            setReminders((current) => [...current, reminder].sort(byRunAt));
            setReminderText('');
            setReminderAt('');
            setError('');
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const undoReminder = async (id) => {
        try {
            setError('');
            await apiRequest(`/api/reminders/${id}`, {
                method: 'PATCH',
                body: JSON.stringify({ completed: false }),
            });
            const reminderUrl = showCompleted ? '/api/reminders?include_completed=true' : '/api/reminders';
            const reminderData = await apiRequest(reminderUrl);
            setReminders([...(reminderData.reminders || [])].sort(byRunAt));
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const cancelReminder = async (id) => {
        try {
            await apiRequest(`/api/reminders/${id}`, { method: 'DELETE' });
            setReminders((current) => current.filter((item) => item.id !== id));
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const addMemory = async (event) => {
        event.preventDefault();
        if (!memoryText.trim()) return;
        try {
            const item = await apiRequest('/api/memories', {
                method: 'POST',
                body: JSON.stringify({ content: memoryText.trim() }),
            });
            setMemories((current) => [item, ...current]);
            setMemoryText('');
            setError('');
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const removeMemory = async (id) => {
        try {
            await apiRequest(`/api/memories/${id}`, { method: 'DELETE' });
            setMemories((current) => current.filter((item) => item.id !== id));
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    if (loading) {
        return (
            <div className="py-16 text-center font-mono text-xs uppercase tracking-[0.18em] text-[#8E867D]">
                // loading recall index...
            </div>
        );
    }

    return (
        <div className="mx-auto max-w-6xl space-y-6 pb-12">
            <header className="flex flex-wrap items-end justify-between gap-4 border-b border-[#F2EFE9]/14 pb-4">
                <div>
                    <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#D95D24]">
                        03 // recall_and_schedule
                    </span>
                    <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[#F2EFE9]">
                        Reminders &amp; Memory
                    </h1>
                </div>
                <div className="flex items-center gap-3 font-mono text-[11px] text-[#8E867D]">
                    <span>{reminders.filter((r) => !r.completed).length} scheduled</span>
                    <span className="text-[#4F4943]">·</span>
                    <span>{memories.length} memories</span>
                </div>
            </header>

            {error && (
                <div className="border border-[#D95D24] bg-[#1F0F09] px-4 py-2.5 font-mono text-xs text-[#F2EFE9]">
                    // {error}
                </div>
            )}

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                {/* Reminders Ledger */}
                <section className="ascii-frame flex flex-col bg-[#0A0908] p-5">
                    <div className="flex items-center justify-between gap-3 border-b border-[#F2EFE9]/12 pb-3 font-mono">
                        <span className="text-xs font-semibold uppercase tracking-[0.14em] text-[#F2EFE9]">
                            <span className="text-[#D95D24]">//</span> Scheduled Reminders
                        </span>
                        <label className="flex cursor-pointer items-center gap-1.5 text-[10px] uppercase text-[#8E867D] hover:text-[#F2EFE9]">
                            <input
                                type="checkbox"
                                checked={showCompleted}
                                onChange={(e) => setShowCompleted(e.target.checked)}
                                className="accent-[#D95D24]"
                            />
                            <span>show_done</span>
                        </label>
                    </div>

                    <form onSubmit={addReminder} className="mt-4 space-y-2.5">
                        <input
                            value={reminderText}
                            onChange={(event) => setReminderText(event.target.value)}
                            maxLength={500}
                            placeholder="What should ORBIT remind you about?"
                            className="w-full border border-[#F2EFE9]/14 bg-[#060606] px-3 py-2 text-sm text-[#F2EFE9] placeholder:text-[#5C564F] focus:border-[#D95D24] focus:outline-none"
                        />
                        <div className="flex gap-2">
                            <input
                                type="datetime-local"
                                value={reminderAt}
                                onChange={(event) => setReminderAt(event.target.value)}
                                className="min-w-0 flex-1 border border-[#F2EFE9]/14 bg-[#060606] px-3 py-2 font-mono text-xs text-[#F2EFE9] [color-scheme:dark] focus:border-[#D95D24] focus:outline-none"
                            />
                            <button
                                type="submit"
                                disabled={!reminderText.trim() || !reminderAt}
                                className="border border-[#D95D24] bg-[#D95D24] px-4 py-2 font-mono text-xs font-semibold uppercase text-[#060606] hover:bg-[#E86B30] disabled:opacity-35"
                            >
                                [+ add]
                            </button>
                        </div>
                    </form>

                    <div className="mt-4 divide-y divide-[#F2EFE9]/10">
                        {reminders.map((reminder) => (
                            <div
                                key={reminder.id}
                                className={`flex items-start justify-between gap-3 py-3 ${reminder.completed ? 'opacity-55' : ''}`}
                            >
                                <div className="min-w-0 flex-1">
                                    <p className={`text-sm ${reminder.completed ? 'line-through text-[#7D756C]' : 'text-[#F2EFE9]'}`}>
                                        {reminder.text}
                                    </p>
                                    <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.1em] text-[#8E867D]">
                                        {format(new Date(reminder.run_at), 'MMM d · h:mm a')}
                                        {reminder.recurrence ? ` · ${reminder.recurrence}` : ''}
                                    </p>
                                </div>
                                <div className="flex shrink-0 items-center gap-1.5 font-mono text-[10px] uppercase">
                                    {Boolean(reminder.completed) && (
                                        <button
                                            type="button"
                                            onClick={() => undoReminder(reminder.id)}
                                            className="border border-[#D95D24]/45 px-2 py-0.5 text-[#E87D42] hover:bg-[#D95D24] hover:text-[#060606]"
                                        >
                                            [undo]
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        onClick={() => cancelReminder(reminder.id)}
                                        className="px-1.5 py-0.5 text-[#8E867D] hover:text-[#D95D24]"
                                        aria-label={`Cancel reminder ${reminder.text}`}
                                    >
                                        [rm]
                                    </button>
                                </div>
                            </div>
                        ))}
                        {!reminders.length && (
                            <p className="py-8 text-center font-mono text-xs text-[#6E675F]">
                                // no reminders scheduled
                            </p>
                        )}
                    </div>
                </section>

                {/* Semantic Memory Store */}
                <section className="ascii-frame flex flex-col bg-[#0A0908] p-5">
                    <div className="flex items-center justify-between gap-3 border-b border-[#F2EFE9]/12 pb-3 font-mono">
                        <span className="text-xs font-semibold uppercase tracking-[0.14em] text-[#F2EFE9]">
                            <span className="text-[#D95D24]">//</span> Long-Term Memory
                        </span>
                        <span className="text-[10px] uppercase text-[#8E867D]">local sqlite</span>
                    </div>

                    <form onSubmit={addMemory} className="mt-4 flex gap-2">
                        <input
                            value={memoryText}
                            onChange={(event) => setMemoryText(event.target.value)}
                            maxLength={500}
                            placeholder="Store a fact or preference..."
                            className="min-w-0 flex-1 border border-[#F2EFE9]/14 bg-[#060606] px-3 py-2 text-sm text-[#F2EFE9] placeholder:text-[#5C564F] focus:border-[#D95D24] focus:outline-none"
                        />
                        <button
                            type="submit"
                            disabled={!memoryText.trim()}
                            className="border border-[#D95D24] bg-[#D95D24] px-4 py-2 font-mono text-xs font-semibold uppercase text-[#060606] hover:bg-[#E86B30] disabled:opacity-35"
                        >
                            [save]
                        </button>
                    </form>

                    <div className="mt-4 divide-y divide-[#F2EFE9]/10">
                        {memories.map((item, idx) => (
                            <div key={item.id} className="flex items-start gap-3 py-3">
                                <span className="mt-0.5 shrink-0 font-mono text-[10px] text-[#5C564F]">
                                    {String(idx + 1).padStart(2, '0')}
                                </span>
                                <p className="min-w-0 flex-1 text-sm leading-relaxed text-[#E5E0D8]">
                                    {item.content}
                                </p>
                                <button
                                    type="button"
                                    onClick={() => removeMemory(item.id)}
                                    className="shrink-0 font-mono text-[10px] uppercase text-[#8E867D] hover:text-[#D95D24]"
                                    aria-label={`Delete memory ${item.content}`}
                                >
                                    [rm]
                                </button>
                            </div>
                        ))}
                        {!memories.length && (
                            <p className="py-8 text-center font-mono text-xs text-[#6E675F]">
                                // memory bank empty
                            </p>
                        )}
                    </div>
                </section>
            </div>
        </div>
    );
};

export default RemindersMemory;
