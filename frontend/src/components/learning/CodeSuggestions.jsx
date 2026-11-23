import { useState, useEffect, useCallback } from 'react';
import { learningService } from '../../services/learningService';
import { useAppData } from '../../context/AppDataContext';

const CodeSuggestions = ({ onChanged, hasLinkedFolders = false }) => {
    const { revision } = useAppData();
    const [suggestions, setSuggestions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [syncing, setSyncing] = useState(false);
    const [busyId, setBusyId] = useState(null);
    const [error, setError] = useState('');

    useEffect(() => {
        let cancelled = false;
        learningService.listCodeSuggestions()
            .then((items) => {
                if (!cancelled) {
                    setSuggestions(items);
                    setError('');
                    setLoading(false);
                }
            })
            .catch((err) => {
                if (!cancelled) {
                    setError(err.message || 'Could not load code suggestions.');
                    setLoading(false);
                }
            });
        return () => { cancelled = true; };
    }, [revision]);

    const handleSyncAll = useCallback(async () => {
        setSyncing(true);
        setError('');
        try {
            const res = await learningService.syncAllFolders();
            setSuggestions(res.suggestions ?? []);
            onChanged?.();
        } catch (err) {
            setError(err.message || 'Could not sync folders.');
        } finally {
            setSyncing(false);
        }
    }, [onChanged]);

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

    if (loading || (!hasLinkedFolders && suggestions.length === 0)) {
        return null;
    }

    if (suggestions.length === 0) {
        return (
            <div className="flex items-center justify-between border border-[#F2EFE9]/10 bg-[#0B0A09] px-4 py-3 font-mono text-xs text-[#7D756C]">
                <span>Linked code folders are synced.</span>
                <button
                    type="button"
                    onClick={handleSyncAll}
                    disabled={syncing}
                    className="border border-[#F2EFE9]/14 px-2.5 py-1 text-[11px] text-[#A8A096] hover:border-[#D95D24] hover:text-[#F2EFE9]"
                >
                    {syncing ? 'Syncing…' : 'Sync now'}
                </button>
            </div>
        );
    }

    return (
        <section className="space-y-3">
            <div className="flex items-center justify-between font-mono text-xs">
                <span className="text-[#D95D24]">Code folder completions ({suggestions.length})</span>
                <button
                    type="button"
                    onClick={handleSyncAll}
                    disabled={syncing}
                    className="text-[11px] text-[#8E867D] hover:text-[#F2EFE9]"
                >
                    {syncing ? 'Syncing…' : 'Refresh'}
                </button>
            </div>

            {error && <p className="font-mono text-xs text-[#D95D24]">{error}</p>}

            <div className="divide-y divide-[#F2EFE9]/10 border border-[#D95D24]/35 bg-[#0C0A09]">
                {suggestions.map((item) => (
                    <div key={item.id} className="flex items-center justify-between gap-4 px-4 py-3">
                        <div className="min-w-0">
                            <p className="truncate text-sm text-[#F2EFE9]">{item.topicName}</p>
                            <p className="truncate font-mono text-[11px] text-[#7D756C]">
                                {item.roadmapName} · {item.reason}
                            </p>
                        </div>
                        <div className="flex shrink-0 gap-2 font-mono text-xs">
                            <button
                                type="button"
                                onClick={() => handleResolve(item, 'confirmed')}
                                disabled={busyId === item.id}
                                className="border border-[#D95D24] bg-[#D95D24] px-3 py-1 font-semibold text-[#060606]"
                            >
                                Confirm
                            </button>
                            <button
                                type="button"
                                onClick={() => handleResolve(item, 'dismissed')}
                                disabled={busyId === item.id}
                                className="border border-[#F2EFE9]/14 px-2.5 py-1 text-[#8E867D] hover:text-[#F2EFE9]"
                            >
                                Skip
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
};

export default CodeSuggestions;
