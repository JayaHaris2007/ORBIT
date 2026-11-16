import { motion } from 'framer-motion';

const EASE_OUT_MECH = [0.22, 1, 0.36, 1];

const LEG_PATHS = [
    // Upper inner pair (cream, circle ticks)
    {
        id: 'leg-ul-inner',
        d: 'M 86 90 L 62 64 L 84 40',
        stroke: '#F2EFE9',
        width: 2.6,
        delay: 0.28,
        tick: { type: 'circle', cx: 85.5, cy: 38, r: 2.7, stroke: '#F2EFE9' },
    },
    {
        id: 'leg-ur-inner',
        d: 'M 114 90 L 138 64 L 116 40',
        stroke: '#F2EFE9',
        width: 2.6,
        delay: 0.28,
        tick: { type: 'circle', cx: 114.5, cy: 38, r: 2.7, stroke: '#F2EFE9' },
    },
    // Muted inner traces under upper legs
    {
        id: 'leg-ul-trace',
        d: 'M 85 83 L 71 65 L 82 52',
        stroke: '#70685F',
        width: 2.1,
        delay: 0.34,
    },
    {
        id: 'leg-ur-trace',
        d: 'M 115 83 L 129 65 L 118 52',
        stroke: '#70685F',
        width: 2.1,
        delay: 0.34,
    },
    // Upper outer pair (cream, square ticks)
    {
        id: 'leg-ul-outer',
        d: 'M 82 97 L 51 71 L 51 54',
        stroke: '#F2EFE9',
        width: 2.6,
        delay: 0.36,
        tick: { type: 'rect', x: 48.5, y: 49, size: 5, stroke: '#F2EFE9' },
    },
    {
        id: 'leg-ur-outer',
        d: 'M 118 97 L 149 71 L 149 54',
        stroke: '#F2EFE9',
        width: 2.6,
        delay: 0.36,
        tick: { type: 'rect', x: 146.5, y: 49, size: 5, stroke: '#F2EFE9' },
    },
    // Mid-outer muted pair (circle ticks)
    {
        id: 'leg-ml-muted',
        d: 'M 78 101 L 40 76',
        stroke: '#70685F',
        width: 2.2,
        delay: 0.42,
        tick: { type: 'circle', cx: 38, cy: 74.5, r: 2.4, stroke: '#70685F' },
    },
    {
        id: 'leg-mr-muted',
        d: 'M 122 101 L 160 76',
        stroke: '#70685F',
        width: 2.2,
        delay: 0.42,
        tick: { type: 'circle', cx: 162, cy: 74.5, r: 2.4, stroke: '#70685F' },
    },
    // Lower outer pair (cream, square ticks)
    {
        id: 'leg-ll-outer',
        d: 'M 82 102 L 70 102 L 45 127 L 45 148',
        stroke: '#F2EFE9',
        width: 2.6,
        delay: 0.46,
        tick: { type: 'rect', x: 42.5, y: 148, size: 5, stroke: '#F2EFE9' },
    },
    {
        id: 'leg-lr-outer',
        d: 'M 118 102 L 130 102 L 155 127 L 155 148',
        stroke: '#F2EFE9',
        width: 2.6,
        delay: 0.46,
        tick: { type: 'rect', x: 152.5, y: 148, size: 5, stroke: '#F2EFE9' },
    },
    // Bottom inner muted pair (square left / circle right ticks)
    {
        id: 'leg-ll-inner',
        d: 'M 79 108 L 56 131 L 78 163',
        stroke: '#70685F',
        width: 2.2,
        delay: 0.52,
        tick: { type: 'rect', x: 76.5, y: 163, size: 4.5, stroke: '#70685F' },
    },
    {
        id: 'leg-lr-inner',
        d: 'M 121 108 L 144 131 L 122 163',
        stroke: '#70685F',
        width: 2.2,
        delay: 0.52,
        tick: { type: 'circle', cx: 120.5, cy: 165, r: 2.4, stroke: '#70685F' },
    },
    // Bottom inner short chevron traces
    {
        id: 'leg-ll-chevron',
        d: 'M 83 114 L 66 131 L 74 143',
        stroke: '#70685F',
        width: 2.1,
        delay: 0.56,
    },
    {
        id: 'leg-lr-chevron',
        d: 'M 117 114 L 134 131 L 126 143',
        stroke: '#70685F',
        width: 2.1,
        delay: 0.56,
    },
];

export default function SpiderMark({
    size = 44,
    state = 'idle',
    animateEntrance = true,
    className = '',
}) {
    const isActive = state === 'thinking' || state === 'listening' || state === 'streaming' || state === 'speaking' || state === 'transcribing';

    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 200 200"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className={`shrink-0 select-none ${className}`}
            aria-label="S.P.I.D.E.Y. geometric spider mark"
        >
            {/* 1. Legs & Terminal Node Ticks (drawn outward from core) */}
            {LEG_PATHS.map((leg, idx) => (
                <g key={leg.id}>
                    <motion.path
                        d={leg.d}
                        stroke={leg.stroke}
                        strokeWidth={leg.width}
                        strokeLinecap="square"
                        strokeLinejoin="miter"
                        initial={animateEntrance ? { pathLength: 0, opacity: 0 } : false}
                        animate={{ pathLength: 1, opacity: 1 }}
                        transition={{
                            pathLength: { duration: 0.42, delay: leg.delay, ease: EASE_OUT_MECH },
                            opacity: { duration: 0.15, delay: leg.delay },
                        }}
                    />

                    {leg.tick?.type === 'circle' && (
                        <motion.circle
                            cx={leg.tick.cx}
                            cy={leg.tick.cy}
                            r={leg.tick.r}
                            fill="#111111"
                            strokeWidth="2.2"
                            initial={animateEntrance ? { scale: 0, opacity: 0 } : false}
                            animate={{
                                scale: 1,
                                opacity: isActive ? [0.65, 1, 0.65] : 1,
                                stroke: isActive ? ['#D95D24', '#F2EFE9', '#D95D24'] : leg.tick.stroke,
                            }}
                            transition={{
                                scale: { duration: 0.2, delay: leg.delay + 0.34, ease: EASE_OUT_MECH },
                                opacity: isActive
                                    ? { duration: 1.4, repeat: Infinity, delay: (idx % 4) * 0.16, ease: 'easeInOut' }
                                    : { duration: 0.2, delay: leg.delay + 0.34 },
                                stroke: isActive
                                    ? { duration: 1.4, repeat: Infinity, delay: (idx % 4) * 0.16, ease: 'easeInOut' }
                                    : { duration: 0.2 },
                            }}
                            style={{ transformOrigin: `${leg.tick.cx}px ${leg.tick.cy}px` }}
                        />
                    )}

                    {leg.tick?.type === 'rect' && (
                        <motion.rect
                            x={leg.tick.x}
                            y={leg.tick.y}
                            width={leg.tick.size}
                            height={leg.tick.size}
                            fill="#111111"
                            strokeWidth="2.2"
                            initial={animateEntrance ? { scale: 0, opacity: 0 } : false}
                            animate={{
                                scale: 1,
                                opacity: isActive ? [0.65, 1, 0.65] : 1,
                                stroke: isActive ? ['#D95D24', '#F2EFE9', '#D95D24'] : leg.tick.stroke,
                            }}
                            transition={{
                                scale: { duration: 0.2, delay: leg.delay + 0.34, ease: EASE_OUT_MECH },
                                opacity: isActive
                                    ? { duration: 1.4, repeat: Infinity, delay: (idx % 4) * 0.16, ease: 'easeInOut' }
                                    : { duration: 0.2, delay: leg.delay + 0.34 },
                                stroke: isActive
                                    ? { duration: 1.4, repeat: Infinity, delay: (idx % 4) * 0.16, ease: 'easeInOut' }
                                    : { duration: 0.2 },
                            }}
                            style={{
                                transformOrigin: `${leg.tick.x + leg.tick.size / 2}px ${leg.tick.y + leg.tick.size / 2}px`,
                            }}
                        />
                    )}
                </g>
            ))}

            {/* 2. Concentric Thorax Rings (trace around core) */}
            <g>
                <motion.circle
                    cx="100"
                    cy="82"
                    r="21.5"
                    stroke="#F2EFE9"
                    strokeWidth="2.4"
                    initial={animateEntrance ? { pathLength: 0, opacity: 0 } : false}
                    animate={{ pathLength: 1, opacity: 1 }}
                    transition={{ duration: 0.36, delay: 0.14, ease: EASE_OUT_MECH }}
                />
                <motion.circle
                    cx="100"
                    cy="82"
                    r="15.5"
                    stroke="#F2EFE9"
                    strokeWidth="2.3"
                    initial={animateEntrance ? { pathLength: 0, opacity: 0 } : false}
                    animate={{ pathLength: 1, opacity: 1 }}
                    transition={{ duration: 0.32, delay: 0.19, ease: EASE_OUT_MECH }}
                />
                <motion.circle
                    cx="100"
                    cy="82"
                    r="9.5"
                    stroke="#F2EFE9"
                    strokeWidth="2.2"
                    initial={animateEntrance ? { pathLength: 0, opacity: 0 } : false}
                    animate={{ pathLength: 1, opacity: 1 }}
                    transition={{ duration: 0.28, delay: 0.24, ease: EASE_OUT_MECH }}
                />
                {/* Mandibles */}
                <motion.path
                    d="M 94 61 C 90 54 91 49 95 46"
                    stroke="#F2EFE9"
                    strokeWidth="2.3"
                    strokeLinecap="round"
                    initial={animateEntrance ? { pathLength: 0, opacity: 0 } : false}
                    animate={{ pathLength: 1, opacity: 1 }}
                    transition={{ duration: 0.25, delay: 0.3, ease: EASE_OUT_MECH }}
                />
                <motion.path
                    d="M 106 61 C 110 54 109 49 105 46"
                    stroke="#F2EFE9"
                    strokeWidth="2.3"
                    strokeLinecap="round"
                    initial={animateEntrance ? { pathLength: 0, opacity: 0 } : false}
                    animate={{ pathLength: 1, opacity: 1 }}
                    transition={{ duration: 0.25, delay: 0.3, ease: EASE_OUT_MECH }}
                />
                {/* Cream crown node dot */}
                <motion.circle
                    cx="100"
                    cy="66.5"
                    r="2.6"
                    fill="#F2EFE9"
                    initial={animateEntrance ? { scale: 0, opacity: 0 } : false}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ duration: 0.2, delay: 0.28, ease: EASE_OUT_MECH }}
                    style={{ transformOrigin: '100px 66.5px' }}
                />
            </g>

            {/* 3. Burnt-Orange Abdomen Core (fades in first from inside out) */}
            <motion.circle
                cx="100"
                cy="126"
                r="24.5"
                fill="#D95D24"
                initial={animateEntrance ? { scale: 0.72, opacity: 0 } : false}
                animate={{
                    scale: isActive ? [1, 1.045, 1] : 1,
                    opacity: isActive ? [0.9, 1, 0.9] : 1,
                }}
                transition={{
                    scale: isActive
                        ? { duration: 1.6, repeat: Infinity, ease: 'easeInOut' }
                        : { duration: 0.3, ease: EASE_OUT_MECH },
                    opacity: isActive
                        ? { duration: 1.6, repeat: Infinity, ease: 'easeInOut' }
                        : { duration: 0.25, ease: EASE_OUT_MECH },
                }}
                style={{ transformOrigin: '100px 126px' }}
            />
        </svg>
    );
}
