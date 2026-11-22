import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FolderCode, Check, X, RefreshCw, Loader2, FileCode2 } from 'lucide-react';
import { learningService } from '../../services/learningService';
import { useAppData } from '../../context/AppDataContext';

/**
 * Review queue for code-based topic completion suggestions detected by S.P.I.D.E.Y.'s
 * local folder analyzer & Hybrid Code RAG engine.
 */
const CodeSuggestions = ({ onChanged, hasLinkedFolders = false }) => {
    const { revision } = useAppData();
    const [suggestions, setSuggestions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [syncing, setSyncing] = useState(false);
    const [busyId, setBusyId] = useState(null);
    const [error, setError] = useState('');

    const load = useCallback(async () => {
        try {
            setError('');
            const items = await learningService.listCodeSuggestions();
            setSuggestions(items);
        } catch (err) {
            setError(err.message || 'Could not load code progress suggestions.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load, revision]);

    const handleSyncAll = async () => {
        setSyncing(true);
        setError('');
        try {
            const res = await learningService.syncAllFolders();
            setSuggestions(res.suggestions ?? []);
            onChanged?.();
        } catch (err) {
            setError(err.message || 'Could not sync linked folders.');
        } finally {
            setSyncing(false);
        }
    };

    const handleResolve = async (item, state) => {
        setBusyId(item.id);
        setError('');
        try {
            await learningService.updateCodeSuggestion(item.id, state);
            setSuggestions((curr) => curr.filter((s) => s.id !== item.id));
            onChanged?.();
        } catch (err) {
            setError(err.message || 'Could not update suggestion.');
        } finally {
            setBusyId(null);
        }
    };

    if (!loading && !hasLinkedFolders && suggestions.length === 0) {
        return null;
    }

    return (
        <section className="space-y-4">
            <div className="flex items-center justify-between gap-2 text-white/80">
                <div className="flex items-center gap-2">
                    <FolderCode size={18} className="text-orange-400" />
                    <h2 className="text-lg font-semibold uppercase tracking-widest">Code folder completions</h2>
                    {!loading && suggestions.length > 0 && (
                        <span className="text-[10px] uppercase font-bold tracking-widest px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-400/20">
                            {suggestions.length} ready to confirm
                        </span>
                    )}
                </div>
                <button
                    type="button"
                    onClick={handleSyncAll}
                    disabled={syncing || loading}
                    className="flex items-center gap-1.5 border border-white/15 bg-white/5 px-2.5 py-1.5 font-mono text-[10px] font-bold uppercase tracking-wider text-textMuted transition-colors hover:border-orange-400/50 hover:text-white disabled:opacity-50"
                    title="Scan linked learning code folders for progress"
                >
                    <RefreshCw size={12} className={syncing ? 'animate-spin' : ''} />
                    <span>{syncing ? 'Analyzing…' : 'Sync folders'}</span>
                </button>
            </div>

            {error && (
                <div className="glass-card p-4 border-red-500/30 text-red-300 text-sm">
                    {error}
                </div>
            )}

            {loading ? (
                <div className="glass-card p-6 flex items-center justify-center gap-2 text-textMuted text-sm">
                    <Loader2 size={16} className="animate-spin" /> Checking code folder progress…
                </div>
            ) : suggestions.length === 0 ? (
                <div className="glass-card p-6 text-center space-y-1.5">
                    <p className="text-sm text-textMuted">
                        All caught up — no pending topic completions waiting from your linked code folders.
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <AnimatePresence>
                        {suggestions.map((item) => (
                            <motion.div
                                key={item.id}
                                layout
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, scale: 0.95 }}
                                className="glass-card p-4 space-y-3 hover:border-white/20 transition-colors"
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <p className="font-medium text-white truncate">{item.topicName}</p>
                                        <p className="text-xs text-textMuted mt-0.5 truncate">
                                            {item.roadmapName} · {item.reason}
                                        </p>
                                    </div>
                                    <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-textMuted shrink-0">
                                        {Math.round((item.confidence ?? 0) * 100)}%
                                    </span>
                                </div>

                                {item.evidenceFiles?.length > 0 && (
                                    <div className="flex flex-wrap gap-1.5">
                                        {item.evidenceFiles.slice(0, 4).map((f) => (
                                            <span
                                                key={f.rel_path}
                                                className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10 text-orange-200"
                                            >
                                                <FileCode2 size={11} className="text-orange-400" />
                                                {f.rel_path}
                                            </span>
                                        ))}
                                    </div>
                                )}

                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => handleResolve(item, 'confirmed')}
                                        disabled={busyId === item.id}
                                        className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-400/20 hover:bg-emerald-500/25 transition-colors text-xs font-semibold disabled:opacity-50"
                                    >
                                        <Check size={14} /> Confirm completed
                                    </button>
                                    <button
                                        onClick={() => handleResolve(item, 'dismissed')}
                                        disabled={busyId === item.id}
                                        className="flex items-center gap-1 px-3 py-2 rounded-lg border border-white/10 text-textMuted hover:text-red-400 hover:bg-red-500/10 transition-colors text-xs font-semibold disabled:opacity-50"
                                        title="Keep in progress for now"
                                    >
                                        <X size={13} /> Not yet
                                    </button>
                                </div>
                            </motion.div>
                        ))}
                    </AnimatePresence>
                </div>
            )}
        </section>
    );
};

export default CodeSuggestions;
