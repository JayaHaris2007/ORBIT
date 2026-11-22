import { Check, Trash2, Calendar, AlertCircle, Pencil } from 'lucide-react';
import { format } from 'date-fns';

const priorityStyles = {
    low: 'border-[#F2EFE9]/15 text-[#9C968E] bg-[#111111]',
    medium: 'border-[#F2EFE9]/30 text-[#F2EFE9] bg-[#191816]',
    high: 'border-[#D95D24] text-[#111111] bg-[#D95D24] font-bold',
};

const TaskCard = ({ task, onToggle, onDelete, onEdit }) => {
    return (
        <div
            data-spidey-card="task"
            data-spidey-title={task.title || ''}
            data-spidey-completed={task.completed ? 'true' : 'false'}
            className={`group flex items-start justify-between gap-3 border border-[#F2EFE9]/14 bg-[#151515] p-4 transition-colors hover:border-[#F2EFE9]/30 ${
                task.completed ? 'opacity-45' : ''
            }`}
        >
            <div className="flex w-full items-start gap-3.5 min-w-0">
                <button
                    type="button"
                    onClick={() => onToggle(task.id, !task.completed)}
                    className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center border transition-colors ${
                        task.completed
                            ? 'border-[#D95D24] bg-[#D95D24] text-[#111111]'
                            : 'border-[#F2EFE9]/30 bg-transparent hover:border-[#D95D24]'
                    }`}
                    aria-label={`Toggle ${task.title}`}
                >
                    {task.completed && <Check size={12} strokeWidth={3} />}
                </button>

                <div className="min-w-0 flex-1">
                    <h3 className={`text-sm font-semibold tracking-wide ${task.completed ? 'line-through text-[#9C968E]' : 'text-[#F2EFE9]'}`}>
                        {task.title}
                    </h3>
                    {task.description && (
                        <p className="mt-1 text-xs leading-relaxed text-[#9C968E]">{task.description}</p>
                    )}

                    <div className="mt-2.5 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]">
                        {task.dueDate && !Number.isNaN(new Date(task.dueDate).getTime()) && (
                            <span className="inline-flex items-center gap-1 border border-[#F2EFE9]/15 bg-[#111111] px-2 py-0.5 text-[#9C968E]">
                                <Calendar size={10} />
                                {format(new Date(task.dueDate), 'MMM d')}
                            </span>
                        )}

                        <span className={`inline-flex items-center gap-1 border px-2 py-0.5 ${priorityStyles[task.priority] || priorityStyles.low}`}>
                            <AlertCircle size={10} />
                            {task.priority}
                        </span>
                    </div>
                </div>
            </div>

            <div className="flex items-center shrink-0">
                {onEdit && (
                    <button
                        type="button"
                        onClick={() => onEdit(task)}
                        className="p-1.5 text-[#9C968E] opacity-100 transition-opacity hover:text-[#F2EFE9] md:opacity-0 md:group-hover:opacity-100"
                        aria-label={`Edit ${task.title}`}
                    >
                        <Pencil size={14} />
                    </button>
                )}
                <button
                    type="button"
                    onClick={() => onDelete(task.id)}
                    className="p-1.5 text-[#9C968E] opacity-100 transition-opacity hover:text-[#D95D24] md:opacity-0 md:group-hover:opacity-100"
                    aria-label={`Delete ${task.title}`}
                >
                    <Trash2 size={14} />
                </button>
            </div>
        </div>
    );
};

export default TaskCard;
