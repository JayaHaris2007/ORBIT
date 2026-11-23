import { useEffect, useRef, useState } from 'react';

const emptyForm = { title: '', description: '', priority: 'medium', dueDate: '' };

const toDateInput = (value) => (
    typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : ''
);

const TaskEditor = ({ task, onSave, onCancel }) => {
    const [form, setForm] = useState(() => (task ? {
        title: task.title || '',
        description: task.description || '',
        priority: task.priority || 'medium',
        dueDate: toDateInput(task.dueDate),
    } : emptyForm));
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const panelRef = useRef(null);
    const isEditing = Boolean(task);

    useEffect(() => {
        if (task) panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, [task]);

    const updateField = (field) => (event) => {
        const { value } = event.target;
        setForm((current) => ({ ...current, [field]: value }));
    };

    const handleSubmit = async (event) => {
        event.preventDefault();
        const title = form.title.trim();
        if (!title || saving) return;
        const originalDue = task?.dueDate;
        const dueDate = form.dueDate && typeof originalDue === 'string'
            && originalDue.slice(0, 10) === form.dueDate
            ? originalDue
            : form.dueDate;
        setSaving(true);
        setError('');
        try {
            await onSave({ ...form, title, dueDate });
            if (!isEditing) setForm(emptyForm);
        } catch (requestError) {
            setError(requestError.message || 'Could not save this task.');
        } finally {
            setSaving(false);
        }
    };

    return (
        <section ref={panelRef} className="ascii-frame bg-[#0A0908] p-5">
            <div className="flex items-start justify-between gap-3 border-b border-[#F2EFE9]/12 pb-3 font-mono">
                <div>
                    <p className="text-[10px] uppercase tracking-[0.18em] text-[#D95D24]">
                        {isEditing ? '// edit_task' : '// new_task'}
                    </p>
                    <h2 className="mt-1 text-sm font-semibold uppercase tracking-[0.12em] text-[#F2EFE9]">
                        {isEditing ? 'Modify Entry' : 'Add to Queue'}
                    </h2>
                </div>
                {isEditing && (
                    <button
                        type="button"
                        onClick={onCancel}
                        className="text-[11px] text-[#8E867D] hover:text-[#D95D24]"
                        aria-label="Stop editing this task"
                    >
                        [x]
                    </button>
                )}
            </div>

            {isEditing && (
                <p className="mt-3 truncate border border-[#D95D24]/45 bg-[#160E09] px-3 py-1.5 font-mono text-[11px] text-[#E87D42]">
                    #{task.id} · {task.title}
                </p>
            )}

            <form onSubmit={handleSubmit} className="mt-4 space-y-4">
                <div>
                    <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-[0.16em] text-[#8E867D]" htmlFor="task-title">
                        Title
                    </label>
                    <input
                        id="task-title"
                        type="text"
                        required
                        value={form.title}
                        onChange={updateField('title')}
                        maxLength={500}
                        placeholder="What needs doing?"
                        className="w-full border border-[#F2EFE9]/15 bg-[#060606] px-3 py-2 text-sm text-[#F2EFE9] placeholder:text-[#5C564F] focus:border-[#D95D24] focus:outline-none"
                    />
                </div>

                <div>
                    <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-[0.16em] text-[#8E867D]" htmlFor="task-desc">
                        Notes
                    </label>
                    <textarea
                        id="task-desc"
                        value={form.description}
                        onChange={updateField('description')}
                        maxLength={2000}
                        rows={3}
                        placeholder="Optional context or checklist..."
                        className="w-full resize-y border border-[#F2EFE9]/15 bg-[#060606] px-3 py-2 text-sm text-[#F2EFE9] placeholder:text-[#5C564F] focus:border-[#D95D24] focus:outline-none"
                    />
                </div>

                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-[0.16em] text-[#8E867D]" htmlFor="task-priority">
                            Priority
                        </label>
                        <select
                            id="task-priority"
                            value={form.priority}
                            onChange={updateField('priority')}
                            className="w-full border border-[#F2EFE9]/15 bg-[#060606] px-2.5 py-2 font-mono text-xs text-[#F2EFE9] focus:border-[#D95D24] focus:outline-none"
                        >
                            <option value="low">LOW</option>
                            <option value="medium">MEDIUM</option>
                            <option value="high">HIGH</option>
                        </select>
                    </div>
                    <div>
                        <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-[0.16em] text-[#8E867D]" htmlFor="task-due">
                            Due Date
                        </label>
                        <input
                            id="task-due"
                            type="date"
                            value={form.dueDate}
                            onChange={updateField('dueDate')}
                            className="w-full border border-[#F2EFE9]/15 bg-[#060606] px-2.5 py-2 font-mono text-xs text-[#F2EFE9] focus:border-[#D95D24] focus:outline-none [color-scheme:dark]"
                        />
                    </div>
                </div>

                {error && (
                    <p className="border border-[#D95D24] bg-[#1F0F09] p-2.5 font-mono text-xs text-[#F2EFE9]">
                        // {error}
                    </p>
                )}

                <button
                    type="submit"
                    disabled={!form.title.trim() || saving}
                    className="w-full border border-[#D95D24] bg-[#D95D24] py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-[#060606] transition-colors hover:bg-[#E86B30] disabled:cursor-not-allowed disabled:opacity-40"
                >
                    {saving ? '[saving...]' : isEditing ? '[save_changes]' : '[+ create_task]'}
                </button>
            </form>
        </section>
    );
};

export default TaskEditor;
