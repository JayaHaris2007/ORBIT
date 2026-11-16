import { motion } from 'framer-motion';

const EASE_PLOTTER = [0.22, 1, 0.36, 1];

/**
 * Architectural pen-plotter line-art backdrop:
 * Parallel S-curve strokes + concentric orbital rings that draw cleanly on load.
 */
export function PlotterBackdrop() {
    const sCurves = [
        'M -40 160 C 260 60, 460 340, 820 220 S 1260 90, 1520 210',
        'M -40 184 C 260 84, 460 364, 820 244 S 1260 114, 1520 234',
        'M -40 208 C 260 108, 460 388, 820 268 S 1260 138, 1520 258',
        'M -40 620 C 310 510, 520 790, 900 660 S 1300 540, 1520 640',
        'M -40 644 C 310 534, 520 814, 900 684 S 1300 564, 1520 664',
    ];

    const orbitalRings = [
        { cx: 1180, cy: 230, r: 110, delay: 0.18 },
        { cx: 1180, cy: 230, r: 146, delay: 0.25 },
        { cx: 1180, cy: 230, r: 184, delay: 0.32 },
        { cx: 220, cy: 700, r: 90, delay: 0.36 },
        { cx: 220, cy: 700, r: 124, delay: 0.43 },
    ];

    return (
        <svg
            aria-hidden="true"
            viewBox="0 0 1440 900"
            preserveAspectRatio="xMidYMid slice"
            className="pointer-events-none fixed inset-0 h-full w-full z-0"
            fill="none"
        >
            {sCurves.map((d, idx) => (
                <motion.path
                    key={d}
                    d={d}
                    stroke={idx === 1 || idx === 4 ? 'rgba(217, 93, 36, 0.14)' : 'rgba(242, 239, 233, 0.065)'}
                    strokeWidth="1"
                    initial={{ pathLength: 0, opacity: 0 }}
                    animate={{ pathLength: 1, opacity: 1 }}
                    transition={{
                        pathLength: { duration: 1.05, delay: idx * 0.08, ease: EASE_PLOTTER },
                        opacity: { duration: 0.25, delay: idx * 0.08 },
                    }}
                />
            ))}

            {orbitalRings.map((ring) => (
                <motion.circle
                    key={`${ring.cx}-${ring.cy}-${ring.r}`}
                    cx={ring.cx}
                    cy={ring.cy}
                    r={ring.r}
                    stroke="rgba(242, 239, 233, 0.06)"
                    strokeWidth="1"
                    initial={{ pathLength: 0, opacity: 0 }}
                    animate={{ pathLength: 1, opacity: 1 }}
                    transition={{
                        pathLength: { duration: 0.95, delay: ring.delay, ease: EASE_PLOTTER },
                        opacity: { duration: 0.2, delay: ring.delay },
                    }}
                />
            ))}

            {/* Slow architectural compass tick ring */}
            <motion.circle
                cx={1180}
                cy={230}
                r={216}
                stroke="rgba(217, 93, 36, 0.14)"
                strokeWidth="1"
                strokeDasharray="3 11"
                initial={{ opacity: 0, rotate: 0 }}
                animate={{ opacity: 1, rotate: 360 }}
                transition={{
                    opacity: { duration: 0.5, delay: 0.45 },
                    rotate: { duration: 90, repeat: Infinity, ease: 'linear' },
                }}
                style={{ transformOrigin: '1180px 230px' }}
            />
        </svg>
    );
}

/**
 * Scroll-triggered pen-plotter section divider with index label and staggered hairline rule.
 */
export function PlotterSectionHeader({ index, title, rightLabel = '' }) {
    return (
        <div className="mb-4">
            <div className="flex items-center justify-between gap-4 pb-2">
                <div className="flex items-center gap-3">
                    {index && (
                        <span className="bg-[#D95D24] px-2 py-0.5 font-mono text-[10px] font-bold tracking-[0.16em] text-[#111111]">
                            {index}
                        </span>
                    )}
                    <h2 className="text-xs font-bold uppercase tracking-[0.22em] text-[#F2EFE9]">
                        {title}
                    </h2>
                </div>
                {rightLabel && (
                    <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
                        {rightLabel}
                    </span>
                )}
            </div>

            <svg
                aria-hidden="true"
                viewBox="0 0 1000 10"
                preserveAspectRatio="none"
                className="block h-[10px] w-full"
                fill="none"
            >
                <motion.line
                    x1="0"
                    y1="2"
                    x2="1000"
                    y2="2"
                    stroke="rgba(242, 239, 233, 0.16)"
                    strokeWidth="1"
                    initial={{ pathLength: 0 }}
                    whileInView={{ pathLength: 1 }}
                    viewport={{ once: true, amount: 0.6 }}
                    transition={{ duration: 0.55, ease: EASE_PLOTTER }}
                />
                <motion.line
                    x1="0"
                    y1="6"
                    x2="160"
                    y2="6"
                    stroke="#D95D24"
                    strokeWidth="1.5"
                    initial={{ pathLength: 0 }}
                    whileInView={{ pathLength: 1 }}
                    viewport={{ once: true, amount: 0.6 }}
                    transition={{ duration: 0.42, delay: 0.1, ease: EASE_PLOTTER }}
                />
            </svg>
        </div>
    );
}
