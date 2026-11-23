import { format } from 'date-fns';

const priorityBadge = {
    low: 'border-[#F2EFE9]/16 text-[#8E867D] bg-[#060606]',
    medium: 'border-[#F2EFE9]/35 text-[#F2EFE9] bg-[#141210]',
    high: 'border-[#D95D24] text-[#060606] bg-[#D95D24] font-semibold',
};

const TaskCard = ({ task, onToggle, onDelete, onEdit }) => {
    return (
        <div
            data-spidey-card="task"
            data-spidey-title={task.title || ''}
            data-spidey-completed={task.completed ? 'true' : 'false'}
            className={`group flex items-start justify-between gap-3 border p-4 transition-colors ${
                task.completed
                    ? 'border-[#F2EFE9]/10 bg-[#080807] opacity-55'
                    : 'border-[#F2EFE9]/14 bg-[#0B0A09] hover:border-[#D95D24]/60'
            }`}
        >
            <div className="flex min-w-0 flex-1 items-start gap-3">
                <button
                    type="button"
                    onClick={() => onToggle(task.id, !task.completed)}
                    className={`mt-0.5 shrink-0 font-mono text-xs transition-colors ${
                        task.completed
                            ? 'text-[#D95D24]'
                            : 'text-[#8E867D] hover:text-[#D95D24]'
                    }`}
                    aria-label={`Toggle ${task.title}`}
                >
                    {task.completed ? '[x]' : '[ ]'}
                </button>

                <div className="min-w-0 flex-1">
                    <h3
                        className={`text-sm font-medium leading-snug ${
                            task.completed ? 'line-through text-[#7D756C]' : 'text-[#F2EFE9]'
                        }`}
                    >
                        {task.title}
                    </h3>
                    {task.description && (
                        <p className="mt-1 text-xs leading-relaxed text-[#8E867D]">{task.description}</p>
                    )}

                    <div className="mt-2.5 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em]">
                        <span className={`border px-1.5 py-0.5 ${priorityBadge[task.priority] || priorityBadge.low}`}>
                            {task.priority || 'low'}
                        </span>
                        {task.dueDate && !Number.isNaN(new Date(task.dueDate).getTime()) && (
                            <span className="border border-[#F2EFE9]/14 bg-[#060606] px-1.5 py-0.5 text-[#8E867D]">
                                due:{format(new Date(task.dueDate), 'MMM_dd').toLowerCase()}
                            </span>
                        )}
                    </div>
                </div>
            </div>

            <div className="flex shrink-0 items-center gap-1 font-mono text-[10px] uppercase">
                {onEdit && (
                    <button
                        type="button"
                        onClick={() => onEdit(task)}
                        className="px-1.5 py-1 text-[#8E867D] opacity-100 transition-opacity hover:text-[#F2EFE9] md:opacity-0 md:group-hover:opacity-100"
                        aria-label={`Edit ${task.title}`}
                    >
                        [ed]
                    </button>
                )}
                <button
                    type="button"
                    onClick={() => onDelete(task.id)}
                    className="px-1.5 py-1 text-[#8E867D] opacity-100 transition-opacity hover:text-[#D95D24] md:opacity-0 md:group-hover:opacity-100"
                    aria-label={`Delete ${task.title}`}
                >
                    [rm]
                </button>
            </div>
        </div>
    );
};

export default TaskCard;
