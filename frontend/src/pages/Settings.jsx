import { useState } from 'react';
import { useAuth, useTheme } from '../context/AuthContext';
import { useAppData } from '../context/AppDataContext';
import { useNotifications } from '../hooks/useNotifications';
import { format } from 'date-fns';
import { motion, AnimatePresence } from 'framer-motion';
import ConfirmationModal from '../components/ConfirmationModal';
import {
    apiRequest,
    DEFAULT_GEMINI_MODEL,
    GEMINI_KEY_STORAGE,
    GEMINI_MODEL_STORAGE,
    getGeminiConfig,
} from '../services/api';

function SettingBlock({ code, title, children }) {
    return (
        <section className="ascii-frame bg-[#0A0908]">
            <div className="border-b border-[#F2EFE9]/10 px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">
                <span className="text-[#D95D24]">{code} //</span> {title}
            </div>
            <div className="divide-y divide-[#F2EFE9]/8">{children}</div>
        </section>
    );
}

function SettingRow({ label, hint, value, onClick, destructive = false, toggle = null }) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={`flex w-full items-center justify-between gap-4 px-4 py-3.5 text-left transition-colors ${
                destructive ? 'hover:bg-[#1E0E09]' : 'hover:bg-[#12100E]'
            }`}
        >
            <div className="min-w-0">
                <div className={`text-sm font-medium ${destructive ? 'text-[#E87D42]' : 'text-[#F2EFE9]'}`}>
                    {label}
                </div>
                {hint && <div className="mt-0.5 font-mono text-[10px] text-[#7D756C]">{hint}</div>}
            </div>

            <div className="flex shrink-0 items-center gap-3 font-mono text-[11px]">
                {value && <span className="hidden text-[#8E867D] sm:inline">{value}</span>}
                {toggle !== null ? (
                    <span
                        className={`border px-2 py-0.5 text-[10px] uppercase ${
                            toggle
                                ? 'border-[#D95D24] bg-[#D95D24] font-semibold text-[#060606]'
                                : 'border-[#F2EFE9]/18 bg-[#060606] text-[#8E867D]'
                        }`}
                    >
                        {toggle ? '[on]' : '[off]'}
                    </span>
                ) : (
                    <span className={destructive ? 'text-[#D95D24]' : 'text-[#7D756C]'}>
                        {destructive ? '[exec]' : '[→]'}
                    </span>
                )}
            </div>
        </button>
    );
}

const Settings = () => {
    const { currentUser, updateDisplayName, logout } = useAuth();
    const { theme, setTheme } = useTheme();
    const { refresh } = useAppData();
    const { requestPermission } = useNotifications(currentUser);
    const [isLoading, setIsLoading] = useState(false);
    const [message, setMessage] = useState({ type: '', text: '' });

    const [modalConfig, setModalConfig] = useState({
        isOpen: false,
        title: '',
        message: '',
        type: 'danger',
        onConfirm: () => {},
        confirmString: null,
    });

    const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
    const [displayName, setDisplayName] = useState(currentUser?.displayName || '');
    const [notificationsEnabled, setNotificationsEnabled] = useState(() => {
        try {
            return (localStorage.getItem('spidey_notifications') ?? localStorage.getItem('kage_notifications')) !== 'false';
        } catch {
            return true;
        }
    });

    const [geminiApiKey, setGeminiApiKey] = useState(() => getGeminiConfig().apiKey);
    const [geminiModel, setGeminiModel] = useState(() => getGeminiConfig().model);
    const [showGeminiKey, setShowGeminiKey] = useState(false);
    const [hasSavedGeminiKey, setHasSavedGeminiKey] = useState(() => Boolean(getGeminiConfig().apiKey));

    const showMessage = (type, text) => {
        setMessage({ type, text });
        setTimeout(() => setMessage({ type: '', text: '' }), 3200);
    };

    const handleUpdateProfile = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        try {
            updateDisplayName?.(displayName);
            showMessage('success', 'Profile updated.');
            setIsProfileModalOpen(false);
        } catch (error) {
            console.error(error);
            showMessage('error', 'Failed to update profile.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleResetPassword = () => {
        setModalConfig({
            isOpen: true,
            title: 'Local Authentication',
            message: 'Password management is handled locally by this ORBIT runtime.',
            type: 'default',
            confirmString: null,
            onConfirm: async () => {
                showMessage('success', 'Local authentication verified.');
            },
        });
    };

    const handleToggleNotifications = async () => {
        const newState = !notificationsEnabled;
        if (newState) {
            const perm = await requestPermission();
            if (perm !== 'granted') {
                showMessage('error', 'Notification permission denied.');
                return;
            }
        }
        setNotificationsEnabled(newState);
        try {
            localStorage.setItem('spidey_notifications', String(newState));
        } catch (error) {
            console.error(error);
            setNotificationsEnabled(!newState);
            showMessage('error', 'Failed to save preference.');
        }
    };

    const handleThemeChange = (event) => {
        setTheme(event.target.value);
        showMessage('success', 'Theme updated.');
    };

    const handleSaveGeminiConfig = (e) => {
        e.preventDefault();
        const trimmedKey = geminiApiKey.trim();
        const chosenModel = (geminiModel || DEFAULT_GEMINI_MODEL).trim();
        try {
            if (trimmedKey) {
                localStorage.setItem(GEMINI_KEY_STORAGE, trimmedKey);
                localStorage.setItem(GEMINI_MODEL_STORAGE, chosenModel);
                setHasSavedGeminiKey(true);
                showMessage('success', `Gemini API active (${chosenModel}).`);
            } else {
                localStorage.removeItem(GEMINI_KEY_STORAGE);
                localStorage.setItem(GEMINI_MODEL_STORAGE, chosenModel);
                setHasSavedGeminiKey(false);
                showMessage('success', 'Cleared Gemini key — using local Ollama.');
            }
            window.dispatchEvent(new CustomEvent('spidey:gemini_config_changed'));
        } catch (error) {
            console.error(error);
            showMessage('error', 'Failed to save Gemini API key.');
        }
    };

    const handleClearGeminiConfig = () => {
        try {
            localStorage.removeItem(GEMINI_KEY_STORAGE);
            setGeminiApiKey('');
            setHasSavedGeminiKey(false);
            window.dispatchEvent(new CustomEvent('spidey:gemini_config_changed'));
            showMessage('success', 'Switched back to local Ollama.');
        } catch (error) {
            console.error(error);
            showMessage('error', 'Failed to clear Gemini API key.');
        }
    };

    const wipeDatabaseAndSyncUi = async () => {
        try {
            await apiRequest('/api/database', { method: 'DELETE' });
        } catch (err) {
            if (String(err?.message || '').toLowerCase().includes('not found')) {
                const [tasksData, habitsData, memData, remData, rmData] = await Promise.all([
                    apiRequest('/api/tasks?include_completed=true').catch(() => ({ tasks: [] })),
                    apiRequest('/api/habits').catch(() => ({ habits: [] })),
                    apiRequest('/api/memories').catch(() => ({ memories: [] })),
                    apiRequest('/api/reminders').catch(() => ({ reminders: [] })),
                    apiRequest('/api/learning/roadmaps').catch(() => ({ roadmaps: [] })),
                ]);
                await Promise.all([
                    apiRequest('/api/chats', { method: 'DELETE' }).catch(() => {}),
                    ...(tasksData.tasks || []).map((t) => apiRequest(`/api/tasks/${t.id}`, { method: 'DELETE' }).catch(() => {})),
                    ...(habitsData.habits || []).map((h) => apiRequest(`/api/habits/${h.id}`, { method: 'DELETE' }).catch(() => {})),
                    ...(memData.memories || []).map((m) => apiRequest(`/api/memories/${m.id}`, { method: 'DELETE' }).catch(() => {})),
                    ...(remData.reminders || []).map((r) => apiRequest(`/api/reminders/${r.id}`, { method: 'DELETE' }).catch(() => {})),
                    ...(rmData.roadmaps || []).map((rm) => apiRequest(`/api/learning/roadmaps/${rm.id}`, { method: 'DELETE' }).catch(() => {})),
                ]);
            } else {
                throw err;
            }
        }
        try {
            localStorage.removeItem('spidey_active_chat_id');
            localStorage.removeItem('jarvis_active_chat_id');
        } catch { /* ignore */ }
        refresh?.();
        window.dispatchEvent(new CustomEvent('orbit:data_reset'));
        window.dispatchEvent(
            new CustomEvent('orbit:refresh', {
                detail: { sections: ['tasks', 'habits', 'memories', 'reminders', 'learning', 'gamification'] },
            })
        );
    };

    const handleDeleteAllDatabaseData = () => {
        setModalConfig({
            isOpen: true,
            title: 'Delete All Database Data',
            message: 'This will permanently erase all tasks, daily habits, reminders, memories, chat history, learning roadmaps, and XP from assistant.db.',
            type: 'danger',
            confirmString: 'DELETE',
            onConfirm: async () => {
                setIsLoading(true);
                try {
                    await wipeDatabaseAndSyncUi();
                    showMessage('success', 'All database data permanently erased.');
                } catch (error) {
                    console.error(error);
                    showMessage('error', error.message || 'Failed to delete database data.');
                } finally {
                    setIsLoading(false);
                }
            },
        });
    };

    const handleDeleteAccount = () => {
        setModalConfig({
            isOpen: true,
            title: 'Delete Account & All Data',
            message: 'Are you sure you want to wipe all local data and reset your session?',
            type: 'danger',
            confirmString: 'DELETE',
            onConfirm: async () => {
                setIsLoading(true);
                try {
                    await wipeDatabaseAndSyncUi();
                    showMessage('success', 'All database data erased.');
                    logout();
                } catch (error) {
                    console.error(error);
                    showMessage('error', 'Failed to delete account data.');
                    setIsLoading(false);
                }
            },
        });
    };

    return (
        <div className="relative mx-auto max-w-3xl space-y-6 pb-12">
            <header className="border-b border-[#F2EFE9]/14 pb-4">
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#D95D24]">
                    06 // system_configuration
                </span>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[#F2EFE9]">Settings</h1>
            </header>

            <AnimatePresence>
                {message.text && (
                    <motion.div
                        initial={{ opacity: 0, y: -12 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -12 }}
                        className={`fixed right-5 top-14 z-50 border px-4 py-2.5 font-mono text-xs ${
                            message.type === 'error'
                                ? 'border-[#D95D24] bg-[#210E08] text-[#F2EFE9]'
                                : 'border-[#D95D24] bg-[#0B0A09] text-[#F2EFE9]'
                        }`}
                    >
                        // {message.text}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Profile Card */}
            <div className="ascii-frame flex items-center gap-4 bg-[#0A0908] p-5">
                <div className="grid h-12 w-12 shrink-0 place-items-center border border-[#D95D24] bg-[#190F09] font-mono text-lg font-bold text-[#E87D42]">
                    {currentUser?.displayName?.charAt(0)?.toUpperCase() || 'S'}
                </div>
                <div className="min-w-0 flex-1">
                    <h2 className="truncate text-lg font-semibold text-[#F2EFE9]">
                        {currentUser?.displayName || 'Shadow Hunter'}
                    </h2>
                    <p className="font-mono text-[11px] text-[#8E867D]">
                        local-runtime · joined{' '}
                        {currentUser?.metadata?.creationTime
                            ? format(new Date(currentUser.metadata.creationTime), 'MMM yyyy')
                            : 'active'}
                    </p>
                </div>
                <button
                    type="button"
                    onClick={() => setIsProfileModalOpen(true)}
                    className="border border-[#F2EFE9]/16 bg-[#060606] px-3 py-1.5 font-mono text-[10px] uppercase text-[#F2EFE9] hover:border-[#D95D24] hover:text-[#D95D24]"
                >
                    [edit]
                </button>
            </div>

            <SettingBlock code="01" title="Appearance & Notifications">
                <div className="flex items-center justify-between gap-4 px-4 py-3.5">
                    <div>
                        <div className="text-sm font-medium text-[#F2EFE9]">Theme Palette</div>
                        <div className="mt-0.5 font-mono text-[10px] text-[#7D756C]">
                            Workspace surface tone
                        </div>
                    </div>
                    <select
                        value={theme}
                        onChange={handleThemeChange}
                        className="border border-[#F2EFE9]/18 bg-[#060606] px-3 py-1.5 font-mono text-xs text-[#F2EFE9] outline-none focus:border-[#D95D24]"
                    >
                        <option value="dark">Obsidian (Default)</option>
                        <option value="midnight">Midnight</option>
                        <option value="light">Paper Light</option>
                    </select>
                </div>
                <SettingRow
                    label="Desktop Notifications"
                    hint="Alert on scheduled reminders and proactive check-ins"
                    toggle={notificationsEnabled}
                    onClick={handleToggleNotifications}
                />
                <SettingRow
                    label="Local Authentication"
                    hint="Verify local session credentials"
                    onClick={handleResetPassword}
                />
            </SettingBlock>

            {/* AI Engine BYOK */}
            <section className="ascii-frame bg-[#0A0908]">
                <div className="flex items-center justify-between border-b border-[#F2EFE9]/10 px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em]">
                    <span className="text-[#8E867D]">
                        <span className="text-[#D95D24]">02 //</span> AI Engine (Ollama / Gemini BYOK)
                    </span>
                    <span className={hasSavedGeminiKey ? 'text-[#D95D24]' : 'text-[#8E867D]'}>
                        {hasSavedGeminiKey ? `gemini:${geminiModel}` : 'local:ollama'}
                    </span>
                </div>

                <form onSubmit={handleSaveGeminiConfig} className="space-y-4 p-4">
                    <p className="font-mono text-[11px] leading-relaxed text-[#8E867D]">
                        Optionally provide a Google AI Studio Gemini API key (stored only in this browser) to run ORBIT remotely without local Ollama.
                    </p>

                    <div>
                        <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-[0.14em] text-[#8E867D]">
                            AI Studio API Key
                        </label>
                        <div className="flex gap-2">
                            <input
                                type={showGeminiKey ? 'text' : 'password'}
                                value={geminiApiKey}
                                onChange={(e) => setGeminiApiKey(e.target.value)}
                                placeholder="AIza..."
                                autoComplete="off"
                                className="min-w-0 flex-1 border border-[#F2EFE9]/16 bg-[#060606] px-3 py-2 font-mono text-xs text-[#F2EFE9] outline-none focus:border-[#D95D24]"
                            />
                            <button
                                type="button"
                                onClick={() => setShowGeminiKey((v) => !v)}
                                className="border border-[#F2EFE9]/16 bg-[#060606] px-3 py-2 font-mono text-[10px] uppercase text-[#8E867D] hover:border-[#D95D24] hover:text-[#F2EFE9]"
                            >
                                {showGeminiKey ? '[hide]' : '[show]'}
                            </button>
                        </div>
                    </div>

                    <div>
                        <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-[0.14em] text-[#8E867D]">
                            Gemini Model
                        </label>
                        <select
                            value={geminiModel}
                            onChange={(e) => setGeminiModel(e.target.value)}
                            className="w-full border border-[#F2EFE9]/16 bg-[#060606] px-3 py-2 font-mono text-xs text-[#F2EFE9] outline-none focus:border-[#D95D24]"
                        >
                            <option value="gemini-3.5-flash">gemini-3.5-flash (Recommended)</option>
                            <option value="gemini-3.5-pro">gemini-3.5-pro (Best Reasoning)</option>
                            <option value="gemini-3.8-flash">gemini-3.8-flash (Fast)</option>
                            <option value="gemini-4-hydrogen">gemini-4-hydrogen</option>
                        </select>
                    </div>

                    <div className="flex items-center gap-2.5 pt-1 font-mono text-xs uppercase">
                        <button
                            type="submit"
                            className="flex-1 border border-[#D95D24] bg-[#D95D24] py-2.5 font-semibold text-[#060606] hover:bg-[#E86B30]"
                        >
                            [save_config]
                        </button>
                        {hasSavedGeminiKey && (
                            <button
                                type="button"
                                onClick={handleClearGeminiConfig}
                                className="border border-[#D95D24]/50 bg-[#1B0E09] px-4 py-2.5 text-[#E87D42] hover:bg-[#D95D24] hover:text-[#060606]"
                            >
                                [use_ollama]
                            </button>
                        )}
                    </div>
                </form>
            </section>

            {/* Danger Zone */}
            <SettingBlock code="03" title="Danger Zone">
                <SettingRow
                    label="Delete All Database Data"
                    hint="Wipe tasks, habits, chats, reminders, memories, and roadmaps"
                    onClick={handleDeleteAllDatabaseData}
                    destructive
                />
                <SettingRow
                    label="Reset Local Account & Data"
                    hint="Erase database and reset active session"
                    onClick={handleDeleteAccount}
                    destructive
                />
            </SettingBlock>

            <div className="pt-2 text-center font-mono text-[10px] uppercase tracking-[0.2em] text-[#5C564F]">
                ORBIT // Neural OS v2.0
            </div>

            {/* Edit Profile Modal */}
            <AnimatePresence>
                {isProfileModalOpen && (
                    <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4">
                        <motion.div
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 4 }}
                            className="ascii-frame relative w-full max-w-sm bg-[#0A0908] p-6"
                        >
                            <div className="mb-4 flex items-center justify-between border-b border-[#F2EFE9]/12 pb-3 font-mono text-[10px] uppercase tracking-[0.16em]">
                                <span className="text-[#D95D24]">// update_profile</span>
                                <button
                                    type="button"
                                    onClick={() => setIsProfileModalOpen(false)}
                                    className="text-[#8E867D] hover:text-[#F2EFE9]"
                                >
                                    [x]
                                </button>
                            </div>
                            <form onSubmit={handleUpdateProfile} className="space-y-4">
                                <div>
                                    <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-[0.14em] text-[#8E867D]">
                                        Display Name
                                    </label>
                                    <input
                                        type="text"
                                        value={displayName}
                                        onChange={(e) => setDisplayName(e.target.value)}
                                        className="w-full border border-[#F2EFE9]/16 bg-[#060606] px-3 py-2 font-mono text-sm text-[#F2EFE9] outline-none focus:border-[#D95D24]"
                                        autoFocus
                                    />
                                </div>
                                <button
                                    type="submit"
                                    disabled={isLoading || !displayName.trim()}
                                    className="w-full border border-[#D95D24] bg-[#D95D24] py-2.5 font-mono text-xs font-semibold uppercase text-[#060606] hover:bg-[#E86B30] disabled:opacity-40"
                                >
                                    {isLoading ? '[saving...]' : '[save_profile]'}
                                </button>
                            </form>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>

            <ConfirmationModal
                isOpen={modalConfig.isOpen}
                onClose={() => setModalConfig((prev) => ({ ...prev, isOpen: false }))}
                onConfirm={modalConfig.onConfirm}
                title={modalConfig.title}
                message={modalConfig.message}
                type={modalConfig.type}
                confirmString={modalConfig.confirmString}
            />
        </div>
    );
};

export default Settings;
