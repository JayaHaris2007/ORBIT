import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Headphones, X, Square, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import NeuralBrainCanvas from '../three/NeuralBrainCanvas';
import SpiderMark from '../brand/SpiderMark';

const STATE_BADGES = {
    listening: {
        label: 'Listening',
        pill: 'border-[#D95D24] bg-[#D95D24] text-[#111111]',
        dot: 'bg-[#111111]',
    },
    transcribing: {
        label: 'Transcribing',
        pill: 'border-[#D95D24]/70 bg-[#1B1612] text-[#F2EFE9]',
        dot: 'bg-[#D95D24]',
    },
    thinking: {
        label: 'Processing',
        pill: 'border-[#F2EFE9] bg-[#F2EFE9] text-[#111111]',
        dot: 'bg-[#D95D24]',
    },
    speaking: {
        label: 'Speaking',
        pill: 'border-[#F2EFE9]/50 bg-[#1A1917] text-[#F2EFE9]',
        dot: 'bg-[#D95D24]',
    },
    idle: {
        label: 'Standby',
        pill: 'border-[#F2EFE9]/20 bg-[#151515] text-[#9C968E]',
        dot: 'bg-[#9C968E]',
    },
};

export default function LiveOverlay({
    isOpen,
    state = 'idle',
    transcript = '',
    reply = '',
    timing = {},
    error = null,
    onStopTurn,
    onClose,
}) {
    const [showDebug, setShowDebug] = useState(false);

    if (!isOpen) return null;

    const badge = STATE_BADGES[state] || STATE_BADGES.idle;

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                className="fixed inset-0 z-50 flex flex-col items-center justify-between bg-[#111111]/98 p-6"
            >
                {/* Header */}
                <div className="relative z-10 flex w-full max-w-2xl items-center justify-between border-b border-[#F2EFE9]/15 pb-4">
                    <div className="flex items-center gap-3">
                        <SpiderMark size={30} state={state} animateEntrance={false} />
                        <span className="font-mono text-xs font-bold uppercase tracking-[0.22em] text-[#F2EFE9]">
                            S.P.I.D.E.Y. Live Core
                        </span>
                        <span className={`inline-flex items-center gap-1.5 border px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] ${badge.pill}`}>
                            <span className={`h-1.5 w-1.5 ${badge.dot}`} />
                            {badge.label}
                        </span>
                    </div>

                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            onClick={() => setShowDebug(!showDebug)}
                            className="flex items-center gap-1.5 border border-[#F2EFE9]/15 bg-[#151515] px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9C968E] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9]"
                            title="Toggle latency diagnostics"
                        >
                            <Clock size={12} />
                            <span>Stats</span>
                            {showDebug ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                        </button>

                        <button
                            type="button"
                            onClick={onClose}
                            className="grid h-8 w-8 place-items-center border border-[#F2EFE9]/15 bg-[#151515] text-[#9C968E] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9]"
                            aria-label="End live session"
                        >
                            <X size={15} />
                        </button>
                    </div>
                </div>

                {/* Center 3D Neural Particle Sphere */}
                <div className="relative z-10 my-auto flex w-full max-w-2xl flex-col items-center justify-center">
                    <div className="relative flex h-[280px] w-[280px] items-center justify-center sm:h-[340px] sm:w-[340px]">
                        <div className="pointer-events-none absolute inset-4 rounded-full border border-[#F2EFE9]/12" />
                        <div className="pointer-events-none absolute inset-12 rounded-full border border-[#D95D24]/25" />
                        <NeuralBrainCanvas
                            size="overlay"
                            stateOverride={state}
                            className="h-full w-full"
                        />
                    </div>

                    {/* Speech Display */}
                    <div className="mt-4 max-w-lg text-center">
                        {error && (
                            <p className="mb-3 border border-[#D95D24] bg-[#1E130F] px-3.5 py-2 font-mono text-xs text-[#F2EFE9]">
                                {error}
                            </p>
                        )}
                        {transcript && (
                            <p className="font-mono text-xs italic text-[#9C968E]">
                                &ldquo;{transcript}&rdquo;
                            </p>
                        )}
                        {reply && (
                            <p className="mt-2 border border-[#F2EFE9]/15 bg-[#151515] px-4 py-3 text-sm font-medium leading-relaxed text-[#F2EFE9]">
                                {reply}
                            </p>
                        )}
                    </div>
                </div>

                {/* Debug Panel */}
                {showDebug && (
                    <motion.div
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                        className="relative z-10 mb-4 w-full max-w-md border border-[#F2EFE9]/15 bg-[#151515] p-3 font-mono text-[11px] text-[#9C968E]"
                    >
                        <div className="grid grid-cols-2 gap-2">
                            <div>Speech &rarr; Transcript: <span className="text-[#D95D24]">{timing.transcript || 0} ms</span></div>
                            <div>Transcript &rarr; Reply: <span className="text-[#D95D24]">{timing.firstSentence || 0} ms</span></div>
                            <div>Sentence &rarr; Audio: <span className="text-[#D95D24]">{timing.firstAudio || 0} ms</span></div>
                            <div className="font-bold text-[#F2EFE9]">Total Turn: <span className="text-[#D95D24]">{timing.total || 0} ms</span></div>
                        </div>
                    </motion.div>
                )}

                {/* Footer Controls */}
                <div className="relative z-10 flex w-full max-w-2xl flex-col items-center gap-3 border-t border-[#F2EFE9]/15 pt-4">
                    <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9C968E]">
                        <Headphones size={12} className="text-[#D95D24]" />
                        <span>Wear headphones for barge-in echo suppression</span>
                    </div>

                    <div className="flex items-center gap-3">
                        <button
                            type="button"
                            onClick={onStopTurn}
                            className="flex items-center gap-1.5 border border-[#D95D24] bg-[#D95D24] px-4 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-[#111111] transition-colors hover:bg-[#C44E19]"
                        >
                            <Square size={12} className="fill-current" />
                            <span>Stop Turn</span>
                        </button>

                        <button
                            type="button"
                            onClick={onClose}
                            className="border border-[#F2EFE9]/25 bg-[#151515] px-5 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-[#F2EFE9] transition-colors hover:border-[#D95D24] hover:text-[#D95D24]"
                        >
                            End Session
                        </button>
                    </div>
                </div>
            </motion.div>
        </AnimatePresence>
    );
}
