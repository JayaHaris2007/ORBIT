import { motion } from 'framer-motion';
import { Check, Flame, Trash2, Pencil } from 'lucide-react';
import { format } from 'date-fns';
import * as Icons from 'lucide-react';

const HabitCard = ({ habit, onToggle, onDelete, onEdit }) => {
    const today = format(new Date(), 'yyyy-MM-dd');
    const isCompletedToday = habit.completedDates?.includes(today);
    const IconComponent = Icons[habit.icon] || Icons.Activity;

    return (
        <motion.div
            layout
            data-spidey-card="habit"
            data-spidey-title={habit.name || habit.title || ''}
            data-spidey-completed={isCompletedToday ? 'true' : 'false'}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className={`group relative border p-4 transition-colors duration-150 ${
                isCompletedToday
                    ? 'border-[#D95D24]/60 bg-[#1A1613]'
                    : 'border-[#F2EFE9]/14 bg-[#151515] hover:border-[#F2EFE9]/30'
            }`}
        >
            <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3.5 min-w-0">
                    <div
                        className={`grid h-10 w-10 shrink-0 place-items-center border transition-colors ${
                            isCompletedToday
                                ? 'border-[#D95D24] bg-[#D95D24] text-[#111111]'
                                : 'border-[#F2EFE9]/15 bg-[#111111] text-[#9C968E]'
                        }`}
                    >
                        <IconComponent size={18} strokeWidth={1.7} />
                    </div>

                    <div className="min-w-0">
                        <h3 className={`truncate text-sm font-semibold tracking-wide ${isCompletedToday ? 'text-[#F2EFE9]' : 'text-[#F2EFE9]/90'}`}>
                            {habit.name}
                        </h3>
                        <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9C968E]">
                            <Flame size={11} className={habit.streak > 0 ? 'text-[#D95D24]' : 'text-[#9C968E]'} />
                            <span className={habit.streak > 0 ? 'text-[#F2EFE9]' : ''}>{habit.streak} day streak</span>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                    {onEdit && (
                        <button
                            type="button"
                            onClick={() => onEdit(habit)}
                            className="p-1.5 text-[#9C968E] opacity-100 transition-opacity hover:text-[#F2EFE9] md:opacity-0 md:group-hover:opacity-100"
                            aria-label={`Edit ${habit.name}`}
                        >
                            <Pencil size={14} />
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={() => onToggle(habit)}
                        className={`grid h-8 w-8 place-items-center border transition-colors ${
                            isCompletedToday
                                ? 'border-[#D95D24] bg-[#D95D24] text-[#111111]'
                                : 'border-[#F2EFE9]/25 bg-transparent text-[#9C968E]/40 hover:border-[#D95D24] hover:text-[#D95D24]'
                        }`}
                        aria-label={`Toggle ${habit.name}`}
                    >
                        <Check size={15} strokeWidth={2.6} />
                    </button>

                    <button
                        type="button"
                        onClick={() => onDelete(habit.id)}
                        className="p-1.5 text-[#9C968E] opacity-100 transition-opacity hover:text-[#D95D24] md:opacity-0 md:group-hover:opacity-100"
                        aria-label={`Delete ${habit.name}`}
                    >
                        <Trash2 size={14} />
                    </button>
                </div>
            </div>
        </motion.div>
    );
};

export default HabitCard;
