import { lazy, Suspense, useState } from 'react';
import { motion } from 'framer-motion';
import { Maximize2, Minimize2, Sparkles, X } from 'lucide-react';
import ErrorBoundary from '../ErrorBoundary';
import { SECTION_META } from './sectionMeta';

const SECTION_COMPONENTS = {
    tasks: lazy(() => import('../../pages/Todos')),
    habits: lazy(() => import('../../pages/Habits')),
    reminders: lazy(() => import('../../pages/RemindersMemory')),
    learning: lazy(() => import('../../pages/Learning')),
    analytics: lazy(() => import('../../pages/Analytics')),
    settings: lazy(() => import('../../pages/Settings')),
};

export default function SectionCanvasCard({ sectionId, onClose, onAskSpidey }) {
    const [expanded, setExpanded] = useState(false);
    const meta = SECTION_META[sectionId];
    const SectionComponent = SECTION_COMPONENTS[sectionId];
    if (!meta || !SectionComponent) return null;

    const Icon = meta.icon;

    return (
        <motion.section
            key={sectionId}
            data-spidey-anchor="section-card"
            initial={{ opacity: 0, y: 18, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.985 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            className={`mx-auto flex min-h-0 w-full flex-1 flex-col overflow-hidden rounded-2xl border border-[#F2EFE9]/12 bg-[#151515]/95 shadow-[0_24px_80px_rgba(0,0,0,0.6)] backdrop-blur-md transition-[max-width] duration-200 ${
                expanded ? 'max-w-6xl' : 'max-w-4xl'
            }`}
            aria-label={`${meta.label} focused panel`}
        >
            {/* Card Header Bar */}
            <header className="flex shrink-0 items-center justify-between gap-3 border-b border-[#F2EFE9]/10 bg-[#131313] px-4 py-3 sm:px-5">
                <div className="flex min-w-0 items-center gap-3">
                    <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-[#D95D24]/35 bg-[#D95D24]/15 text-[#D95D24]">
                        <Icon size={16} />
                    </div>
                    <div className="min-w-0">
                        <div className="flex items-center gap-2">
                            <h2 className="truncate text-sm font-semibold tracking-wide text-[#F2EFE9]">
                                {meta.label}
                            </h2>
                            <span className="hidden rounded border border-[#F2EFE9]/10 bg-[#1B1A18] px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.16em] text-[#9C968E] sm:inline-block">
                                {meta.code}
                            </span>
                        </div>
                        <p className="truncate text-[11px] text-[#9C968E]">{meta.subtitle}</p>
                    </div>
                </div>

                <div className="flex shrink-0 items-center gap-1.5">
                    {meta.askPrompt && onAskSpidey && (
                        <button
                            type="button"
                            onClick={() => onAskSpidey(meta.askPrompt)}
                            className="hidden items-center gap-1.5 rounded-lg border border-[#D95D24]/35 bg-[#D95D24]/12 px-2.5 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-[#E07A48] transition-colors hover:border-[#D95D24] hover:bg-[#D95D24]/20 hover:text-[#F2EFE9] sm:flex"
                            title="Ask S.P.I.D.E.Y about this section"
                        >
                            <Sparkles size={12} />
                            <span>Ask S.P.I.D.E.Y</span>
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={() => setExpanded((v) => !v)}
                        className="hidden h-8 w-8 place-items-center rounded-lg border border-[#F2EFE9]/10 bg-[#181715] text-[#9C968E] transition-colors hover:border-[#D95D24]/50 hover:text-[#F2EFE9] md:grid"
                        title={expanded ? 'Compact card width' : 'Expand card width'}
                        aria-label={expanded ? 'Compact card width' : 'Expand card width'}
                    >
                        {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                    </button>
                    <button
                        type="button"
                        onClick={onClose}
                        className="flex h-8 items-center gap-1 rounded-lg border border-[#F2EFE9]/10 bg-[#181715] px-2.5 text-xs text-[#9C968E] transition-colors hover:border-[#D95D24]/60 hover:text-[#F2EFE9]"
                        title="Back to chat (Esc)"
                        aria-label="Close section card"
                    >
                        <X size={14} />
                        <span className="hidden font-mono text-[10px] uppercase tracking-[0.12em] sm:inline">Chat</span>
                    </button>
                </div>
            </header>

            {/* Card Content Area */}
            <div className="spidey-section-card-body min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6 sm:py-5">
                <ErrorBoundary resetKey={sectionId}>
                    <Suspense
                        fallback={
                            <div className="flex h-52 items-center justify-center font-mono text-xs uppercase tracking-[0.18em] text-[#9C968E] animate-pulse">
                                Loading {meta.label}...
                            </div>
                        }
                    >
                        <SectionComponent />
                    </Suspense>
                </ErrorBoundary>
            </div>
        </motion.section>
    );
}
