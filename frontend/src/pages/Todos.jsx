import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useAppData } from '../context/AppDataContext';
import { taskService } from '../services/taskService';
import TaskCard from '../components/TaskCard';
import TaskEditor from '../components/TaskEditor';
import ConfirmationModal from '../components/ConfirmationModal';
import { buildAsciiBar } from '../utils/asciiUtils';

const Todos = () => {
    const { currentUser } = useAuth();
    const { revision } = useAppData();
    const [tasks, setTasks] = useState([]);
    const [editingTask, setEditingTask] = useState(null);
    const [filter, setFilter] = useState('all');
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
        const matchesSearch = String(task.title || '').toLowerCase().includes(search.toLowerCase());
        return matchesFilter && matchesSearch;
    });

    const sortedTasks = [...filteredTasks].sort((a, b) => {
        if (a.completed === b.completed) {
            const p = { high: 3, medium: 2, low: 1 };
            return (p[b.priority] || 0) - (p[a.priority] || 0);
        }
        return a.completed ? 1 : -1;
    });

    const completedCount = tasks.filter((t) => t.completed).length;
    const pct = tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0;

    const handleToggleTask = async (taskId, status) => {
        try {
            await taskService.toggleTaskCompletion(taskId, status);
            setTasks(await taskService.getTasks(true));
        } catch (error) {
            console.error('Error toggling task:', error);
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
    };

    if (loading) {
        return (
            <div className="py-16 text-center font-mono text-xs uppercase tracking-[0.18em] text-[#8E867D]">
                // loading task queue...
            </div>
        );
    }

    return (
        <div className="mx-auto max-w-6xl space-y-6 pb-12">
            {/* ASCII Telemetry Header */}
            <div className="flex flex-col justify-between gap-4 border-b border-[#F2EFE9]/14 pb-4 md:flex-row md:items-end">
                <div>
                    <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#D95D24]">
                        01 // execution_queue
                    </span>
                    <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[#F2EFE9]">Tasks</h1>
                </div>
                <div className="flex flex-wrap items-center gap-4 font-mono text-xs">
                    <div className="border border-[#F2EFE9]/12 bg-[#0B0A09] px-3 py-1.5">
                        <span className="text-[#8E867D]">DONE </span>
                        <span className="text-[#D95D24]">[{buildAsciiBar(pct, 12)}]</span>
                        <span className="ml-2 text-[#F2EFE9]">{completedCount}/{tasks.length}</span>
                    </div>
                    <button
                        type="button"
                        onClick={() => setEditingTask(null)}
                        className="border border-[#D95D24] bg-[#D95D24] px-3.5 py-1.5 font-semibold uppercase tracking-[0.12em] text-[#060606] hover:bg-[#E86B30]"
                    >
                        [+ new_task]
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_330px]">
                <div className="min-w-0 space-y-4">
                    {/* Search + Filter Strip */}
                    <div className="flex flex-col gap-2.5 sm:flex-row">
                        <input
                            type="text"
                            placeholder="Filter tasks..."
                            className="flex-1 border border-[#F2EFE9]/14 bg-[#0A0908] px-3.5 py-2 font-mono text-xs text-[#F2EFE9] placeholder:text-[#615A52] focus:border-[#D95D24] focus:outline-none"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                        <div className="flex items-center gap-1 border border-[#F2EFE9]/14 bg-[#0A0908] p-1 font-mono text-[10px] uppercase tracking-[0.12em]">
                            {[
                                { id: 'all', label: 'All' },
                                { id: 'pending', label: 'Open' },
                                { id: 'completed', label: 'Done' },
                                { id: 'high', label: 'High' },
                            ].map((opt) => (
                                <button
                                    key={opt.id}
                                    type="button"
                                    onClick={() => setFilter(opt.id)}
                                    className={`px-2.5 py-1.5 transition-colors ${
                                        filter === opt.id
                                            ? 'bg-[#D95D24] font-semibold text-[#060606]'
                                            : 'text-[#8E867D] hover:text-[#F2EFE9]'
                                    }`}
                                >
                                    {opt.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Task Cards */}
                    <div data-spidey-section="tasks" className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {sortedTasks.map((task) => (
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

                        {sortedTasks.length === 0 && (
                            <div className="col-span-full border border-[#F2EFE9]/12 bg-[#0A0908] py-14 text-center font-mono text-xs uppercase tracking-[0.14em] text-[#7D756C]">
                                // queue empty — all clear
                            </div>
                        )}
                    </div>
                </div>

                {/* Docked Task Editor */}
                <div className="lg:sticky lg:top-4">
                    <TaskEditor
                        key={editingTask?.id || 'new'}
                        task={editingTask}
                        onSave={handleSaveTask}
                        onCancel={() => setEditingTask(null)}
                    />
                </div>
            </div>

            <ConfirmationModal
                isOpen={isDeleteModalOpen}
                onClose={() => setIsDeleteModalOpen(false)}
                onConfirm={confirmDeleteTask}
                title="Delete this task?"
                message="This task will be permanently removed from your queue."
            />
        </div>
    );
};

export default Todos;
