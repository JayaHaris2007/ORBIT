import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useAppData } from '../context/AppDataContext';
import { taskService } from '../services/taskService';
import { Plus, Search } from 'lucide-react';
import TaskCard from '../components/TaskCard';
import TaskEditor from '../components/TaskEditor';
import { AnimatePresence } from 'framer-motion';

import ConfirmationModal from '../components/ConfirmationModal';

const Todos = () => {
    const { currentUser } = useAuth();
    const { revision } = useAppData();
    const [tasks, setTasks] = useState([]);
    const [editingTask, setEditingTask] = useState(null);
    const [filter, setFilter] = useState('all'); // all, pending, completed
    const [search, setSearch] = useState('');

    const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
    const [taskToDelete, setTaskToDelete] = useState(null);

    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!currentUser) return;
        taskService.getTasks(true).then((data) => {
            setTasks(data);
            setLoading(false);
        }).catch((error) => {
            console.error('Error loading tasks:', error);
            setLoading(false);
        });
    }, [currentUser, revision]);

    useEffect(() => {
        const handleUiAction = (event) => {
            const action = event?.detail;
            if (!action) return;
            if (action.type === 'apply_filter' && (!action.target || action.target === 'tasks' || action.target === 'todos')) {
                const val = String(action.value || '').toLowerCase().trim();
                if (['all', 'pending', 'completed', 'high', 'medium', 'low'].includes(val)) {
                    setFilter(val);
                } else if (val) {
                    setSearch(val);
                }
            } else if (action.type === 'open_modal' && action.value) {
                const found = tasks.find((t) => String(t.id) === String(action.value) || t.title.toLowerCase().includes(String(action.value).toLowerCase()));
                if (found) setEditingTask(found);
            }
        };
        window.addEventListener('orbit:ui_action', handleUiAction);
        return () => window.removeEventListener('orbit:ui_action', handleUiAction);
    }, [tasks]);

    const filteredTasks = tasks.filter(task => {
        const matchesFilter =
            filter === 'all' ? true :
                filter === 'completed' ? task.completed :
                    filter === 'pending' ? !task.completed :
                        ['high', 'medium', 'low'].includes(filter) ? (!task.completed && task.priority === filter) :
                            !task.completed;

        const matchesSearch = task.title.toLowerCase().includes(search.toLowerCase());

        return matchesFilter && matchesSearch;
    });

    // Sort by completed (bottom) then priority (high > medium > low)
    const sortedTasks = filteredTasks.sort((a, b) => {
        if (a.completed === b.completed) {
            const p = { high: 3, medium: 2, low: 1 };
            return p[b.priority] - p[a.priority];
        }
        return a.completed ? 1 : -1;
    });

    const handleToggleTask = async (taskId, status) => {
        try {
            await taskService.toggleTaskCompletion(taskId, status);
            setTasks(await taskService.getTasks(true));
        } catch (error) {
            console.error("Error toggling task:", error);
        }
    };

    const handleSaveTask = async (values) => {
        if (editingTask) {
            const updated = await taskService.updateTask(editingTask.id, values);
            setTasks((current) => current.map((task) => (task.id === updated.id ? updated : task)));
            setEditingTask(updated);
        } else {
            const created = await taskService.addTask(currentUser?.uid, values);
            setTasks((current) => [created, ...current]);
        }
    };

    const confirmDeleteTask = async () => {
        if (taskToDelete) {
            try {
                await taskService.deleteTask(taskToDelete);
                setTasks(await taskService.getTasks(true));
                if (editingTask?.id === taskToDelete) setEditingTask(null);
                setTaskToDelete(null);
            } catch (error) {
                console.error(error);
            }
        }
    }

    if (loading) {
        return (
            <div className="py-16 text-center font-mono text-xs uppercase tracking-[0.18em] text-[#9C968E] animate-pulse">
                Loading your tasks...
            </div>
        );
    }

    return (
        <div className="pb-20">
            <div className="mb-8 flex flex-col items-start justify-between gap-4 border-b border-[#F2EFE9]/15 pb-5 md:flex-row md:items-end">
                <div>
                    <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#D95D24]">03 · Execution</span>
                    <h1 className="mt-1 text-3xl font-bold uppercase tracking-[0.14em] text-[#F2EFE9]">Your tasks</h1>
                    <p className="mt-1 font-mono text-xs text-[#9C968E]">Keep the important things moving.</p>
                </div>

                <button
                    onClick={() => setEditingTask(null)}
                    className="flex items-center gap-2 border border-[#D95D24] bg-[#D95D24] px-4 py-2 font-mono text-xs font-bold uppercase tracking-[0.14em] text-[#111111] transition-colors hover:bg-[#C44E19]"
                >
                    <Plus size={16} />
                    <span>New task</span>
                </button>
            </div>

            <div className="grid grid-cols-1 items-start gap-6 2xl:grid-cols-[minmax(0,1fr)_340px]">
                <div className="min-w-0">
                    {/* Controls */}
                    <div className="mb-6 flex flex-col gap-3">
                        <div className="relative w-full">
                            <Search className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[#9C968E]" size={16} />
                            <input
                                type="text"
                                placeholder="Search your tasks..."
                                className="w-full border border-[#F2EFE9]/15 bg-[#151515] py-2.5 pl-10 pr-4 font-mono text-xs text-[#F2EFE9] placeholder:text-[#9C968E]/60 transition-colors focus:border-[#D95D24] focus:outline-none"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                            />
                        </div>

                        <div className="flex flex-wrap items-center gap-1 border border-[#F2EFE9]/15 bg-[#151515] p-1">
                            {[
                                { id: 'all', label: 'All' },
                                { id: 'pending', label: 'Pending' },
                                { id: 'completed', label: 'Completed' },
                                { id: 'high', label: 'High Priority' },
                            ].map((opt) => (
                                <button
                                    key={opt.id}
                                    type="button"
                                    onClick={() => setFilter(opt.id)}
                                    className={`flex-1 whitespace-nowrap px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] transition-colors ${
                                        filter === opt.id
                                            ? 'bg-[#D95D24] text-[#111111]'
                                            : 'text-[#9C968E] hover:bg-[#1D1D1D] hover:text-[#F2EFE9]'
                                    }`}
                                >
                                    {opt.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Task List */}
                    <div data-spidey-section="tasks" className="space-y-3">
                        <AnimatePresence>
                            {sortedTasks.map(task => (
                                <TaskCard
                                    key={task.id}
                                    task={task}
                                    onToggle={handleToggleTask}
                                    onEdit={setEditingTask}
                                    onDelete={(id) => {
                                        setTaskToDelete(id);
                                        setIsDeleteModalOpen(true);
                                    }}
                                />
                            ))}
                        </AnimatePresence>

                        {sortedTasks.length === 0 && (
                            <div className="border border-[#F2EFE9]/14 bg-[#151515] py-16 text-center font-mono text-xs uppercase tracking-[0.14em] text-[#9C968E]">
                                Nothing here yet. You&apos;re doing great.
                            </div>
                        )}
                    </div>
                </div>

                {/* Task editor, docked on the right of the page */}
                <div className="2xl:sticky 2xl:top-6">
                    <TaskEditor
                        task={editingTask}
                        onSave={handleSaveTask}
                        onCancel={() => setEditingTask(null)}
                    />
                </div>
            </div>

            {/* Confirmation Modal */}
            <ConfirmationModal
                isOpen={isDeleteModalOpen}
                onClose={() => setIsDeleteModalOpen(false)}
                onConfirm={confirmDeleteTask}
                title="Delete this task?"
                message="This task will be removed from your list."
            />
        </div>
    );
};

export default Todos;
