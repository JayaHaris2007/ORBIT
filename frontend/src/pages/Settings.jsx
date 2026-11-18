import { useState, useEffect } from 'react';
import { useAuth, useTheme } from '../context/AuthContext';
import { useAppData } from '../context/AppDataContext';
import { useNotifications } from '../hooks/useNotifications';
import { User, Bell, Shield, LogOut, ChevronRight, X, AlertTriangle, Save, Loader, Key, Eye, EyeOff, Trash2, Database } from 'lucide-react';
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

const Settings = () => {
    const { currentUser, logout } = useAuth();
    const { theme, setTheme } = useTheme();
    const { refresh } = useAppData();
    const { requestPermission } = useNotifications(currentUser);
    const [isLoading, setIsLoading] = useState(false);
    const [message, setMessage] = useState({ type: '', text: '' });

    // Modal Config
    const [modalConfig, setModalConfig] = useState({
        isOpen: false,
        title: '',
        message: '',
        type: 'danger',
        onConfirm: () => { },
        confirmString: null
    });

    // Profile State
    const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
    const [displayName, setDisplayName] = useState(currentUser?.displayName || '');

    // Preferences State
    const [notificationsEnabled, setNotificationsEnabled] = useState(true);

    // AI Studio Gemini API Key State (BYOK)
    const [geminiApiKey, setGeminiApiKey] = useState(() => getGeminiConfig().apiKey);
    const [geminiModel, setGeminiModel] = useState(() => getGeminiConfig().model);
    const [showGeminiKey, setShowGeminiKey] = useState(false);
    const [hasSavedGeminiKey, setHasSavedGeminiKey] = useState(() => Boolean(getGeminiConfig().apiKey));

    // Initial Fetch for Preferences
    useEffect(() => {
        const fetchPreferences = async () => {
            if (currentUser) {
                try {
                    setNotificationsEnabled(
                        (localStorage.getItem('spidey_notifications')
                            ?? localStorage.getItem('kage_notifications')) !== 'false'
                    );
                } catch (error) {
                    console.error("Error fetching settings:", error);
                }
            }
        };
        fetchPreferences();
    }, [currentUser]);

    const showMessage = (type, text) => {
        setMessage({ type, text });
        setTimeout(() => setMessage({ type: '', text: '' }), 3000);
    };

    // --- Handlers ---

    const handleUpdateProfile = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        try {
            currentUser.displayName = displayName;

            showMessage('success', 'Profile updated successfully.');
            setIsProfileModalOpen(false);
        } catch (error) {
            console.error(error);
            showMessage('error', 'Failed to update profile.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleResetPassword = async () => {
        setModalConfig({
            isOpen: true,
            title: 'Reset Password',
            message: 'Password reset is managed by the local S.P.I.D.E.Y assistant.',
            type: 'default',
            onConfirm: async () => {
                setIsLoading(true);
                try {
                    showMessage('success', 'S.P.I.D.E.Y uses local authentication for this installation.');
                } catch (error) {
                    console.error(error);
                    showMessage('error', 'Failed to send reset email. Try again later.');
                } finally {
                    setIsLoading(false);
                }
            }
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

        setNotificationsEnabled(newState); // Optimistic update

        try {
            localStorage.setItem('spidey_notifications', String(newState));
        } catch (error) {
            console.error(error);
            setNotificationsEnabled(!newState); // Revert
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
            // Fallback if running an un-restarted backend process without /api/database
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
            message:
                'This will permanently erase all tasks, daily habits, reminders, saved memories/notes, chat history, learning roadmaps/topics, and XP from assistant.db. This action cannot be undone.',
            type: 'danger',
            confirmString: 'DELETE',
            onConfirm: async () => {
                setIsLoading(true);
                try {
                    await wipeDatabaseAndSyncUi();
                    showMessage('success', 'All database data has been permanently deleted.');
                } catch (error) {
                    console.error(error);
                    showMessage('error', error.message || 'Failed to delete database data.');
                } finally {
                    setIsLoading(false);
                }
            },
        });
    };

    const handleDeleteAccount = async () => {
        setModalConfig({
            isOpen: true,
            title: 'Delete Account & All Data',
            message: 'Are you sure you want to delete your account? This action cannot be undone. All database data will be permanently erased.',
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
            }
        });
    };

    // --- Components ---

    const SettingSection = ({ title, children }) => (
        <div className="glass-card mb-6 border border-white/5 overflow-hidden">
            <h2 className="text-xs font-bold text-textMuted uppercase tracking-widest mb-4 px-4 pt-4">{title}</h2>
            <div className="space-y-1">
                {children}
            </div>
        </div>
    );

    const SettingItem = ({ icon: Icon, label, value, onClick, destructive = false, toggle = null }) => (
        <div
            onClick={onClick}
            className={`flex items-center justify-between p-4 transition-colors cursor-pointer group ${destructive ? 'hover:bg-red-500/10' : 'hover:bg-white/5'
                }`}
        >
            <div className="flex items-center space-x-4">
                <div className={`p-2 rounded-lg ${destructive ? 'bg-red-500/10 text-red-400' : 'bg-surfaceHighlight text-textMuted group-hover:text-white transition-colors'
                    }`}>
                    <Icon size={18} />
                </div>
                <span className={`text-sm font-medium ${destructive ? 'text-red-400' : 'text-text group-hover:text-white transition-colors'}`}>
                    {label}
                </span>
            </div>

            <div className="flex items-center space-x-3">
                {value && <span className="text-xs text-textMuted font-mono">{value}</span>}

                {toggle !== null ? (
                    <div className={`w-8 h-4 rounded-full relative transition-colors ${toggle ? 'bg-white' : 'bg-white/20'}`}>
                        <div className={`absolute top-0.5 left-0.5 w-3 h-3 bg-black rounded-full transition-transform ${toggle ? 'translate-x-4' : 'translate-x-0'}`} />
                    </div>
                ) : (
                    !destructive && <ChevronRight size={16} className="text-textMuted group-hover:text-white transition-colors" />
                )}
            </div>
        </div>
    );

    return (
        <div className="max-w-2xl mx-auto pb-20 relative">
            <header className="mb-8 border-b border-[#F2EFE9]/15 pb-5">
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#D95D24]">07 · Configuration</span>
                <h1 className="mt-1 text-3xl font-bold uppercase tracking-[0.14em] text-[#F2EFE9]">Settings</h1>
                <p className="mt-1 font-mono text-xs text-[#9C968E]">Make this space feel like yours.</p>
            </header>

            <SettingSection title="Appearance">
                <div className="flex items-center justify-between p-4">
                    <div>
                        <p className="text-sm font-medium text-text">Theme</p>
                        <p className="text-xs text-textMuted mt-1">Choose the dashboard visual mode.</p>
                    </div>
                    <select value={theme} onChange={handleThemeChange} className="bg-surfaceHighlight border border-white/10 rounded-lg p-2 text-white text-sm">
                        <option value="dark">Shadow</option>
                        <option value="midnight">Midnight</option>
                        <option value="light">Light</option>
                    </select>
                </div>
            </SettingSection>

            {/* Feedback Message */}
            <AnimatePresence>
                {message.text && (
                    <motion.div
                        initial={{ opacity: 0, y: -20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg border ${message.type === 'error' ? 'bg-red-900/90 border-red-500 text-white' : 'bg-green-900/90 border-green-500 text-white'
                            }`}
                    >
                        <p className="text-sm font-bold flex items-center gap-2">
                            {message.type === 'error' && <AlertTriangle size={16} />}
                            {message.text}
                        </p>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Profile Card */}
            <div className="flex items-center space-x-4 mb-8 p-6 glass-card border border-white/10 bg-gradient-to-r from-white/5 to-transparent">
                <div className="w-16 h-16 rounded-full bg-white text-black flex items-center justify-center text-2xl font-bold shadow-[0_0_20px_rgba(255,255,255,0.2)]">
                    {currentUser?.photoURL ? (
                        <img src={currentUser.photoURL} alt="Profile" className="w-full h-full rounded-full object-cover" />
                    ) : (
                        currentUser?.displayName?.charAt(0) || 'K'
                    )}
                </div>
                <div>
                    <h2 className="text-xl font-bold text-white flex items-center gap-2">
                        {currentUser?.displayName || 'User'}
                    </h2>
                    <p className="text-textMuted text-sm font-mono">{currentUser?.email}</p>
                    <p className="text-textMuted text-xs mt-1">
                        Joined {currentUser?.metadata?.creationTime ? format(new Date(currentUser.metadata.creationTime), 'MMMM yyyy') : 'Recently'}
                    </p>
                </div>
            </div>

            <SettingSection title="Account">
                <SettingItem
                    icon={User}
                    label="Edit Profile"
                    onClick={() => setIsProfileModalOpen(true)}
                />
                <SettingItem
                    icon={Shield}
                    label="Reset Password"
                    onClick={handleResetPassword}
                />
            </SettingSection>

            <SettingSection title="Preferences">
                <SettingItem
                    icon={Bell}
                    label="Notifications"
                    toggle={notificationsEnabled}
                    onClick={handleToggleNotifications}
                />
            </SettingSection>

            <div className="mb-8">
                <div className="flex items-center justify-between mb-3 px-1">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-textMuted">
                        AI Engine (Google AI Studio)
                    </h3>
                    <span className={`text-[11px] font-mono px-2.5 py-0.5 rounded-full border ${
                        hasSavedGeminiKey
                            ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                            : 'bg-white/5 border-white/10 text-textMuted'
                    }`}>
                        {hasSavedGeminiKey ? `Gemini (${geminiModel})` : 'Local Ollama'}
                    </span>
                </div>
                <form
                    onSubmit={handleSaveGeminiConfig}
                    className="glass-card border border-white/5 p-4 space-y-4"
                >
                    <p className="text-xs text-textMuted leading-relaxed">
                        Add your Google AI Studio Gemini API key to use S.P.I.D.E.Y from mobile or any browser without local Ollama. Stored only in this device&apos;s browser.
                    </p>
                    <div>
                        <label className="block text-[11px] font-bold text-textMuted uppercase mb-1.5">
                            AI Studio API Key
                        </label>
                        <div className="relative flex items-center">
                            <Key size={16} className="absolute left-3.5 text-textMuted pointer-events-none" />
                            <input
                                type={showGeminiKey ? 'text' : 'password'}
                                value={geminiApiKey}
                                onChange={(e) => setGeminiApiKey(e.target.value)}
                                placeholder="AQ... or AIza..."
                                autoComplete="off"
                                className="w-full bg-surfaceHighlight border border-white/10 rounded-lg py-2.5 pl-10 pr-10 text-sm text-white placeholder:text-textMuted/50 focus:outline-none focus:border-white/40 font-mono"
                            />
                            <button
                                type="button"
                                onClick={() => setShowGeminiKey((v) => !v)}
                                aria-label={showGeminiKey ? 'Hide API key' : 'Show API key'}
                                className="absolute right-3 text-textMuted hover:text-white transition-colors"
                            >
                                {showGeminiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                            </button>
                        </div>
                    </div>
                    <div>
                        <label className="block text-[11px] font-bold text-textMuted uppercase mb-1.5">
                            Gemini Model
                        </label>
                        <select
                            value={geminiModel}
                            onChange={(e) => setGeminiModel(e.target.value)}
                            className="w-full bg-surfaceHighlight border border-white/10 rounded-lg py-2.5 px-3 text-sm text-white focus:outline-none focus:border-white/40 font-mono"
                        >
                            <option value="gemini-3.5-flash">gemini-3.5-flash (Recommended)</option>
                            <option value="gemini-3.5-pro">gemini-3.5-pro (Best Reasoning)</option>
                            <option value="gemini-3.8-flash">gemini-3.8-flash (Fast)</option>
                            <option value="gemini-4-hydrogen">gemini-4-hydrogen</option>
                        </select>
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                        <button
                            type="submit"
                            className="flex-1 bg-white hover:bg-gray-200 text-black font-bold py-2.5 px-4 rounded-lg transition-colors text-xs uppercase tracking-wider flex items-center justify-center gap-2"
                        >
                            <Save size={15} />
                            Save Key
                        </button>
                        {hasSavedGeminiKey && (
                            <button
                                type="button"
                                onClick={handleClearGeminiConfig}
                                className="bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 text-red-300 font-bold py-2.5 px-3.5 rounded-lg transition-colors text-xs uppercase tracking-wider flex items-center justify-center gap-1.5"
                            >
                                <Trash2 size={15} />
                                Use Ollama
                            </button>
                        )}
                    </div>
                </form>
            </div>

            <SettingSection title="Session">
                <SettingItem icon={LogOut} label="Log Out" onClick={logout} destructive />
            </SettingSection>

            <div className="mt-12">
                <SettingSection title="Danger Zone">
                    <SettingItem
                        icon={Database}
                        label="Delete All Database Data"
                        value="Tasks, Habits, Chats, Memories, Reminders, Learning"
                        onClick={handleDeleteAllDatabaseData}
                        destructive
                    />
                    <SettingItem
                        icon={AlertTriangle}
                        label="Delete Account"
                        onClick={handleDeleteAccount}
                        destructive
                    />
                </SettingSection>
            </div>

            <div className="text-center mt-12 mb-8">
                <p className="text-[10px] text-textMuted uppercase tracking-widest opacity-50">S.P.I.D.E.Y System v1.1.0</p>
            </div>

            {/* Edit Profile Modal */}
            <AnimatePresence>
                {isProfileModalOpen && (
                    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.95 }}
                            className="glass-card w-full max-w-sm relative border border-white/10 shadow-[0_0_30px_rgba(0,0,0,0.5)] p-6"
                        >
                            <button
                                onClick={() => setIsProfileModalOpen(false)}
                                className="absolute top-4 right-4 text-textMuted hover:text-white transition-colors"
                            >
                                <X size={20} />
                            </button>

                            <h2 className="text-lg font-bold mb-6 text-white uppercase tracking-wide flex items-center gap-2">
                                <User size={20} />
                                Update Profile
                            </h2>

                            <form onSubmit={handleUpdateProfile} className="space-y-6">
                                <div>
                                    <label className="block text-xs font-bold text-textMuted uppercase mb-2">Display Name</label>
                                    <input
                                        type="text"
                                        value={displayName}
                                        onChange={(e) => setDisplayName(e.target.value)}
                                        className="w-full bg-surfaceHighlight border border-white/5 rounded-full py-3 px-6 text-white focus:outline-none focus:border-white/50 focus:ring-1 focus:ring-white/50 transition-all font-mono"
                                        placeholder="Enter your name"
                                        autoFocus
                                    />
                                </div>

                                <button
                                    type="submit"
                                    disabled={isLoading || !displayName.trim()}
                                    className="w-full bg-white hover:bg-gray-200 text-black font-bold py-3 rounded-full transition-colors shadow-[0_0_15px_rgba(255,255,255,0.1)] disabled:opacity-50 disabled:cursor-not-allowed uppercase tracking-wider text-sm flex items-center justify-center gap-2"
                                >
                                    {isLoading ? <Loader size={18} className="animate-spin" /> : <Save size={18} />}
                                    Save Changes
                                </button>
                            </form>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
            {/* Confirmation Modal */}
            <ConfirmationModal
                isOpen={modalConfig.isOpen}
                onClose={() => setModalConfig({ ...modalConfig, isOpen: false })}
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
