import { motion } from 'framer-motion';

const CircularProgress = ({ value, max, size = 120, strokeWidth = 6, color = '#D95D24' }) => {
    const radius = (size - strokeWidth) / 2;
    const circumference = radius * 2 * Math.PI;
    const progress = Math.min(value / Math.max(max, 1), 1);
    const dashoffset = circumference - progress * circumference;

    return (
        <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
            <svg width={size} height={size} className="-rotate-90 transform">
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    stroke="rgba(242, 239, 233, 0.12)"
                    strokeWidth={strokeWidth}
                    fill="transparent"
                />
                <motion.circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    stroke={color}
                    strokeWidth={strokeWidth}
                    fill="transparent"
                    strokeLinecap="butt"
                    initial={{ strokeDashoffset: circumference }}
                    animate={{ strokeDashoffset: dashoffset }}
                    transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
                    style={{ strokeDasharray: circumference }}
                />
            </svg>
            <div className="absolute flex flex-col items-center">
                <span className="font-mono text-2xl font-bold tracking-tight text-[#F2EFE9]">
                    {Math.round(progress * 100)}%
                </span>
            </div>
        </div>
    );
};

export default CircularProgress;
