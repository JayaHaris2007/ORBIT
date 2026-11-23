import { motion } from 'framer-motion';
import { format, subDays } from 'date-fns';
import * as Icons from 'lucide-react';

const HabitCard = ({ habit, onToggle, onDelete, onEdit }) => {
    const today = format(new Date(), 'yyyy-MM-dd');
    const isCompletedToday = habit.completedDates?.includes(today);
    const IconComponent = Icons[habit.icon] || Icons.Activity;

    // 7-day ASCII dot strip
    const last7 = Array.from({ length: 7 }, (_, i) => {
        const key = format(subDays(new Date(), 6 - i), 'yyyy-MM-dd');
        return Boolean(habit.completedDates?.includes(key));
    });

    return (
        <motion.div
            layout
            data-spidey-card="habit"
            data-spidey-title={habit.name || habit.title || ''}
            data-spidey-completed={isCompletedToday ? 'true' : 'false'}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.16 }}
            className={`group relative border p-4 transition-colors ${
                isCompletedToday
                    ? 'border-[#D95D24]/65 bg-[#150E0A]'
                    : 'border-[#F2EFE9]/14 bg-[#0B0A09] hover:border-[#F2EFE9]/35'
            }`}
        >
            <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                    <div
                        className={`grid h-9 w-9 shrink-0 place-items-center border transition-colors ${
                            isCompletedToday
                                ? 'border-[#D95D24] bg-[#D95D24] text-[#060606]'
                                : 'border-[#F2EFE9]/16 bg-[#060606] text-[#8E867D]'
                        }`}
                    >
                        <IconComponent size={16} strokeWidth={1.8} />
                    </div>

                    <div className="min-w-0">
                        <h3 className="truncate text-sm font-medium text-[#F2EFE9]">
                            {habit.name}
                        </h3>
                        <div className="mt-1 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em]">
                            <span className={habit.streak > 0 ? 'text-[#D95D24]' : 'text-[#6E675F]'}>
                                {habit.streak || 0}d streak
                            </span>
                            <span className="text-[#4F4943]">·</span>
                            <span className="tracking-widest" title="Last 7 days">
                                {last7.map((done, i) => (
                                    <span key={i} className={done ? 'text-[#D95D24]' : 'text-[#3A3530]'}>
                                        {done ? '▪' : '▫'}
                                    </span>
                                ))}
                            </span>
                        </div>
                    </div>
                </div>

                <div className="flex shrink-0 items-center gap-1.5 font-mono text-[10px] uppercase">
                    {onEdit && (
                        <button
                            type="button"
                            onClick={() => onEdit(habit)}
                            className="px-1.5 py-1 text-[#8E867D] opacity-100 transition-opacity hover:text-[#F2EFE9] md:opacity-0 md:group-hover:opacity-100"
                            aria-label={`Edit ${habit.name}`}
                        >
                            [ed]
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={() => onToggle(habit)}
                        className={`border px-2.5 py-1 font-semibold transition-colors ${
                            isCompletedToday
                                ? 'border-[#D95D24] bg-[#D95D24] text-[#060606]'
                                : 'border-[#F2EFE9]/22 bg-[#060606] text-[#8E867D] hover:border-[#D95D24] hover:text-[#D95D24]'
                        }`}
                        aria-label={`Toggle ${habit.name}`}
                    >
                        {isCompletedToday ? '[done]' : '[mark]'}
                    </button>
                    <button
                        type="button"
                        onClick={() => onDelete(habit.id)}
                        className="px-1.5 py-1 text-[#8E867D] opacity-100 transition-opacity hover:text-[#D95D24] md:opacity-0 md:group-hover:opacity-100"
                        aria-label={`Delete ${habit.name}`}
                    >
                        [rm]
                    </button>
                </div>
            </div>
        </motion.div>
    );
};

export default HabitCard;
