import { lazy, Suspense } from 'react';
import { motion } from 'framer-motion';
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
    const meta = SECTION_META[sectionId];
    const SectionComponent = SECTION_COMPONENTS[sectionId];
    if (!meta || !SectionComponent) return null;

    return (
        <motion.section
            key={sectionId}
            initial={{ opacity: 0, y: 12, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.99 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="ascii-frame flex max-h-[84dvh] min-h-0 w-full flex-col overflow-hidden bg-[#090807] shadow-[0_24px_80px_rgba(0,0,0,0.85)]"
            aria-label={`${meta.label} pop-up`}
        >
            {/* Calm Minimal Pop-Up Header */}
            <header className="flex shrink-0 items-center justify-between gap-4 border-b border-[#F2EFE9]/10 px-6 py-4">
                <div className="min-w-0">
                    <h2 className="truncate text-base font-medium tracking-wide text-[#F2EFE9]">
                        {meta.label}
                    </h2>
                    <p className="mt-0.5 truncate text-xs text-[#7D756C]">{meta.subtitle}</p>
                </div>

                <div className="flex shrink-0 items-center gap-2 font-mono text-xs">
                    {meta.askPrompt && onAskSpidey && (
                        <button
                            type="button"
                            onClick={() => onAskSpidey(meta.askPrompt)}
                            className="hidden border border-[#F2EFE9]/14 px-3 py-1.5 text-[11px] text-[#A8A096] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9] sm:inline-block"
                        >
                            Ask ORBIT
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={onClose}
                        className="border border-[#F2EFE9]/14 px-3 py-1.5 text-[11px] text-[#8E867D] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9]"
                        title="Close (Esc)"
                    >
                        Close ×
                    </button>
                </div>
            </header>

            {/* Spacious Scrollable Body */}
            <div className="spidey-section-card-body min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-8 sm:py-7">
                <ErrorBoundary resetKey={sectionId}>
                    <Suspense
                        fallback={
                            <div className="flex h-44 items-center justify-center font-mono text-xs text-[#7D756C]">
                                Loading {meta.label}…
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
