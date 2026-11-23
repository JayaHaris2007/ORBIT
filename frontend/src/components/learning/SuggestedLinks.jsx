import { useState, useEffect, useRef } from 'react';
import { learningService } from '../../services/learningService';
import { useAppData } from '../../context/AppDataContext';

const SuggestedLinks = ({ onChanged }) => {
    const { revision } = useAppData();
    const [links, setLinks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [scanning, setScanning] = useState(false);
    const [error, setError] = useState('');
    const [busyId, setBusyId] = useState(null);
    const autoScannedRef = useRef(false);

    useEffect(() => {
        let cancelled = false;
        const run = async () => {
            try {
                let items = await learningService.listSuggestedLinks();
                if (items.length === 0 && !autoScannedRef.current) {
                    autoScannedRef.current = true;
                    try {
                        items = await learningService.scanSuggestedLinks();
                    } catch { /* ignore */ }
                }
                if (!cancelled) {
                    setLinks(items);
                    setError('');
                    setLoading(false);
                }
            } catch (loadError) {
                if (!cancelled) {
                    setError(loadError.message || 'Could not load task links.');
                    setLoading(false);
                }
            }
        };
        run();
        return () => { cancelled = true; };
    }, [revision]);

    const handleScan = async () => {
        setScanning(true);
        setError('');
        try {
            const items = await learningService.scanSuggestedLinks();
            setLinks(items);
        } catch (scanError) {
            setError(scanError.message || 'Could not scan tasks.');
        } finally {
            setScanning(false);
        }
    };

    const handleAction = async (link, patch) => {
        setBusyId(link.id);
        setError('');
        try {
            await learningService.updateLink(link.id, patch);
            setLinks((current) => current.filter((item) => item.id !== link.id));
            onChanged?.();
        } catch (actionError) {
            setError(actionError.message);
        } finally {
            setBusyId(null);
        }
    };

    if (loading || links.length === 0) return null;

    return (
        <section className="space-y-3">
            <div className="flex items-center justify-between font-mono text-xs">
                <span className="text-[#8E867D]">Suggested task links ({links.length})</span>
                <button
                    type="button"
                    onClick={handleScan}
                    disabled={scanning}
                    className="text-[11px] text-[#7D756C] hover:text-[#F2EFE9]"
                >
                    {scanning ? 'Scanning…' : 'Rescan'}
                </button>
            </div>

            {error && <p className="font-mono text-xs text-[#D95D24]">{error}</p>}

            <div className="divide-y divide-[#F2EFE9]/10 border border-[#F2EFE9]/12 bg-[#0B0A09]">
                {links.map((link) => (
                    <div key={link.id} className="flex items-center justify-between gap-4 px-4 py-3">
                        <div className="min-w-0">
                            <p className="truncate text-sm text-[#F2EFE9]">{link.taskTitle}</p>
                            <p className="truncate font-mono text-[11px] text-[#7D756C]">
                                → {link.topicName} · {link.roadmapName}
                            </p>
                        </div>
                        <div className="flex shrink-0 gap-2 font-mono text-xs">
                            <button
                                type="button"
                                onClick={() => handleAction(link, { state: 'confirmed' })}
                                disabled={busyId === link.id}
                                className="border border-[#D95D24] bg-[#D95D24] px-3 py-1 font-semibold text-[#060606]"
                            >
                                Link
                            </button>
                            <button
                                type="button"
                                onClick={() => handleAction(link, { state: 'rejected' })}
                                disabled={busyId === link.id}
                                className="border border-[#F2EFE9]/14 px-2.5 py-1 text-[#8E867D] hover:text-[#F2EFE9]"
                            >
                                Dismiss
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
};

export default SuggestedLinks;
