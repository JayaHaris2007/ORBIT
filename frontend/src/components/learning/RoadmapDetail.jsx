import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'framer-motion';
import { learningService } from '../../services/learningService';
import { useAppData } from '../../context/AppDataContext';
import { useTheme } from '../../context/AuthContext';

const NEXT_STATUS = {
    not_started: 'learning',
    learning: 'completed',
    completed: 'not_started',
    on_hold: 'learning',
};

const STATUS_STYLE = {
    not_started: { symbol: '○', label: 'To do', cls: 'text-[#7D756C] border-[#F2EFE9]/14' },
    learning: { symbol: '◐', label: 'Learning', cls: 'text-[#E87D42] border-[#D95D24]/55 bg-[#190F09]' },
    completed: { symbol: '●', label: 'Done', cls: 'text-[#060606] border-[#D95D24] bg-[#D95D24] font-semibold' },
    on_hold: { symbol: '—', label: 'Paused', cls: 'text-[#8E867D] border-[#F2EFE9]/14' },
};

/**
 * Calm, spacious centered pop-up for inspecting and updating a Learning Roadmap.
 * Clean 2-tab separation keeps the topic checklist distraction-free while preserving
 * full Local Code Folder & Hybrid RAG search in its own dedicated tab.
 */
const RoadmapDetail = ({ roadmap, onClose, onChanged }) => {
    const { revision } = useAppData();
    const { theme } = useTheme();
    const [detail, setDetail] = useState(roadmap);
    const [tab, setTab] = useState('topics'); // 'topics' | 'folder'
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);

    // Inline rename
    const [isRenaming, setIsRenaming] = useState(false);
    const [draftName, setDraftName] = useState('');

    // Add topics form
    const [isAdding, setIsAdding] = useState(false);
    const [newName, setNewName] = useState('');

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
            // Optional when backend is offline / mock
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
        learningService.getCodeInsights(roadmap.id)
            .then((data) => {
                if (!cancelled) {
                    setInsights(data);
                    if (data?.folder?.folder_path) {
                        setFolderInput(data.folder.folder_path);
                    }
                }
            })
            .catch(() => {});
        return () => { cancelled = true; };
    }, [roadmap.id, revision]);

    useEffect(() => {
        const handleKey = (e) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                onClose?.();
            }
        };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [onClose]);

    const reload = async () => {
        const data = await learningService.getRoadmap(roadmap.id);
        setDetail(data);
        await loadInsights(roadmap.id);
        onChanged?.();
    };

    const handleRename = async () => {
        const name = draftName.trim();
        if (!name || name === detail.name || busy) {
            setIsRenaming(false);
            return;
        }
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
        if (busy) return;
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
        if (busy) return;
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
                await learningService.bulkCreateTopics(detail.id, { raw_text: raw, priority: 2 });
            } else {
                await learningService.createTopic({
                    roadmap_id: detail.id,
                    roadmapId: detail.id,
                    name: raw,
                    priority: 2,
                });
            }
            setNewName('');
            setIsAdding(false);
            await reload();
        } catch (addError) {
            setError(addError.message);
        } finally {
            setBusy(false);
        }
    };

    const handleBrowseFolder = async () => {
        if (pickingFolder || syncingFolder) return;
        setPickingFolder(true);
        setError('');
        try {
            const currentPath = insights?.folder?.folder_path || folderInput.trim() || null;
            const picked = await learningService.pickFolder(currentPath);
            if (picked?.cancelled || !picked?.folder_path) return;
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

    const handleOpenInExplorer = async () => {
        try {
            await learningService.openFolderInExplorer(detail.id);
        } catch (openErr) {
            setError(openErr.message || 'Could not open folder.');
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
            setError(searchErr.message || 'Code search failed.');
        } finally {
            setRagSearching(false);
        }
    };

    const topics = detail.topics ?? [];
    const completed = topics.filter((t) => t.status === 'completed').length;
    const percent = topics.length ? Math.round((completed / topics.length) * 100) : 0;
    const pendingSuggestionsCount = insights?.pending_suggestions?.length ?? 0;

    return createPortal(
        <div className={`app-theme-${theme}`}>
            <div
                role="dialog"
                aria-modal="true"
                className="fixed inset-0 z-[115] flex items-center justify-center p-3 sm:p-6"
            >
                <div
                    className="fixed inset-0 bg-black/80 backdrop-blur-[3px]"
                    onClick={onClose}
                />

                <motion.div
                    initial={{ opacity: 0, y: 12, scale: 0.985 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 8, scale: 0.985 }}
                    transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                    className="ascii-frame relative z-10 flex max-h-[84dvh] w-full max-w-2xl flex-col overflow-hidden bg-[#0A0908] text-[#F2EFE9] shadow-[0_28px_90px_rgba(0,0,0,0.9)]"
                >
                    {/* Minimal Header */}
                    <div className="shrink-0 border-b border-[#F2EFE9]/10 px-6 py-5 sm:px-7">
                        <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0 flex-1">
                                {isRenaming ? (
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="text"
                                            value={draftName}
                                            onChange={(e) => setDraftName(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') handleRename();
                                                if (e.key === 'Escape') setIsRenaming(false);
                                            }}
                                            className="w-full border border-[#D95D24] bg-[#060606] px-3 py-1.5 text-base font-medium text-[#F2EFE9] outline-none"
                                            autoFocus
                                            maxLength={120}
                                        />
                                        <button
                                            type="button"
                                            onClick={handleRename}
                                            className="border border-[#D95D24] bg-[#D95D24] px-3 py-1.5 font-mono text-xs font-semibold text-[#060606]"
                                        >
                                            Save
                                        </button>
                                    </div>
                                ) : (
                                    <div className="flex items-center gap-2.5">
                                        <h2 className="truncate text-lg font-medium text-[#F2EFE9]">
                                            {detail.name}
                                        </h2>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setDraftName(detail.name);
                                                setIsRenaming(true);
                                            }}
                                            className="font-mono text-[11px] text-[#6E675F] hover:text-[#F2EFE9]"
                                        >
                                            rename
                                        </button>
                                    </div>
                                )}

                                {/* Subtle progress bar */}
                                <div className="mt-3 flex items-center gap-3">
                                    <div className="h-[3px] flex-1 bg-[#F2EFE9]/10">
                                        <div
                                            className="h-full bg-[#D95D24] transition-all duration-300"
                                            style={{ width: `${percent}%` }}
                                        />
                                    </div>
                                    <span className="shrink-0 font-mono text-[11px] text-[#8E867D]">
                                        {completed}/{topics.length} · {percent}%
                                    </span>
                                </div>
                            </div>

                            <button
                                type="button"
                                onClick={onClose}
                                className="shrink-0 border border-[#F2EFE9]/14 px-3 py-1 font-mono text-xs text-[#8E867D] hover:border-[#D95D24] hover:text-[#F2EFE9]"
                            >
                                Close ×
                            </button>
                        </div>

                        {/* Clean 2-Tab Switcher */}
                        <div className="mt-4 flex items-center gap-4 font-mono text-xs">
                            <button
                                type="button"
                                onClick={() => setTab('topics')}
                                className={`border-b pb-1.5 transition-colors ${
                                    tab === 'topics'
                                        ? 'border-[#D95D24] text-[#F2EFE9]'
                                        : 'border-transparent text-[#7D756C] hover:text-[#F2EFE9]'
                                }`}
                            >
                                Topics ({topics.length})
                            </button>
                            <button
                                type="button"
                                onClick={() => setTab('folder')}
                                className={`border-b pb-1.5 transition-colors ${
                                    tab === 'folder'
                                        ? 'border-[#D95D24] text-[#F2EFE9]'
                                        : 'border-transparent text-[#7D756C] hover:text-[#F2EFE9]'
                                }`}
                            >
                                Code Folder
                                {pendingSuggestionsCount > 0 && (
                                    <span className="ml-1.5 text-[#D95D24]">({pendingSuggestionsCount})</span>
                                )}
                            </button>
                        </div>
                    </div>

                    {/* Body */}
                    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5 sm:px-7">
                        {error && (
                            <div className="mb-4 border border-[#D95D24]/60 bg-[#1B0E09] px-3.5 py-2.5 font-mono text-xs text-[#F2EFE9]">
                                {error}
                            </div>
                        )}

                        {tab === 'topics' ? (
                            <div className="space-y-3">
                                {loading ? (
                                    <p className="py-12 text-center font-mono text-xs text-[#7D756C]">
                                        Loading topics…
                                    </p>
                                ) : topics.length === 0 ? (
                                    <div className="py-12 text-center">
                                        <p className="text-sm text-[#8E867D]">No topics in this roadmap yet.</p>
                                        <p className="mt-1 text-xs text-[#5C564F]">
                                            Add one below to start tracking your progress.
                                        </p>
                                    </div>
                                ) : (
                                    <div className="divide-y divide-[#F2EFE9]/10 border border-[#F2EFE9]/12 bg-[#060606]">
                                        {topics.map((topic) => {
                                            const locked = !topic.available;
                                            const style = STATUS_STYLE[topic.status] || STATUS_STYLE.not_started;
                                            const nextStatus = NEXT_STATUS[topic.status] || 'learning';
                                            return (
                                                <div
                                                    key={topic.id}
                                                    className={`group flex items-center justify-between gap-3 px-4 py-3.5 transition-colors hover:bg-[#0E0D0C] ${
                                                        locked ? 'opacity-55' : ''
                                                    }`}
                                                >
                                                    <div className="flex min-w-0 flex-1 items-center gap-3.5">
                                                        <button
                                                            type="button"
                                                            disabled={busy || locked}
                                                            onClick={() => handleStatus(topic, nextStatus)}
                                                            title={locked ? 'Complete prerequisites first' : `Click to mark as ${nextStatus.replace('_', ' ')}`}
                                                            className={`shrink-0 border px-2 py-0.5 font-mono text-[11px] transition-colors disabled:cursor-not-allowed ${style.cls}`}
                                                        >
                                                            {style.symbol} {style.label}
                                                        </button>

                                                        <div className="min-w-0 flex-1">
                                                            <p className={`truncate text-sm ${topic.status === 'completed' ? 'line-through text-[#7D756C]' : 'text-[#F2EFE9]'}`}>
                                                                {topic.name}
                                                            </p>
                                                            {locked && topic.unmetPrerequisites?.length > 0 && (
                                                                <p className="mt-0.5 truncate font-mono text-[10px] text-[#7D756C]">
                                                                    Requires: {topic.unmetPrerequisites.join(', ')}
                                                                </p>
                                                            )}
                                                        </div>
                                                    </div>

                                                    <button
                                                        type="button"
                                                        disabled={busy}
                                                        onClick={() => handleDeleteTopic(topic)}
                                                        className="shrink-0 px-1.5 py-0.5 font-mono text-xs text-[#5C564F] opacity-0 transition-opacity hover:text-[#D95D24] group-hover:opacity-100"
                                                        title="Delete topic"
                                                    >
                                                        ×
                                                    </button>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        ) : (
                            /* Dedicated Code Folder & Hybrid RAG Tab */
                            <div className="space-y-5">
                                {!insights?.folder ? (
                                    <div className="border border-[#F2EFE9]/12 bg-[#060606] p-5 space-y-4">
                                        <p className="text-sm leading-relaxed text-[#A8A096]">
                                            Link a local practice folder so ORBIT can track your code files and let you search your snippets.
                                        </p>
                                        <div className="flex flex-wrap items-center gap-3">
                                            <button
                                                type="button"
                                                onClick={handleBrowseFolder}
                                                disabled={pickingFolder || syncingFolder}
                                                className="border border-[#D95D24] bg-[#D95D24] px-4 py-2 font-mono text-xs font-semibold text-[#060606] hover:bg-[#E86B30] disabled:opacity-45"
                                            >
                                                {pickingFolder ? 'Selecting…' : syncingFolder ? 'Syncing…' : 'Choose Folder'}
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => setIsManualPathOpen((v) => !v)}
                                                className="font-mono text-xs text-[#8E867D] hover:text-[#F2EFE9]"
                                            >
                                                {isManualPathOpen ? 'Hide path input' : 'Enter path manually'}
                                            </button>
                                        </div>

                                        {isManualPathOpen && (
                                            <form onSubmit={handleLinkFolder} className="flex gap-2 pt-1">
                                                <input
                                                    type="text"
                                                    value={folderInput}
                                                    onChange={(e) => setFolderInput(e.target.value)}
                                                    placeholder="C:\path\to\practice\folder"
                                                    className="min-w-0 flex-1 border border-[#F2EFE9]/14 bg-[#0B0A09] px-3 py-2 font-mono text-xs text-[#F2EFE9] outline-none focus:border-[#D95D24]"
                                                    autoFocus
                                                />
                                                <button
                                                    type="submit"
                                                    disabled={!folderInput.trim() || syncingFolder}
                                                    className="border border-[#F2EFE9]/20 px-4 py-2 font-mono text-xs text-[#F2EFE9] hover:border-[#D95D24] disabled:opacity-40"
                                                >
                                                    Link
                                                </button>
                                            </form>
                                        )}
                                    </div>
                                ) : (
                                    <>
                                        <div className="border border-[#F2EFE9]/12 bg-[#060606] p-4 space-y-3">
                                            <div className="flex items-center justify-between gap-3">
                                                <p className="truncate font-mono text-xs text-[#CFC9BF]" title={insights.folder.folder_path}>
                                                    {insights.folder.folder_path}
                                                </p>
                                                <div className="flex shrink-0 items-center gap-2 font-mono text-[11px]">
                                                    <button
                                                        type="button"
                                                        onClick={handleSyncFolder}
                                                        disabled={syncingFolder}
                                                        className="border border-[#D95D24]/60 px-2.5 py-1 text-[#E87D42] hover:bg-[#D95D24] hover:text-[#060606]"
                                                    >
                                                        {syncingFolder ? 'Syncing…' : 'Sync'}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={handleOpenInExplorer}
                                                        className="text-[#8E867D] hover:text-[#F2EFE9]"
                                                    >
                                                        Open
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={handleUnlinkFolder}
                                                        className="text-[#8E867D] hover:text-[#D95D24]"
                                                    >
                                                        Unlink
                                                    </button>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-5 font-mono text-xs text-[#8E867D]">
                                                <span><strong className="text-[#F2EFE9]">{insights.practiced_count ?? 0}</strong> coded</span>
                                                <span><strong className="text-[#F2EFE9]">{insights.wip_count ?? 0}</strong> empty</span>
                                                <span><strong className="text-[#D95D24]">{pendingSuggestionsCount}</strong> ready</span>
                                            </div>

                                            {insights.files?.length > 0 && (
                                                <div>
                                                    <button
                                                        type="button"
                                                        onClick={() => setShowFiles((v) => !v)}
                                                        className="font-mono text-[11px] text-[#7D756C] hover:text-[#F2EFE9]"
                                                    >
                                                        {showFiles ? '▾ Hide files' : `▸ View ${insights.files.length} indexed files`}
                                                    </button>
                                                    {showFiles && (
                                                        <div className="mt-2 flex flex-wrap gap-1.5">
                                                            {insights.files.map((f) => (
                                                                <span
                                                                    key={f.rel_path}
                                                                    className="border border-[#F2EFE9]/12 bg-[#0B0A09] px-2 py-0.5 font-mono text-[10px] text-[#B5AEA4]"
                                                                >
                                                                    {f.rel_path}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>

                                        {pendingSuggestionsCount > 0 && (
                                            <div className="space-y-2">
                                                <p className="font-mono text-[11px] text-[#D95D24]">
                                                    Detected completions
                                                </p>
                                                {insights.pending_suggestions.map((s) => (
                                                    <div key={s.id} className="flex items-center justify-between gap-3 border border-[#D95D24]/40 bg-[#130C08] px-4 py-3">
                                                        <div className="min-w-0">
                                                            <p className="truncate text-sm text-[#F2EFE9]">{s.topic_name}</p>
                                                            <p className="truncate text-xs text-[#8E867D]">{s.reason}</p>
                                                        </div>
                                                        <div className="flex shrink-0 gap-2 font-mono text-xs">
                                                            <button
                                                                type="button"
                                                                onClick={() => handleResolveSuggestion(s.id, 'confirmed')}
                                                                disabled={busy}
                                                                className="border border-[#D95D24] bg-[#D95D24] px-2.5 py-1 font-semibold text-[#060606]"
                                                            >
                                                                Confirm
                                                            </button>
                                                            <button
                                                                type="button"
                                                                onClick={() => handleResolveSuggestion(s.id, 'dismissed')}
                                                                disabled={busy}
                                                                className="border border-[#F2EFE9]/16 px-2.5 py-1 text-[#8E867D] hover:text-[#F2EFE9]"
                                                            >
                                                                Skip
                                                            </button>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {/* Code Search */}
                                        <form onSubmit={handleRagSearch} className="flex gap-2">
                                            <input
                                                type="text"
                                                value={ragQuery}
                                                onChange={(e) => setRagQuery(e.target.value)}
                                                placeholder="Search inside your practice code…"
                                                className="min-w-0 flex-1 border border-[#F2EFE9]/14 bg-[#060606] px-3.5 py-2 font-mono text-xs text-[#F2EFE9] outline-none focus:border-[#D95D24]"
                                            />
                                            <button
                                                type="submit"
                                                disabled={!ragQuery.trim() || ragSearching}
                                                className="border border-[#F2EFE9]/16 px-4 py-2 font-mono text-xs text-[#F2EFE9] hover:border-[#D95D24] disabled:opacity-40"
                                            >
                                                {ragSearching ? '…' : 'Search'}
                                            </button>
                                        </form>

                                        {ragSearched && (
                                            <div className="space-y-2.5">
                                                {ragResults.length === 0 ? (
                                                    <p className="font-mono text-xs text-[#7D756C]">No matching code found.</p>
                                                ) : (
                                                    ragResults.map((hit) => (
                                                        <div key={hit.chunk_id} className="border border-[#F2EFE9]/12 bg-[#060606] p-3">
                                                            <div className="mb-1.5 font-mono text-[10px] text-[#D95D24]">
                                                                {hit.rel_path} · L{hit.start_line}–{hit.end_line}
                                                            </div>
                                                            <pre className="max-h-28 overflow-x-auto whitespace-pre-wrap font-mono text-[11px] text-[#D6D0C7]">
                                                                {hit.snippet}
                                                            </pre>
                                                        </div>
                                                    ))
                                                )}
                                            </div>
                                        )}
                                    </>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Minimal Footer for Adding Topics (only on Topics tab) */}
                    {tab === 'topics' && (
                        <div className="shrink-0 border-t border-[#F2EFE9]/10 px-6 py-4 sm:px-7">
                            {isAdding ? (
                                <form onSubmit={handleAddTopic} className="space-y-3">
                                    <textarea
                                        rows={2}
                                        value={newName}
                                        onChange={(e) => setNewName(e.target.value)}
                                        placeholder="Enter one topic or paste multiple lines…"
                                        className="w-full resize-none border border-[#F2EFE9]/16 bg-[#060606] px-3.5 py-2 text-sm text-[#F2EFE9] outline-none placeholder:text-[#5C564F] focus:border-[#D95D24]"
                                        autoFocus
                                    />
                                    <div className="flex justify-end gap-2 font-mono text-xs">
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setIsAdding(false);
                                                setNewName('');
                                            }}
                                            className="border border-[#F2EFE9]/14 px-3.5 py-1.5 text-[#8E867D] hover:text-[#F2EFE9]"
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            type="submit"
                                            disabled={!newName.trim() || busy}
                                            className="border border-[#D95D24] bg-[#D95D24] px-4 py-1.5 font-semibold text-[#060606] hover:bg-[#E86B30] disabled:opacity-40"
                                        >
                                            Add
                                        </button>
                                    </div>
                                </form>
                            ) : (
                                <button
                                    type="button"
                                    onClick={() => setIsAdding(true)}
                                    className="w-full border border-[#F2EFE9]/12 py-2 font-mono text-xs text-[#A8A096] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9]"
                                >
                                    + Add topic
                                </button>
                            )}
                        </div>
                    )}
                </motion.div>
            </div>
        </div>,
        document.body
    );
};

export default RoadmapDetail;
