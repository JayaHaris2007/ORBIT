import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
    X, Lock, Play, CheckCircle2, PauseCircle, Trash2, Plus,
    Pencil, BookOpen, Sparkles, FolderCode, FolderOpen, RefreshCw, Search,
    FileCode2, Unlink, Check, ExternalLink, RotateCcw,
} from 'lucide-react';
import { learningService } from '../../services/learningService';
import { useAppData } from '../../context/AppDataContext';
import { useTheme } from '../../context/AuthContext';

const STATUS_LABELS = {
    not_started: 'Not started',
    learning: 'Learning',
    completed: 'Completed',
    on_hold: 'On hold',
};

const STATUS_CHIP = {
    not_started: 'bg-white/5 text-textMuted border-white/10',
    learning: 'bg-amber-500/15 text-amber-300 border-amber-400/20',
    completed: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/20',
    on_hold: 'bg-red-500/15 text-red-300 border-red-400/20',
};

const RoadmapDetail = ({ roadmap, onClose, onChanged }) => {
    const { revision } = useAppData();
    const { theme } = useTheme();
    const [detail, setDetail] = useState(roadmap);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);

    // Edit roadmap name
    const [isRenaming, setIsRenaming] = useState(false);
    const [draftName, setDraftName] = useState('');

    // Add topic form
    const [isAdding, setIsAdding] = useState(false);
    const [newName, setNewName] = useState('');
    const [newPriority, setNewPriority] = useState(2);

    // Code folder & Hybrid RAG state
    const [insights, setInsights] = useState(null);
    const [folderInput, setFolderInput] = useState('');
    const [isManualPathOpen, setIsManualPathOpen] = useState(false);
    const [pickingFolder, setPickingFolder] = useState(false);
    const [syncingFolder, setSyncingFolder] = useState(false);
    const [showFiles, setShowFiles] = useState(false);
    const [ragQuery, setRagQuery] = useState('');
    const [ragResults, setRagResults] = useState([]);
    const [ragSearching, setRagSearching] = useState(false);
    const [ragSearched, setRagSearched] = useState(false);

    const loadInsights = useCallback(async (id) => {
        try {
            const data = await learningService.getCodeInsights(id);
            setInsights(data);
            if (data?.folder?.folder_path) {
                setFolderInput(data.folder.folder_path);
            }
        } catch {
            // Optional if backend is in mock mode
        }
    }, []);

    useEffect(() => {
        let cancelled = false;
        learningService.getRoadmap(roadmap.id)
            .then((data) => {
                if (!cancelled) {
                    setDetail(data);
                    setLoading(false);
                }
            })
            .catch((loadError) => {
                if (!cancelled) {
                    setError(loadError.message || 'Could not load this roadmap.');
                    setLoading(false);
                }
            });
        loadInsights(roadmap.id);
        return () => { cancelled = true; };
    }, [roadmap.id, revision, loadInsights]);

    const reload = async () => {
        const data = await learningService.getRoadmap(roadmap.id);
        setDetail(data);
        await loadInsights(roadmap.id);
        onChanged?.();
    };

    const handleBrowseFolder = async () => {
        if (pickingFolder || syncingFolder) return;
        setPickingFolder(true);
        setError('');
        try {
            const currentPath = insights?.folder?.folder_path || folderInput.trim() || null;
            const picked = await learningService.pickFolder(currentPath);
            if (picked?.cancelled || !picked?.folder_path) {
                return;
            }
            setFolderInput(picked.folder_path);
            setSyncingFolder(true);
            await learningService.linkFolder(detail.id, picked.folder_path, true);
            setIsManualPathOpen(false);
            await reload();
        } catch (pickError) {
            setError(pickError.message || 'Could not select folder.');
        } finally {
            setPickingFolder(false);
            setSyncingFolder(false);
        }
    };

    const handleOpenInExplorer = async () => {
        setError('');
        try {
            await learningService.openFolderInExplorer(detail.id);
        } catch (openErr) {
            setError(openErr.message || 'Could not open folder.');
        }
    };

    const handleLinkFolder = async (e) => {
        e.preventDefault();
        const cleaned = folderInput.trim();
        if (!cleaned || syncingFolder) return;
        setSyncingFolder(true);
        setError('');
        try {
            await learningService.linkFolder(detail.id, cleaned, true);
            setIsManualPathOpen(false);
            await reload();
        } catch (linkError) {
            setError(linkError.message || 'Could not link folder.');
        } finally {
            setSyncingFolder(false);
        }
    };

    const handleSyncFolder = async () => {
        if (syncingFolder) return;
        setSyncingFolder(true);
        setError('');
        try {
            await learningService.syncFolder(detail.id);
            await reload();
        } catch (syncError) {
            setError(syncError.message || 'Could not sync folder.');
        } finally {
            setSyncingFolder(false);
        }
    };

    const handleUnlinkFolder = async () => {
        if (syncingFolder) return;
        setSyncingFolder(true);
        setError('');
        try {
            await learningService.unlinkFolder(detail.id);
            setFolderInput('');
            setIsManualPathOpen(false);
            setRagResults([]);
            setRagSearched(false);
            await reload();
        } catch (unlinkError) {
            setError(unlinkError.message || 'Could not unlink folder.');
        } finally {
            setSyncingFolder(false);
        }
    };

    const handleResolveSuggestion = async (suggestionId, state) => {
        setBusy(true);
        setError('');
        try {
            await learningService.updateCodeSuggestion(suggestionId, state);
            await reload();
        } catch (resolveErr) {
            setError(resolveErr.message);
        } finally {
            setBusy(false);
        }
    };

    const handleRagSearch = async (e) => {
        e.preventDefault();
        const q = ragQuery.trim();
        if (!q || ragSearching) return;
        setRagSearching(true);
        setRagSearched(true);
        setError('');
        try {
            const hits = await learningService.searchCodeRag(q, detail.id, 4);
            setRagResults(hits);
        } catch (searchErr) {
            setError(searchErr.message || 'RAG search failed.');
        } finally {
            setRagSearching(false);
        }
    };

    const handleRename = async () => {
        const name = draftName.trim();
        if (!name || name === detail.name || busy) return;
        setBusy(true);
        try {
            const updated = await learningService.updateRoadmap(detail.id, { name });
            setDetail((current) => ({ ...current, ...updated }));
            setIsRenaming(false);
            onChanged?.();
        } catch (renameError) {
            setError(renameError.message);
        } finally {
            setBusy(false);
        }
    };

    const handleStatus = async (topic, status) => {
        setBusy(true);
        setError('');
        try {
            await learningService.updateTopic(topic.id, { status });
            await reload();
        } catch (statusError) {
            setError(statusError.message);
        } finally {
            setBusy(false);
        }
    };

    const handleDeleteTopic = async (topic) => {
        setBusy(true);
        setError('');
        try {
            await learningService.deleteTopic(topic.id);
            await reload();
        } catch (deleteError) {
            setError(deleteError.message);
        } finally {
            setBusy(false);
        }
    };

    const handleAddTopic = async (e) => {
        e.preventDefault();
        const raw = newName.trim();
        if (!raw || busy) return;
        setBusy(true);
        setError('');
        try {
            const lines = raw.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
            if (lines.length > 1) {
                await learningService.bulkCreateTopics(detail.id, {
                    raw_text: raw,
                    priority: newPriority,
                });
            } else {
                await learningService.createTopic({
                    roadmap_id: detail.id,
                    roadmapId: detail.id,
                    name: raw,
                    priority: newPriority,
                });
            }
            setNewName('');
            setNewPriority(2);
            setIsAdding(false);
            await reload();
        } catch (addError) {
            setError(addError.message);
        } finally {
            setBusy(false);
        }
    };

    useEffect(() => {
        const handleKey = (e) => {
            if (e.key === 'Escape') onClose?.();
        };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [onClose]);

    const topics = detail.topics ?? [];
    const completed = topics.filter((topic) => topic.status === 'completed').length;
    const percent = topics.length ? Math.round((completed / topics.length) * 100) : 0;

    return createPortal(
        <div className={`app-theme-${theme}`}>
            <AnimatePresence>
                <div className="fixed inset-0 z-[110] bg-black/75 backdrop-blur-sm" onClick={onClose} />
                <motion.aside
                    initial={{ x: '100%' }}
                    animate={{ x: 0 }}
                    exit={{ x: '100%' }}
                    transition={{ type: 'tween', duration: 0.25 }}
                    className="fixed top-0 right-0 bottom-0 z-[115] w-full max-w-xl bg-surface text-text border-l border-white/15 shadow-2xl flex flex-col"
                >
                {/* Header */}
                <div className="p-6 border-b border-white/10 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        {isRenaming ? (
                            <div className="flex items-center gap-2">
                                <input
                                    type="text"
                                    value={draftName}
                                    onChange={(e) => setDraftName(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleRename()}
                                    className="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-white text-lg font-bold focus:border-orange-400/50 outline-none"
                                    autoFocus
                                    maxLength={120}
                                />
                                <button
                                    onClick={handleRename}
                                    className="p-2 rounded-lg bg-primary text-white shrink-0 hover:bg-orange-500 transition-colors"
                                    title="Save name"
                                >
                                    <CheckCircle2 size={18} />
                                </button>
                            </div>
                        ) : (
                            <div className="flex items-center gap-2">
                                <h2 className="text-xl font-bold text-white truncate">{detail.name}</h2>
                                <button
                                    onClick={() => { setDraftName(detail.name); setIsRenaming(true); }}
                                    className="p-1.5 rounded-lg text-textMuted hover:text-white hover:bg-white/5 transition-colors shrink-0"
                                    title="Rename roadmap"
                                >
                                    <Pencil size={14} />
                                </button>
                            </div>
                        )}
                        <p className="text-xs text-textMuted mt-1 line-clamp-2">{detail.description}</p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 rounded-lg text-textMuted hover:text-white hover:bg-white/5 transition-colors shrink-0"
                        title="Close"
                    >
                        <X size={18} />
                    </button>
                </div>

                {/* Progress strip */}
                <div className="px-6 py-4 border-b border-white/10 space-y-2">
                    <div className="flex justify-between text-xs text-textMuted">
                        <span className="uppercase tracking-widest font-bold">Progress</span>
                        <span>{completed} / {topics.length} topics · {percent}%</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div
                            className="h-full rounded-full bg-gradient-to-r from-orange-500 to-amber-400 transition-all duration-500"
                            style={{ width: `${percent}%` }}
                        />
                    </div>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto p-6 space-y-4">
                    {error && (
                        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                            {error}
                        </div>
                    )}

                    {/* Local Code Folder Auto-Tracker & Hybrid RAG Panel */}
                    <div className="glass-card p-4 space-y-3 border-orange-400/20">
                        <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                                <FolderCode size={15} className="text-orange-400 shrink-0" />
                                <span className="text-[11px] font-mono font-bold uppercase tracking-widest text-white">
                                    Code Folder &amp; RAG
                                </span>
                            </div>
                            {insights?.folder ? (
                                <div className="flex items-center gap-1.5 shrink-0">
                                    <button
                                        type="button"
                                        onClick={handleSyncFolder}
                                        disabled={syncingFolder || pickingFolder}
                                        className="flex items-center gap-1 px-2 py-1 rounded bg-orange-500/15 text-orange-300 border border-orange-400/25 hover:bg-orange-500/25 text-[10px] font-mono uppercase font-bold transition-colors disabled:opacity-50"
                                        title="Re-scan folder and update RAG index"
                                    >
                                        <RefreshCw size={11} className={syncingFolder ? 'animate-spin' : ''} />
                                        {syncingFolder ? 'Syncing' : 'Sync'}
                                    </button>
                                    <button
                                        type="button"
                                        onClick={handleBrowseFolder}
                                        disabled={pickingFolder || syncingFolder}
                                        className="p-1 rounded text-textMuted hover:text-white hover:bg-white/5 transition-colors disabled:opacity-50"
                                        title="Change folder via Explorer window"
                                    >
                                        <FolderOpen size={13} />
                                    </button>
                                    <button
                                        type="button"
                                        onClick={handleUnlinkFolder}
                                        disabled={syncingFolder || pickingFolder}
                                        className="p-1 rounded text-textMuted hover:text-red-400 hover:bg-red-500/10 transition-colors"
                                        title="Unlink folder"
                                    >
                                        <Unlink size={12} />
                                    </button>
                                </div>
                            ) : null}
                        </div>

                        {!insights?.folder && (
                            <div className="space-y-2.5">
                                <p className="text-xs text-textMuted">
                                    Choose your local practice folder so S.P.I.D.E.Y. tracks your progress, notices unfinished files, and indexes your code for RAG Q&amp;A.
                                </p>
                                <button
                                    type="button"
                                    onClick={handleBrowseFolder}
                                    disabled={pickingFolder || syncingFolder}
                                    className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-primary hover:bg-orange-500 text-white text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50"
                                >
                                    <FolderOpen size={15} />
                                    {pickingFolder
                                        ? 'Choose folder in window…'
                                        : syncingFolder
                                            ? 'Analyzing folder…'
                                            : 'Browse Folder'}
                                </button>
                                {isManualPathOpen ? (
                                    <form onSubmit={handleLinkFolder} className="space-y-2 pt-1">
                                        <input
                                            type="text"
                                            value={folderInput}
                                            onChange={(e) => setFolderInput(e.target.value)}
                                            placeholder="Or paste folder path…"
                                            className="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-white text-xs font-mono focus:border-orange-400/50 outline-none"
                                            autoFocus
                                        />
                                        <div className="flex gap-2">
                                            <button
                                                type="button"
                                                onClick={() => setIsManualPathOpen(false)}
                                                className="px-3 py-1.5 rounded-lg border border-white/10 text-[11px] text-textMuted hover:text-white"
                                            >
                                                Cancel
                                            </button>
                                            <button
                                                type="submit"
                                                disabled={!folderInput.trim() || syncingFolder}
                                                className="flex-1 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-white text-[11px] font-bold uppercase tracking-wider disabled:opacity-50"
                                            >
                                                Link Path
                                            </button>
                                        </div>
                                    </form>
                                ) : (
                                    <button
                                        type="button"
                                        onClick={() => setIsManualPathOpen(true)}
                                        className="text-[10px] font-mono text-textMuted hover:text-white transition-colors"
                                    >
                                        or enter path manually
                                    </button>
                                )}
                            </div>
                        )}

                        {insights?.folder && (
                            <div className="space-y-3">
                                <div className="flex items-center justify-between gap-2 rounded-lg bg-black/30 border border-white/10 px-2.5 py-1.5">
                                    <p className="text-[11px] font-mono text-textMuted truncate" title={insights.folder.folder_path}>
                                        {insights.folder.folder_path}
                                    </p>
                                    <button
                                        type="button"
                                        onClick={handleOpenInExplorer}
                                        className="p-1 rounded text-textMuted hover:text-orange-300 transition-colors shrink-0"
                                        title="Open folder in Explorer"
                                    >
                                        <ExternalLink size={12} />
                                    </button>
                                </div>

                                <div className="grid grid-cols-3 gap-2 text-center">
                                    <div className="rounded-lg bg-white/5 border border-white/5 px-2 py-1.5">
                                        <p className="text-sm font-bold text-emerald-400">{insights.practiced_count ?? 0}</p>
                                        <p className="text-[9px] font-mono uppercase text-textMuted">Coded</p>
                                    </div>
                                    <div className="rounded-lg bg-white/5 border border-white/5 px-2 py-1.5">
                                        <p className="text-sm font-bold text-amber-400">{insights.wip_count ?? 0}</p>
                                        <p className="text-[9px] font-mono uppercase text-textMuted">WIP / Empty</p>
                                    </div>
                                    <div className="rounded-lg bg-white/5 border border-white/5 px-2 py-1.5">
                                        <p className="text-sm font-bold text-orange-300">{insights.pending_suggestions?.length ?? 0}</p>
                                        <p className="text-[9px] font-mono uppercase text-textMuted">To confirm</p>
                                    </div>
                                </div>

                                {insights.friendly_summary && (
                                    <div className="rounded-lg bg-orange-500/10 border border-orange-400/20 px-3 py-2 text-xs text-white/90 leading-relaxed">
                                        {insights.friendly_summary.replace(/\*\*/g, '')}
                                    </div>
                                )}

                                {insights.pending_suggestions?.length > 0 && (
                                    <div className="space-y-2">
                                        <p className="text-[10px] font-mono uppercase tracking-wider text-emerald-300">
                                            New code detected — mark completed?
                                        </p>
                                        {insights.pending_suggestions.map((s) => (
                                            <div
                                                key={s.id}
                                                className="rounded-lg bg-emerald-500/10 border border-emerald-400/25 p-2.5 space-y-2"
                                            >
                                                <div className="min-w-0">
                                                    <p className="text-xs font-semibold text-white truncate">{s.topic_name}</p>
                                                    <p className="text-[11px] text-textMuted mt-0.5">{s.reason}</p>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => handleResolveSuggestion(s.id, 'confirmed')}
                                                        disabled={busy}
                                                        className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 hover:bg-emerald-500/30 text-[11px] font-semibold transition-colors disabled:opacity-50"
                                                    >
                                                        <Check size={12} /> Yes, mark completed
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => handleResolveSuggestion(s.id, 'dismissed')}
                                                        disabled={busy}
                                                        className="px-2.5 py-1.5 rounded border border-white/10 text-textMuted hover:text-white hover:bg-white/5 text-[11px] transition-colors disabled:opacity-50"
                                                    >
                                                        Not yet
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {insights.files?.length > 0 && (
                                    <div className="space-y-1.5">
                                        <button
                                            type="button"
                                            onClick={() => setShowFiles((v) => !v)}
                                            className="text-[10px] font-mono uppercase tracking-wider text-textMuted hover:text-white transition-colors"
                                        >
                                            {showFiles ? '▾ Hide' : '▸ Show'} indexed files ({insights.files.length})
                                        </button>
                                        {showFiles && (
                                            <div className="flex flex-wrap gap-1.5 pt-1">
                                                {insights.files.map((f) => (
                                                    <span
                                                        key={f.rel_path}
                                                        title={f.summary}
                                                        className={`inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded border ${
                                                            f.file_state === 'practiced'
                                                                ? 'bg-emerald-500/10 text-emerald-300 border-emerald-400/20'
                                                                : 'bg-amber-500/10 text-amber-300 border-amber-400/20'
                                                        }`}
                                                    >
                                                        <FileCode2 size={10} />
                                                        {f.rel_path}
                                                        {f.file_state === 'empty' ? ' (empty)' : ''}
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Mini Hybrid Code RAG Search */}
                                <form onSubmit={handleRagSearch} className="flex gap-1.5">
                                    <input
                                        type="text"
                                        value={ragQuery}
                                        onChange={(e) => setRagQuery(e.target.value)}
                                        placeholder="Search your code (e.g. while loop, type casting, cin)…"
                                        className="flex-1 bg-black/30 border border-white/10 rounded-lg px-2.5 py-1.5 text-white text-xs focus:border-orange-400/50 outline-none"
                                    />
                                    <button
                                        type="submit"
                                        disabled={!ragQuery.trim() || ragSearching}
                                        className="px-2.5 py-1.5 rounded-lg bg-white/10 hover:bg-orange-500/20 text-white text-xs transition-colors disabled:opacity-50"
                                        title="Search code via Hybrid RAG"
                                    >
                                        <Search size={13} />
                                    </button>
                                </form>

                                {ragSearched && (
                                    <div className="space-y-2">
                                        {ragResults.length === 0 ? (
                                            <p className="text-[11px] text-textMuted">No matching code chunks found.</p>
                                        ) : (
                                            ragResults.map((hit) => (
                                                <div
                                                    key={hit.chunk_id}
                                                    className="rounded-lg bg-black/40 border border-white/10 p-2.5 space-y-1"
                                                >
                                                    <div className="flex items-center justify-between text-[10px] font-mono text-orange-300">
                                                        <span>{hit.rel_path} (L{hit.start_line}–L{hit.end_line})</span>
                                                        <span className="text-textMuted">{hit.file_state}</span>
                                                    </div>
                                                    <pre className="text-[10px] font-mono text-white/80 overflow-x-auto max-h-28 whitespace-pre-wrap">
                                                        {hit.snippet}
                                                    </pre>
                                                </div>
                                            ))
                                        )}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {loading ? (
                        <p className="text-sm text-textMuted text-center py-10">Loading topics…</p>
                    ) : topics.length === 0 ? (
                        <div className="glass-card p-8 text-center space-y-3">
                            <div className="p-3 bg-white/5 rounded-full w-fit mx-auto text-textMuted"><BookOpen size={22} /></div>
                            <p className="text-sm text-textMuted">No topics yet — add the first one below.</p>
                        </div>
                    ) : (
                        topics.map((topic) => {
                            const locked = !topic.available;
                            const topicEv = insights?.evidence_by_topic?.[topic.id] || insights?.evidence_by_topic?.[String(topic.id)];
                            const isPendingCodeConfirm = topicEv?.suggestion_state === 'pending' && topic.status !== 'completed';
                            return (
                                <motion.div
                                    key={topic.id}
                                    layout
                                    initial={{ opacity: 0, y: 8 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className={`glass-card p-4 space-y-3 ${locked ? 'opacity-75' : ''}`}
                                >
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="min-w-0">
                                            <div className="flex items-center gap-2">
                                                <p className="font-medium text-white truncate">{topic.name}</p>
                                                {locked && <Lock size={13} className="text-textMuted shrink-0" />}
                                            </div>
                                            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                                                <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full border ${STATUS_CHIP[topic.status] || STATUS_CHIP.not_started}`}>
                                                    {STATUS_LABELS[topic.status] || topic.status}
                                                </span>
                                                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full border border-white/10 text-textMuted">
                                                    P{topic.priority || 2}
                                                </span>
                                                {topicEv?.evidence_files?.slice(0, 2).map((ef) => (
                                                    <span
                                                        key={ef.rel_path}
                                                        className="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-orange-200/90"
                                                    >
                                                        <FileCode2 size={10} className="text-orange-400" />
                                                        {ef.rel_path}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-1.5 shrink-0">
                                            {isPendingCodeConfirm && (
                                                <button
                                                    onClick={() => handleResolveSuggestion(topicEv.id, 'confirmed')}
                                                    disabled={busy}
                                                    className="flex items-center gap-1 px-2 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 hover:bg-emerald-500/30 text-[10px] font-bold uppercase tracking-wider transition-colors disabled:opacity-50"
                                                    title="Confirm completed based on code files"
                                                >
                                                    <Check size={12} /> Confirm
                                                </button>
                                            )}
                                            {!locked && topic.status !== 'completed' && topic.status !== 'learning' && (
                                                <button
                                                    onClick={() => handleStatus(topic, 'learning')}
                                                    disabled={busy}
                                                    className="p-2 rounded-lg bg-amber-500/15 text-amber-300 hover:bg-amber-500/25 transition-colors disabled:opacity-50"
                                                    title="Start learning"
                                                >
                                                    <Play size={15} />
                                                </button>
                                            )}
                                            {!locked && topic.status !== 'completed' && (
                                                <button
                                                    onClick={() => handleStatus(topic, 'completed')}
                                                    disabled={busy}
                                                    className="p-2 rounded-lg bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 transition-colors disabled:opacity-50"
                                                    title="Mark completed"
                                                >
                                                    <CheckCircle2 size={15} />
                                                </button>
                                            )}
                                            {topic.status === 'completed' && (
                                                <button
                                                    onClick={() => handleStatus(topic, 'learning')}
                                                    disabled={busy}
                                                    className="p-2 rounded-lg bg-white/5 text-textMuted hover:text-amber-300 hover:bg-amber-500/15 transition-colors disabled:opacity-50"
                                                    title="Reopen as In Progress"
                                                >
                                                    <RotateCcw size={14} />
                                                </button>
                                            )}
                                            {topic.status === 'learning' && (
                                                <button
                                                    onClick={() => handleStatus(topic, 'on_hold')}
                                                    disabled={busy}
                                                    className="p-2 rounded-lg bg-red-500/15 text-red-300 hover:bg-red-500/25 transition-colors disabled:opacity-50"
                                                    title="Put on hold"
                                                >
                                                    <PauseCircle size={15} />
                                                </button>
                                            )}
                                            <button
                                                onClick={() => handleDeleteTopic(topic)}
                                                disabled={busy}
                                                className="p-2 rounded-lg text-textMuted hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                                                title="Delete topic"
                                            >
                                                <Trash2 size={15} />
                                            </button>
                                        </div>
                                    </div>

                                    {locked && topic.unmetPrerequisites?.length > 0 && (
                                        <div className="flex items-center gap-2 text-xs text-textMuted bg-white/5 rounded-lg px-3 py-2 border border-white/5">
                                            <Sparkles size={13} className="text-orange-400 shrink-0" />
                                            <span className="truncate">
                                                Complete first: {topic.unmetPrerequisites.join(', ')}
                                            </span>
                                        </div>
                                    )}
                                </motion.div>
                            );
                        })
                    )}
                </div>

                {/* Add topic footer */}
                <div className="p-6 border-t border-white/10">
                    {isAdding ? (
                        <form onSubmit={handleAddTopic} className="space-y-3">
                            <div className="flex gap-2 items-start">
                                <textarea
                                    rows={3}
                                    value={newName}
                                    onChange={(e) => setNewName(e.target.value)}
                                    placeholder="Topic name (or paste multiple headings, one per line)"
                                    className="flex-1 bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:border-orange-400/50 outline-none resize-y"
                                    autoFocus
                                />
                                <select
                                    value={newPriority}
                                    onChange={(e) => setNewPriority(Number(e.target.value))}
                                    className="w-24 bg-surfaceHighlight border border-white/10 rounded-lg px-2 py-2.5 text-sm text-white focus:border-orange-400/50 outline-none"
                                    title="Priority"
                                >
                                    <option value={1}>P1</option>
                                    <option value={2}>P2</option>
                                    <option value={3}>P3</option>
                                </select>
                            </div>
                            <div className="flex gap-2">
                                <button
                                    type="button"
                                    onClick={() => setIsAdding(false)}
                                    className="flex-1 py-2.5 rounded-lg border border-white/10 text-textMuted hover:text-white hover:bg-white/5 transition-all uppercase text-xs font-bold tracking-wider"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={!newName.trim() || busy}
                                    className="flex-1 py-2.5 rounded-lg bg-primary hover:bg-orange-500 text-white transition-all uppercase text-xs font-bold tracking-wider disabled:opacity-50"
                                >
                                    Add topic
                                </button>
                            </div>
                        </form>
                    ) : (
                        <button
                            onClick={() => setIsAdding(true)}
                            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-dashed border-white/15 text-textMuted hover:text-white hover:border-orange-400/40 hover:bg-orange-500/5 transition-colors text-sm font-semibold"
                        >
                            <Plus size={16} /> Add topic
                        </button>
                    )}
                </div>
                </motion.aside>
            </AnimatePresence>
        </div>,
        document.body
    );
};

export default RoadmapDetail;
