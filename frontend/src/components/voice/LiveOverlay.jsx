import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { motion } from 'framer-motion';
import { useSpideyBrain } from '../../context/SpideyBrainContext';
import { getSharedAudioQueue } from '../../services/voiceService';
import { cleanAssistantText } from '../../utils/textUtils';

const STATE_META = {
    connecting: {
        label: 'CONNECTING',
        hint: 'Opening microphone and live channel…',
        pill: 'border-[#D95D24]/60 bg-[#140D09] text-[#FF944D]',
        dot: 'animate-pulse bg-[#FF944D]',
    },
    listening: {
        label: 'LISTENING',
        hint: 'Speak naturally — ORBIT listens continuously',
        pill: 'border-[#D95D24] bg-[#D95D24] text-[#060606]',
        dot: 'animate-pulse bg-[#060606]',
    },
    muted: {
        label: 'MUTED',
        hint: 'Microphone paused — press M or click unmute to resume',
        pill: 'border-[#F2EFE9]/25 bg-[#11100E] text-[#A8A096]',
        dot: 'bg-[#7D756C]',
    },
    transcribing: {
        label: 'TRANSCRIBING',
        hint: 'Transcribing your voice…',
        pill: 'border-[#D95D24]/75 bg-[#1B110B] text-[#FFD4A8]',
        dot: 'animate-pulse bg-[#FF944D]',
    },
    thinking: {
        label: 'THINKING',
        hint: 'ORBIT is composing a reply…',
        pill: 'border-[#F2EFE9]/75 bg-[#F2EFE9] text-[#060606]',
        dot: 'bg-[#D95D24]',
    },
    speaking: {
        label: 'SPEAKING',
        hint: 'Press Space or click [interrupt] anytime to cut in',
        pill: 'border-[#FF944D]/80 bg-[#1A100A] text-[#FFD4A8]',
        dot: 'animate-pulse bg-[#D95D24]',
    },
    idle: {
        label: 'STANDBY',
        hint: 'Live session ready',
        pill: 'border-[#F2EFE9]/20 bg-[#0D0C0B] text-[#8E867D]',
        dot: 'bg-[#6E675F]',
    },
};

/**
 * High-contrast 100% Pure ASCII Symmetric Harmonic Voice Matrix rendered inside
 * a dedicated solid obsidian (#060606) stage so it matches S.P.I.D.E.Y's ASCII
 * aesthetic with zero visual blending into the background terrain.
 */
const ASCII_RAMP = ' .:-=+*#%@';
const EMBER_PALETTE = [
    '#1F1C19', '#38332E', '#595149', '#8A8076', '#CFC9BF',
    '#7A2F10', '#B34517', '#D95D24', '#FF8A3D', '#FFD4A8',
];

export function LiveVoiceWave({ state = 'listening', isMuted = false, brainRef = null }) {
    const canvasRef = useRef(null);
    const stateRef = useRef(state);
    const mutedRef = useRef(isMuted);

    useEffect(() => {
        stateRef.current = state;
        mutedRef.current = isMuted;
    }, [state, isMuted]);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return undefined;
        const ctx = canvas.getContext('2d', { alpha: false });
        if (!ctx) return undefined;

        const CELL_W = 8.6;
        const CELL_H = 13.5;
        const FONT_SIZE = 12.5;

        let width = 540;
        const height = 166;
        let cols = 62;
        let rows = 12;
        let dpr = Math.min(window.devicePixelRatio || 1, 2);

        const resize = () => {
            const rect = canvas.parentElement?.getBoundingClientRect();
            width = Math.max(280, Math.min(600, Math.floor(rect?.width || 540)));
            dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = Math.floor(width * dpr);
            canvas.height = Math.floor(height * dpr);
            canvas.style.width = `${width}px`;
            canvas.style.height = `${height}px`;
            cols = Math.max(30, Math.floor(width / CELL_W));
            rows = Math.max(9, Math.floor(height / CELL_H));
        };

        resize();
        const ro = new ResizeObserver(resize);
        if (canvas.parentElement) ro.observe(canvas.parentElement);

        let simT = 0;
        let smoothEnergy = 0;
        let lastTime = performance.now();
        let rafId = 0;

        const draw = (now) => {
            rafId = requestAnimationFrame(draw);
            const dt = Math.min((now - lastTime) / 1000, 0.05);
            lastTime = now;

            const st = stateRef.current;
            const muted = mutedRef.current;

            const rawMic = muted ? 0 : (brainRef?.current?.audioLevelRef?.current || 0);
            const rawTts = getSharedAudioQueue()?.getOutputLevel?.() || 0;
            let targetEnergy = Math.max(rawMic, rawTts);

            if (muted) {
                targetEnergy = 0;
            } else if (st === 'speaking' && targetEnergy < 0.2) {
                targetEnergy = 0.36 + 0.2 * Math.sin(simT * 6.4) * Math.cos(simT * 2.5);
            } else if (st === 'thinking' || st === 'transcribing' || st === 'connecting') {
                targetEnergy = 0.24 + 0.09 * Math.sin(simT * 4.0);
            } else if (st === 'listening') {
                targetEnergy = Math.max(0.14 + 0.04 * Math.sin(simT * 1.9), targetEnergy * 1.3);
            }

            const rate = targetEnergy > smoothEnergy ? 16 : 6.2;
            smoothEnergy += (targetEnergy - smoothEnergy) * Math.min(1, dt * rate);

            const speedMul =
                st === 'thinking' || st === 'transcribing'
                    ? 1.55
                    : st === 'speaking'
                    ? 1.25 + smoothEnergy * 0.8
                    : muted
                    ? 0.2
                    : 0.9 + smoothEnergy * 0.9;
            simT += dt * speedMul;

            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.fillStyle = '#060606';
            ctx.fillRect(0, 0, width, height);

            ctx.font = `500 ${FONT_SIZE}px "JetBrains Mono", "Cascadia Code", "Fira Code", Consolas, monospace`;
            ctx.textBaseline = 'middle';
            ctx.textAlign = 'center';

            const offsetX = (width - cols * CELL_W) * 0.5 + CELL_W * 0.5;
            const offsetY = (height - rows * CELL_H) * 0.5 + CELL_H * 0.5;
            const midRow = (rows - 1) * 0.5;
            const isProcessing = st === 'thinking' || st === 'transcribing' || st === 'connecting';
            const beaconU = 0.5 + 0.38 * Math.sin(simT * 2.8);

            // Precompute symmetric harmonic envelope height & phase crest per column
            for (let c = 0; c < cols; c++) {
                const u = c / Math.max(1, cols - 1); // 0..1
                const taper = Math.pow(Math.sin(u * Math.PI), 1.45);
                const xNorm = (u - 0.5) * Math.PI * 2;

                let colHeight = 0;
                let crestShift = 0;
                let colHeat = 0;

                if (muted) {
                    colHeight = 0.45 * taper;
                    colHeat = 0;
                } else if (isProcessing) {
                    const distB = u - beaconU;
                    const pulse = Math.exp(-(distB * distB) / 0.016);
                    colHeight = (0.7 + pulse * 3.8) * taper;
                    crestShift = Math.sin(xNorm * 2.4 + simT * 4.5) * 0.45 * pulse;
                    colHeat = 0.25 + pulse * 0.85;
                } else {
                    // Rich multi-harmonic acoustic envelope radiating from center
                    const distCenter = Math.abs(u - 0.5) * 2;
                    const w1 = Math.abs(Math.sin(xNorm * 2.15 - simT * 3.1));
                    const w2 = Math.abs(Math.cos(xNorm * 3.45 + simT * 2.35));
                    const radial = 0.5 + 0.5 * Math.cos(distCenter * 7.5 - simT * 4.6);
                    const harmonic = 0.45 * w1 + 0.35 * w2 + 0.20 * radial;

                    const activeAmp = Math.min(1.15, 0.22 + smoothEnergy * 1.15);
                    colHeight = Math.max(0.55, harmonic * activeAmp * (rows * 0.48)) * taper;
                    crestShift = Math.sin(xNorm * 1.9 + simT * 2.8) * Math.min(1.4, smoothEnergy * 1.6) * taper;
                    colHeat = Math.min(1, (0.28 + harmonic * 0.55) * (0.55 + smoothEnergy * 0.85) * taper);
                }

                for (let r = 0; r < rows; r++) {
                    const dy = Math.abs(r - (midRow + crestShift));

                    if (muted) {
                        if (Math.abs(r - midRow) <= 0.55 && taper > 0.12) {
                            ctx.fillStyle = c % 2 === 0 ? '#5C564F' : '#2C2824';
                            ctx.fillText(c % 2 === 0 ? '-' : '·', offsetX + c * CELL_W, offsetY + r * CELL_H);
                        }
                        continue;
                    }

                    // Smooth vertical density inside the harmonic wave body
                    const normDist = dy / Math.max(0.65, colHeight);
                    if (normDist > 1.35) {
                        // Subtle quiet coordinate dot grid outside the wave body
                        if (r % 3 === 0 && c % 6 === 0 && taper > 0.2) {
                            ctx.fillStyle = '#181513';
                            ctx.fillText('·', offsetX + c * CELL_W, offsetY + r * CELL_H);
                        }
                        continue;
                    }

                    const coreFalloff = Math.exp(-(normDist * normDist) * 1.85);
                    const lum = Math.max(0, Math.min(1, coreFalloff * (0.45 + colHeat * 0.72)));
                    if (lum < 0.08) continue;

                    const rampIdx = Math.min(ASCII_RAMP.length - 1, Math.max(1, Math.floor(lum * ASCII_RAMP.length)));
                    const ch = ASCII_RAMP[rampIdx];

                    // Inner hot crest uses incandescent burnt ember; outer aura blends warm ash & bone cream
                    const isEmber = (normDist < 0.68 && (colHeat > 0.32 || st === 'speaking')) || isProcessing;
                    let palIdx;
                    if (isEmber) {
                        palIdx = 5 + Math.min(4, Math.floor(lum * 5.1));
                    } else {
                        palIdx = Math.min(4, Math.floor(lum * 5.0));
                    }

                    ctx.fillStyle = EMBER_PALETTE[palIdx];
                    ctx.fillText(ch, offsetX + c * CELL_W, offsetY + r * CELL_H);
                }
            }
        };

        rafId = requestAnimationFrame(draw);
        return () => {
            cancelAnimationFrame(rafId);
            ro.disconnect();
        };
    }, [brainRef]);

    return (
        <div
            aria-hidden="true"
            className="relative flex w-full items-center justify-center overflow-hidden bg-[#060606] select-none"
        >
            <canvas ref={canvasRef} className="block" />
        </div>
    );
}

function formatElapsed(totalSeconds) {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

export default function LiveOverlay({
    state = 'listening',
    isMuted = false,
    transcript = '',
    reply = '',
    turns = [],
    timing = {},
    error = null,
    onToggleMute,
    onCommit,
    onInterrupt,
    onRetry,
    onClose,
}) {
    const brain = useSpideyBrain();
    const brainRef = useRef(brain);
    const [showStats, setShowStats] = useState(false);
    const [showLog, setShowLog] = useState(false);
    const [elapsed, setElapsed] = useState(0);

    useEffect(() => {
        brainRef.current = brain;
    }, [brain]);

    // Session elapsed timer
    useEffect(() => {
        const startAt = Date.now();
        const timer = window.setInterval(() => {
            setElapsed(Math.floor((Date.now() - startAt) / 1000));
        }, 1000);
        return () => window.clearInterval(timer);
    }, []);

    // Live-mode local hotkeys: M = mute, Space (no modifiers) = interrupt or send now
    useEffect(() => {
        const onKey = (e) => {
            if (e.ctrlKey || e.metaKey || e.altKey || e.repeat) return;
            const tag = document.activeElement?.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA') return;

            if (e.key === 'm' || e.key === 'M') {
                e.preventDefault();
                onToggleMute?.();
            } else if (e.code === 'Space') {
                e.preventDefault();
                if (state === 'speaking' || state === 'thinking' || state === 'transcribing') {
                    onInterrupt?.();
                } else if (state === 'listening' && !isMuted) {
                    onCommit?.();
                }
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isMuted, onCommit, onInterrupt, onToggleMute, state]);

    const effectiveKey = isMuted && state === 'listening' ? 'muted' : state;
    const meta = STATE_META[effectiveKey] || STATE_META.idle;
    const canInterrupt = state === 'speaking' || state === 'thinking' || state === 'transcribing';
    const canCommit = state === 'listening' && !isMuted;
    const cleanReply = reply ? cleanAssistantText(reply) : '';

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="fixed inset-0 z-30 flex h-dvh flex-col justify-between overflow-hidden bg-[#050505]/86 px-4 py-4 backdrop-blur-[5px] sm:px-6 sm:py-5"
        >
            {/* TOP BAR — Always Visible, High Contrast */}
            <header className="mx-auto flex w-full max-w-2xl shrink-0 items-center justify-between gap-3 border border-[#F2EFE9]/14 bg-[#090807]/95 px-4 py-2.5 shadow-lg">
                <div className="flex items-center gap-3">
                    <img
                        src="/logo.png"
                        alt="ORBIT"
                        className="h-5 w-5 rounded-full object-cover"
                    />
                    <span className="font-mono text-xs font-semibold tracking-[0.22em] text-[#F2EFE9]">
                        ORBIT <span className="text-[#D95D24]">//</span> LIVE
                    </span>
                    <span
                        className={`inline-flex items-center gap-1.5 border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] ${meta.pill}`}
                    >
                        <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
                        {meta.label}
                    </span>
                </div>

                <div className="flex items-center gap-2 font-mono text-[11px]">
                    <span className="hidden text-[#8E867D] sm:inline">{formatElapsed(elapsed)}</span>
                    {turns.length > 0 && (
                        <button
                            type="button"
                            onClick={() => setShowLog((v) => !v)}
                            className={`border px-2 py-1 text-[10px] uppercase tracking-[0.12em] transition-colors ${
                                showLog
                                    ? 'border-[#D95D24] bg-[#D95D24]/15 text-[#F2EFE9]'
                                    : 'border-[#F2EFE9]/14 text-[#8E867D] hover:border-[#D95D24] hover:text-[#F2EFE9]'
                            }`}
                        >
                            log ({turns.length})
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={() => setShowStats((v) => !v)}
                        className={`border px-2 py-1 text-[10px] uppercase tracking-[0.12em] transition-colors ${
                            showStats
                                ? 'border-[#D95D24] bg-[#D95D24]/15 text-[#F2EFE9]'
                                : 'border-[#F2EFE9]/14 text-[#8E867D] hover:border-[#D95D24] hover:text-[#F2EFE9]'
                        }`}
                    >
                        stats
                    </button>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="End Live Mode"
                        className="border border-[#F2EFE9]/16 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-[#A8A096] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9]"
                    >
                        [× esc]
                    </button>
                </div>
            </header>

            {/* CENTER — Dedicated Obsidian Voice Core Stage + Clean Captions */}
            <div className="mx-auto flex min-h-0 w-full max-w-2xl flex-1 flex-col items-center justify-center overflow-y-auto py-4">
                <div className="ascii-frame w-full bg-[#070606]/94 px-5 py-6 shadow-2xl">
                    <LiveVoiceWave state={state} isMuted={isMuted} brainRef={brainRef} />

                    <p className="mt-3 text-center font-mono text-xs text-[#CFC9BF]">
                        {meta.hint}
                    </p>

                    <div className="mt-4 flex items-center justify-center gap-4 border-t border-[#F2EFE9]/8 pt-3 font-mono text-[10px] uppercase tracking-[0.16em] text-[#6E675F]">
                        <span>16khz pcm</span>
                        <span className="text-[#D95D24]/60">·</span>
                        <span>{isMuted ? 'mic paused' : 'vad active'}</span>
                        <span className="text-[#D95D24]/60">·</span>
                        <span>{formatElapsed(elapsed)}</span>
                    </div>
                </div>

                {/* Error Banner with Retry */}
                {error && (
                    <div className="mt-4 flex w-full items-center justify-between gap-3 border border-[#D95D24] bg-[#160C08] px-4 py-2.5 font-mono text-xs text-[#FFD4A8]">
                        <span className="flex-1">{error}</span>
                        {onRetry && (
                            <button
                                type="button"
                                onClick={onRetry}
                                className="shrink-0 border border-[#D95D24] bg-[#D95D24] px-2.5 py-1 text-[10px] font-semibold uppercase text-[#060606] hover:bg-[#E86B30]"
                            >
                                retry
                            </button>
                        )}
                    </div>
                )}

                {/* Live Captions */}
                {(transcript || cleanReply) && !showLog && (
                    <div className="mt-4 w-full space-y-2.5">
                        {transcript && (
                            <div className="border border-[#D95D24]/40 bg-[#120B07]/95 px-4 py-2.5">
                                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#D95D24]">
                                    you
                                </div>
                                <p className="mt-0.5 text-sm leading-relaxed text-[#F2EFE9]">
                                    “{transcript}”
                                </p>
                            </div>
                        )}
                        {cleanReply && (
                            <div className="border-l-2 border-[#D95D24] bg-[#0A0908]/96 px-4 py-3">
                                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#8E867D]">
                                    orbit
                                </div>
                                <div className="assistant-message mt-1.5 max-h-48 overflow-y-auto pr-1 text-[14px] leading-[1.65] text-[#F2EFE9]">
                                    <ReactMarkdown>{cleanReply}</ReactMarkdown>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* Expandable Live Session Log */}
                {showLog && turns.length > 0 && (
                    <div className="mt-4 max-h-56 w-full space-y-3 overflow-y-auto border border-[#F2EFE9]/14 bg-[#090807]/96 p-4">
                        {turns.slice(-10).map((turn) => (
                            <div key={turn.id} className="text-xs leading-relaxed">
                                <div
                                    className={`mb-0.5 font-mono text-[10px] uppercase tracking-[0.12em] ${
                                        turn.role === 'user' ? 'text-[#D95D24]' : 'text-[#8E867D]'
                                    }`}
                                >
                                    {turn.role === 'user' ? 'you' : 'orbit'}
                                </div>
                                {turn.role === 'assistant' ? (
                                    <div className="assistant-message text-[13px] leading-relaxed text-[#E5DFD6]">
                                        <ReactMarkdown>{cleanAssistantText(turn.content)}</ReactMarkdown>
                                    </div>
                                ) : (
                                    <p className="text-[13px] text-[#F2EFE9]">{turn.content}</p>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {/* Latency Diagnostics */}
                {showStats && (
                    <div className="mt-4 grid w-full max-w-md grid-cols-2 gap-2 border border-[#F2EFE9]/14 bg-[#090807]/96 p-3 font-mono text-[11px] text-[#8E867D]">
                        <div>
                            STT: <span className="text-[#FF944D]">{timing.transcript || 0} ms</span>
                        </div>
                        <div>
                            LLM: <span className="text-[#FF944D]">{timing.firstSentence || 0} ms</span>
                        </div>
                        <div>
                            TTS: <span className="text-[#FF944D]">{timing.firstAudio || 0} ms</span>
                        </div>
                        <div className="text-[#F2EFE9]">
                            Total: <span className="text-[#D95D24]">{timing.total || 0} ms</span>
                        </div>
                    </div>
                )}
            </div>

            {/* BOTTOM CONTROL DOCK */}
            <footer className="mx-auto flex w-full max-w-2xl shrink-0 flex-wrap items-center justify-center gap-2.5 border border-[#F2EFE9]/14 bg-[#090807]/95 px-4 py-3 shadow-lg">
                <button
                    type="button"
                    onClick={onToggleMute}
                    className={`border px-3.5 py-2 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors ${
                        isMuted
                            ? 'border-[#D95D24] bg-[#D95D24]/20 text-[#FFD4A8]'
                            : 'border-[#F2EFE9]/18 bg-[#0C0B0A] text-[#CFC9BF] hover:border-[#D95D24] hover:text-[#F2EFE9]'
                    }`}
                    title="Toggle Microphone (M)"
                >
                    {isMuted ? '[mic:muted · m]' : '[mic:on · m]'}
                </button>

                {canCommit && (
                    <button
                        type="button"
                        onClick={onCommit}
                        className="border border-[#F2EFE9]/18 bg-[#0C0B0A] px-3.5 py-2 font-mono text-[11px] uppercase tracking-[0.12em] text-[#CFC9BF] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9]"
                        title="Send spoken audio now (Space)"
                    >
                        [send now · space]
                    </button>
                )}

                {canInterrupt && (
                    <button
                        type="button"
                        onClick={onInterrupt}
                        className="border border-[#D95D24] bg-[#D95D24]/18 px-3.5 py-2 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-[#FFD4A8] transition-colors hover:bg-[#D95D24] hover:text-[#060606]"
                        title="Interrupt ORBIT (Space)"
                    >
                        [interrupt · space]
                    </button>
                )}

                <button
                    type="button"
                    onClick={onClose}
                    className="border border-[#D95D24] bg-[#D95D24] px-4 py-2 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-[#060606] transition-colors hover:bg-[#E86B30]"
                    title="Exit Live Mode (Ctrl+Space or Esc)"
                >
                    [end live · ctrl+space]
                </button>
            </footer>
        </motion.div>
    );
}
