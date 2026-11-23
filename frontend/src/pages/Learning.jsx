import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useAuth, useTheme } from '../context/AuthContext';
import { useAppData } from '../context/AppDataContext';
import { learningService } from '../services/learningService';
import { motion, AnimatePresence } from 'framer-motion';
import ConfirmationModal from '../components/ConfirmationModal';
import RoadmapDetail from '../components/learning/RoadmapDetail';
import SuggestedLinks from '../components/learning/SuggestedLinks';
import CodeSuggestions from '../components/learning/CodeSuggestions';

const CATEGORIES = ['technical', 'academic', 'personal'];

const Learning = () => {
    const { currentUser } = useAuth();
    const { theme } = useTheme();
    const { revision } = useAppData();

    const [activeTab, setActiveTab] = useState('roadmaps'); // 'roadmaps' | 'next'
    const [progress, setProgress] = useState(null);
    const [roadmaps, setRoadmaps] = useState([]);
    const [nextTopics, setNextTopics] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const [isCreateOpen, setIsCreateOpen] = useState(false);
    const [newName, setNewName] = useState('');
    const [newCategory, setNewCategory] = useState('technical');
    const [newTopicsText, setNewTopicsText] = useState('');
    const [autoSubtopics, setAutoSubtopics] = useState(true);
    const [roadmapToDelete, setRoadmapToDelete] = useState(null);
    const [selectedRoadmap, setSelectedRoadmap] = useState(null);
    const [busy, setBusy] = useState(false);

    const loadAll = useCallback(async () => {
        try {
            const [progressData, roadmapList, nextList] = await Promise.all([
                learningService.getProgress(),
                learningService.listRoadmaps(),
                learningService.getNext(),
            ]);
            setError('');
            setProgress(progressData);
            setRoadmaps(roadmapList);
            setNextTopics(nextList);
        } catch (loadError) {
            console.error('Error loading learning data:', loadError);
            setError(loadError.message || 'Could not load learning data.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!currentUser) return undefined;
        let cancelled = false;
        Promise.all([
            learningService.getProgress(),
            learningService.listRoadmaps(),
            learningService.getNext(),
        ])
            .then(([progressData, roadmapList, nextList]) => {
                if (cancelled) return;
                setError('');
                setProgress(progressData);
                setRoadmaps(roadmapList);
                setNextTopics(nextList);
                setLoading(false);
            })
            .catch((loadError) => {
                if (cancelled) return;
                setError(loadError.message || 'Could not load learning data.');
                setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [currentUser, revision]);

    const handleTopicsPasteChange = (val) => {
        setNewTopicsText(val);
        if (!newName.trim() && val.trim()) {
            const firstLine = val.trim().split(/\r?\n/)[0].trim();
            const headingMatch = firstLine.match(
                /^(?:here\s+are\s+)?(?:some\s+)?(?:short\s+|the\s+)?([A-Za-z0-9+#.\-/&\s]{1,50}?)\s+(?:headings?|sub[\s-]?topics?|topics?|roadmap|learning\s+path)/i
            );
            if (headingMatch?.[1]) {
                setNewName(headingMatch[1].trim());
            } else if (firstLine.endsWith(':') && firstLine.length <= 50) {
                setNewName(firstLine.slice(0, -1).trim());
            }
        }
    };

    const detectedSubtopicsCount = newTopicsText
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter((l) => l && !/^(?:here\s+are\s+|create\s+|add\s+).*:$/i.test(l)).length;

    const handleCreateRoadmap = async (e) => {
        e.preventDefault();
        if ((!newName.trim() && !newTopicsText.trim()) || busy) return;
        setBusy(true);
        try {
            if (newTopicsText.trim() || autoSubtopics) {
                await learningService.importRoadmap({
                    name: newName.trim() || undefined,
                    category: newCategory,
                    raw_text: newTopicsText.trim() || undefined,
                    auto_subtopics: autoSubtopics,
                });
            } else {
                await learningService.createRoadmap({ name: newName.trim(), category: newCategory });
            }
            setNewName('');
            setNewTopicsText('');
            setNewCategory('technical');
            setIsCreateOpen(false);
            await loadAll();
        } catch (createError) {
            setError(createError.message);
        } finally {
            setBusy(false);
        }
    };

    const handleDeleteRoadmap = async () => {
        if (!roadmapToDelete || busy) return;
        const targetId = roadmapToDelete.id;
        setBusy(true);
        try {
            await learningService.deleteRoadmap(targetId);
        } catch (deleteError) {
            if (!String(deleteError.message || '').toLowerCase().includes('not found')) {
                setError(deleteError.message);
            }
        } finally {
            if (selectedRoadmap?.id === targetId) setSelectedRoadmap(null);
            setRoadmapToDelete(null);
            await loadAll();
            setBusy(false);
        }
    };

    const handleCompleteTopic = async (topic) => {
        try {
            await learningService.updateTopic(topic.topicId, { status: 'completed' });
            await loadAll();
        } catch (completeError) {
            setError(completeError.message);
        }
    };

    if (loading) {
        return (
            <div className="py-16 text-center font-mono text-xs text-[#7D756C]">
                Loading roadmaps…
            </div>
        );
    }

    const masteryPct = Math.round(progress?.completionPercent ?? 0);

    return (
        <div data-spidey-section="learning" className="space-y-6">
            {/* Calm Single-Row Controls: 2 clean tabs + quiet summary + New button */}
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-1 border border-[#F2EFE9]/12 bg-[#060606] p-1 font-mono text-xs">
                    <button
                        type="button"
                        onClick={() => setActiveTab('roadmaps')}
                        className={`px-3.5 py-1.5 transition-colors ${
                            activeTab === 'roadmaps'
                                ? 'bg-[#D95D24] font-semibold text-[#060606]'
                                : 'text-[#8E867D] hover:text-[#F2EFE9]'
                        }`}
                    >
                        Roadmaps ({roadmaps.length})
                    </button>
                    <button
                        type="button"
                        onClick={() => setActiveTab('next')}
                        className={`px-3.5 py-1.5 transition-colors ${
                            activeTab === 'next'
                                ? 'bg-[#D95D24] font-semibold text-[#060606]'
                                : 'text-[#8E867D] hover:text-[#F2EFE9]'
                        }`}
                    >
                        Up Next ({nextTopics.length})
                    </button>
                </div>

                <div className="flex items-center gap-4">
                    {progress && (
                        <span className="hidden font-mono text-xs text-[#7D756C] sm:inline">
                            {progress.completedTopics}/{progress.topicCount} done · {masteryPct}%
                        </span>
                    )}
                    <button
                        type="button"
                        onClick={() => setIsCreateOpen(true)}
                        className="border border-[#D95D24] bg-[#D95D24] px-4 py-2 font-mono text-xs font-semibold text-[#060606] transition-colors hover:bg-[#E86B30]"
                    >
                        + New roadmap
                    </button>
                </div>
            </div>

            {error && (
                <div className="border border-[#D95D24]/60 bg-[#1B0E09] px-4 py-3 font-mono text-xs text-[#F2EFE9]">
                    {error}
                </div>
            )}

            {/* TAB 1: Clean, Spacious Roadmaps Grid */}
            {activeTab === 'roadmaps' ? (
                roadmaps.length === 0 ? (
                    <div className="border border-[#F2EFE9]/10 bg-[#060606] px-6 py-16 text-center">
                        <p className="text-sm text-[#A8A096]">No learning roadmaps yet.</p>
                        <p className="mt-1.5 text-xs text-[#6E675F]">
                            Create one to track topics step by step, or ask ORBIT in chat.
                        </p>
                        <button
                            type="button"
                            onClick={() => setIsCreateOpen(true)}
                            className="mt-5 border border-[#D95D24] bg-[#D95D24]/12 px-4 py-2 font-mono text-xs text-[#F2EFE9] hover:bg-[#D95D24] hover:text-[#060606]"
                        >
                            + Create first roadmap
                        </button>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        <AnimatePresence>
                            {roadmaps.map((roadmap) => {
                                const pct = Math.round(roadmap.completionPercent ?? 0);
                                return (
                                    <motion.div
                                        key={roadmap.id}
                                        layout
                                        initial={{ opacity: 0, y: 6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0 }}
                                        onClick={() => setSelectedRoadmap(roadmap)}
                                        className="group flex cursor-pointer flex-col justify-between gap-4 border border-[#F2EFE9]/12 bg-[#0C0B0A] p-5 transition-colors hover:border-[#D95D24]/65"
                                    >
                                        <div className="flex items-start justify-between gap-3">
                                            <div className="min-w-0">
                                                <h3 className="truncate text-[15px] font-medium text-[#F2EFE9]">
                                                    {roadmap.name}
                                                </h3>
                                                <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-[#7D756C]">
                                                    {roadmap.category}
                                                    {roadmap.folderLink ? ' · folder linked' : ''}
                                                </p>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setRoadmapToDelete(roadmap);
                                                }}
                                                className="shrink-0 px-1.5 py-0.5 font-mono text-[11px] text-[#5C564F] opacity-0 transition-opacity hover:text-[#D95D24] group-hover:opacity-100"
                                                title="Delete roadmap"
                                            >
                                                ×
                                            </button>
                                        </div>

                                        <div className="space-y-2">
                                            <div className="flex items-center justify-between font-mono text-[11px]">
                                                <span className="text-[#8E867D]">
                                                    {roadmap.completedCount} / {roadmap.topicCount} topics
                                                </span>
                                                <span className="text-[#D95D24]">{pct}%</span>
                                            </div>
                                            <div className="h-[3px] w-full bg-[#F2EFE9]/10">
                                                <div
                                                    className="h-full bg-[#D95D24] transition-all duration-300"
                                                    style={{ width: `${pct}%` }}
                                                />
                                            </div>
                                        </div>

                                        {roadmap.nextTopic && (
                                            <p className="truncate text-xs text-[#7D756C]">
                                                Next: <span className="text-[#CFC9BF]">{roadmap.nextTopic}</span>
                                            </p>
                                        )}
                                    </motion.div>
                                );
                            })}
                        </AnimatePresence>
                    </div>
                )
            ) : (
                /* TAB 2: Up Next + Quiet Sync Reviews */
                <div className="space-y-6">
                    {nextTopics.length === 0 ? (
                        <div className="border border-[#F2EFE9]/10 bg-[#060606] py-12 text-center text-xs text-[#7D756C]">
                            All queued topics are complete.
                        </div>
                    ) : (
                        <div className="divide-y divide-[#F2EFE9]/10 border border-[#F2EFE9]/12 bg-[#0B0A09]">
                            {nextTopics.map((topic) => (
                                <div
                                    key={topic.topicId}
                                    className="flex items-center justify-between gap-4 px-4 py-3.5 transition-colors hover:bg-[#110F0D]"
                                >
                                    <div className="min-w-0">
                                        <p className="truncate text-sm text-[#F2EFE9]">{topic.name}</p>
                                        <p className="mt-0.5 truncate font-mono text-[11px] text-[#7D756C]">
                                            {topic.roadmapName}
                                        </p>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => handleCompleteTopic(topic)}
                                        className="shrink-0 border border-[#F2EFE9]/16 px-3 py-1 font-mono text-[11px] text-[#A8A096] hover:border-[#D95D24] hover:text-[#D95D24]"
                                    >
                                        Mark done
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}

                    <CodeSuggestions
                        onChanged={loadAll}
                        hasLinkedFolders={roadmaps.some((r) => Boolean(r.folderLink))}
                    />
                    <SuggestedLinks onChanged={loadAll} />
                </div>
            )}

            {/* Calm Centered New Roadmap Pop-Up */}
            {createPortal(
                <div className={`app-theme-${theme}`}>
                    <AnimatePresence>
                        {isCreateOpen && (
                            <div role="dialog" aria-modal="true" className="fixed inset-0 z-[120] flex items-center justify-center bg-black/80 p-4 backdrop-blur-[2px]">
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: 6 }}
                                    className="ascii-frame relative w-full max-w-md bg-[#0A0908] p-6 text-[#F2EFE9]"
                                >
                                    <div className="mb-5 flex items-center justify-between">
                                        <h3 className="text-base font-medium text-[#F2EFE9]">New Roadmap</h3>
                                        <button
                                            type="button"
                                            onClick={() => setIsCreateOpen(false)}
                                            className="font-mono text-xs text-[#8E867D] hover:text-[#F2EFE9]"
                                        >
                                            ×
                                        </button>
                                    </div>

                                    <form onSubmit={handleCreateRoadmap} className="space-y-4">
                                        <div>
                                            <label className="mb-1.5 block font-mono text-[11px] text-[#8E867D]">
                                                Title
                                            </label>
                                            <input
                                                type="text"
                                                value={newName}
                                                onChange={(e) => setNewName(e.target.value)}
                                                placeholder="e.g. Python, System Design, Calculus"
                                                className="w-full border border-[#F2EFE9]/14 bg-[#060606] px-3.5 py-2.5 text-sm text-[#F2EFE9] outline-none placeholder:text-[#5C564F] focus:border-[#D95D24]"
                                                autoFocus
                                            />
                                        </div>

                                        <div>
                                            <div className="mb-1.5 flex items-center justify-between font-mono text-[11px]">
                                                <label className="text-[#8E867D]">Topics (optional, one per line)</label>
                                                {detectedSubtopicsCount > 0 && (
                                                    <span className="text-[#D95D24]">{detectedSubtopicsCount} topics</span>
                                                )}
                                            </div>
                                            <textarea
                                                rows={4}
                                                value={newTopicsText}
                                                onChange={(e) => handleTopicsPasteChange(e.target.value)}
                                                placeholder={"Paste topics here or leave blank to auto-generate…"}
                                                className="w-full resize-y border border-[#F2EFE9]/14 bg-[#060606] px-3.5 py-2.5 font-mono text-xs text-[#F2EFE9] outline-none placeholder:text-[#5C564F] focus:border-[#D95D24]"
                                            />
                                            <label className="mt-2 flex cursor-pointer items-center gap-2 text-xs text-[#8E867D] select-none">
                                                <input
                                                    type="checkbox"
                                                    checked={autoSubtopics}
                                                    onChange={(e) => setAutoSubtopics(e.target.checked)}
                                                    className="accent-[#D95D24]"
                                                />
                                                <span>Auto-generate sub-topics if blank</span>
                                            </label>
                                        </div>

                                        <div className="grid grid-cols-3 gap-2 font-mono text-xs">
                                            {CATEGORIES.map((category) => (
                                                <button
                                                    key={category}
                                                    type="button"
                                                    onClick={() => setNewCategory(category)}
                                                    className={`border py-2 capitalize transition-colors ${
                                                        newCategory === category
                                                            ? 'border-[#D95D24] bg-[#D95D24] font-semibold text-[#060606]'
                                                            : 'border-[#F2EFE9]/14 bg-[#060606] text-[#8E867D] hover:text-[#F2EFE9]'
                                                    }`}
                                                >
                                                    {category}
                                                </button>
                                            ))}
                                        </div>

                                        <div className="flex gap-2.5 pt-2 font-mono text-xs">
                                            <button
                                                type="button"
                                                onClick={() => setIsCreateOpen(false)}
                                                className="flex-1 border border-[#F2EFE9]/14 py-2.5 text-[#8E867D] hover:text-[#F2EFE9]"
                                            >
                                                Cancel
                                            </button>
                                            <button
                                                type="submit"
                                                disabled={(!newName.trim() && !newTopicsText.trim()) || busy}
                                                className="flex-1 border border-[#D95D24] bg-[#D95D24] py-2.5 font-semibold text-[#060606] hover:bg-[#E86B30] disabled:opacity-40"
                                            >
                                                {busy ? 'Creating…' : 'Create'}
                                            </button>
                                        </div>
                                    </form>
                                </motion.div>
                            </div>
                        )}
                    </AnimatePresence>
                </div>,
                document.body
            )}

            <ConfirmationModal
                isOpen={Boolean(roadmapToDelete)}
                onClose={() => setRoadmapToDelete(null)}
                onConfirm={handleDeleteRoadmap}
                title="Delete roadmap"
                message={`Delete "${roadmapToDelete?.name ?? ''}" and all of its topics?`}
                type="danger"
                confirmString={roadmapToDelete?.name}
            />

            {selectedRoadmap && (
                <RoadmapDetail
                    roadmap={selectedRoadmap}
                    onClose={() => setSelectedRoadmap(null)}
                    onChanged={loadAll}
                />
            )}
        </div>
    );
};

export default Learning;
