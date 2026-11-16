import { useEffect, useRef, useState } from 'react';
import { Check, Plus, X } from 'lucide-react';

const emptyForm = { title: '', description: '', priority: 'medium', dueDate: '' };

const toDateInput = (value) => (
    typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : ''
);

const TaskEditor = ({ task, onSave, onCancel }) => {
    const [form, setForm] = useState(emptyForm);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const panelRef = useRef(null);
    const isEditing = Boolean(task);

    useEffect(() => {
        setForm(task ? {
            title: task.title || '',
            description: task.description || '',
            priority: task.priority || 'medium',
            dueDate: toDateInput(task.dueDate)
        } : emptyForm);
        setSaving(false);
        setError('');
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
        // Keep any stored time-of-day when the date itself did not change.
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
        <section ref={panelRef} className="border border-[#F2EFE9]/15 bg-[#151515] p-5">
            <div className="flex items-start justify-between gap-3 border-b border-[#F2EFE9]/10 pb-3">
                <div>
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#9C968E]">
                        {isEditing ? 'Editing task' : 'New task'}
                    </p>
                    <h2 className="mt-1 text-base font-bold uppercase tracking-[0.1em] text-[#F2EFE9]">
                        {isEditing ? 'Task details' : 'Add a task'}
                    </h2>
                </div>
                {isEditing && (
                    <button
                        type="button"
                        onClick={onCancel}
                        className="p-1 text-[#9C968E] transition-colors hover:text-[#F2EFE9]"
                        aria-label="Stop editing this task"
                    >
                        <X size={16} />
                    </button>
                )}
            </div>

            {isEditing && (
                <p className="mt-3 truncate border border-[#D95D24]/40 bg-[#1B1612] px-3 py-2 font-mono text-xs text-[#F2EFE9]">
                    #{task.id} · {task.title}
                </p>
            )}

            <form onSubmit={handleSubmit} className="mt-4 space-y-4">
                <div>
                    <label className="mb-1.5 block font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-[#9C968E]" htmlFor="task-title">Title</label>
                    <input
                        id="task-title"
                        type="text"
                        required
                        value={form.title}
                        onChange={updateField('title')}
                        maxLength={500}
                        placeholder="What needs doing?"
                        className="w-full border border-[#F2EFE9]/15 bg-[#111111] px-3 py-2.5 text-sm text-[#F2EFE9] placeholder:text-[#9C968E]/50 focus:border-[#D95D24] focus:outline-none"
                    />
                </div>

                <div>
                    <label className="mb-1.5 block font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-[#9C968E]" htmlFor="task-desc">Description</label>
                    <textarea
                        id="task-desc"
                        value={form.description}
                        onChange={updateField('description')}
                        maxLength={2000}
                        rows={3}
                        placeholder="Add a note, if it helps..."
                        className="w-full resize-y border border-[#F2EFE9]/15 bg-[#111111] px-3 py-2.5 text-sm text-[#F2EFE9] placeholder:text-[#9C968E]/50 focus:border-[#D95D24] focus:outline-none"
                    />
                </div>

                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="mb-1.5 block font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-[#9C968E]" htmlFor="task-priority">Priority</label>
                        <select
                            id="task-priority"
                            value={form.priority}
                            onChange={updateField('priority')}
                            className="w-full border border-[#F2EFE9]/15 bg-[#111111] px-2.5 py-2.5 font-mono text-xs text-[#F2EFE9] focus:border-[#D95D24] focus:outline-none"
                        >
                            <option value="low">LOW</option>
                            <option value="medium">MEDIUM</option>
                            <option value="high">HIGH</option>
                        </select>
                    </div>
                    <div>
                        <label className="mb-1.5 block font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-[#9C968E]" htmlFor="task-due">Due date</label>
                        <input
                            id="task-due"
                            type="date"
                            value={form.dueDate}
                            onChange={updateField('dueDate')}
                            className="w-full border border-[#F2EFE9]/15 bg-[#111111] px-2.5 py-2.5 font-mono text-xs text-[#F2EFE9] focus:border-[#D95D24] focus:outline-none [color-scheme:dark]"
                        />
                    </div>
                </div>

                {error && (
                    <p className="border border-[#D95D24] bg-[#1E130F] p-3 font-mono text-xs text-[#F2EFE9]">{error}</p>
                )}

                <button
                    type="submit"
                    disabled={!form.title.trim() || saving}
                    className="flex w-full items-center justify-center gap-2 border border-[#D95D24] bg-[#D95D24] py-3 font-mono text-xs font-bold uppercase tracking-[0.16em] text-[#111111] transition-colors hover:bg-[#C44E19] disabled:cursor-not-allowed disabled:opacity-40"
                >
                    {isEditing ? <Check size={14} /> : <Plus size={14} />}
                    {saving ? 'Saving...' : isEditing ? 'Save changes' : 'Create task'}
                </button>
            </form>
        </section>
    );
};

export default TaskEditor;
