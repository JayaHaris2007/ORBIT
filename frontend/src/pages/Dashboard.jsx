import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { useAppData } from '../context/AppDataContext';
import { habitService } from '../services/habitService';
import { taskService } from '../services/taskService';
import { learningService } from '../services/learningService';
import { format } from 'date-fns';
import { Focus } from 'lucide-react';
import { motion } from 'framer-motion';
import HabitCard from '../components/HabitCard';
import TaskCard from '../components/TaskCard';
import AnimeQuote from '../components/AnimeQuote';
import ConfirmationModal from '../components/ConfirmationModal';
import TaskEditor from '../components/TaskEditor';
import NeuralCoreDeck from '../components/three/NeuralCoreDeck';
import { PlotterSectionHeader } from '../components/editorial/PlotterArtwork';

const EASE_MECH = [0.22, 1, 0.36, 1];

const STAGGER_CONTAINER = {
    hidden: { opacity: 0 },
    show: {
        opacity: 1,
        transition: {
            staggerChildren: 0.06,
        },
    },
};

const STAGGER_ITEM = {
    hidden: { opacity: 0, y: 10 },
    show: {
        opacity: 1,
        y: 0,
        transition: { duration: 0.28, ease: EASE_MECH },
    },
};

const Dashboard = () => {
    const { currentUser } = useAuth();
    const { revision } = useAppData();
    const [habits, setHabits] = useState([]);
    const [tasks, setTasks] = useState([]);
    const [learningProgress, setLearningProgress] = useState(null);
    const [nextTopics, setNextTopics] = useState([]);
    const [editingTask, setEditingTask] = useState(null);
    const [focusMode, setFocusMode] = useState(false);
    const [loading, setLoading] = useState(true);
    const [userData, setUserData] = useState(null);

    const [deleteConfig, setDeleteConfig] = useState({
        isOpen: false,
        type: null, // 'habit' | 'task'
        id: null,
        title: '',
        message: '',
    });

    const loadDashboardData = useCallback(async () => {
        try {
            const [habitData, taskData, gamification, progressData, nextData] = await Promise.all([
                habitService.getHabits(),
                taskService.getTasks(true),
                habitService.getGamification(),
                learningService.getProgress().catch(() => null),
                learningService.getNext(3).catch(() => []),
            ]);
            setHabits(habitData);
            setTasks(taskData);
            setUserData(gamification);
            setLearningProgress(progressData);
            setNextTopics(nextData || []);
        } catch (error) {
            console.error('Error loading dashboard:', error);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (currentUser) {
            loadDashboardData();
        }
    }, [currentUser, revision, loadDashboardData]);

    const today = format(new Date(), 'yyyy-MM-dd');
    const todaysHabits = habits;
    const completedHabitsCount = habits.filter((h) => h.completedDates?.includes(today)).length;
    const totalHabitsCount = habits.length;
    const pendingTasks = tasks.filter((t) => !t.completed);
    const completedTasks = tasks.filter((t) => t.completed);

    const focusHabits = habits.filter((h) => !h.completedDates?.includes(today));
    const priorityRank = { high: 3, medium: 2, low: 1 };
    const focusTasks = [...pendingTasks]
        .sort((a, b) => (priorityRank[b.priority] || 0) - (priorityRank[a.priority] || 0))
        .slice(0, 3);

    const handleToggleHabit = async (habit) => {
        try {
            await habitService.toggleHabitCompletion(habit.id, currentUser.uid, today, habit.completedDates || []);
            setHabits(await habitService.getHabits());
            setUserData(await habitService.getGamification());
        } catch (error) {
            console.error(error);
        }
    };

    const handleToggleTask = async (taskId, status) => {
        try {
            await taskService.toggleTaskCompletion(taskId, status);
            setTasks(await taskService.getTasks(true));
        } catch (error) {
            console.error(error);
        }
    };

    const handleQuickStartTopic = async (topic) => {
        if (!topic?.topicId) return;
        try {
            await learningService.updateTopic(topic.topicId, { status: 'learning' });
            const [progressData, nextData] = await Promise.all([
                learningService.getProgress().catch(() => null),
                learningService.getNext(3).catch(() => []),
            ]);
            setLearningProgress(progressData);
            setNextTopics(nextData || []);
        } catch (error) {
            console.error(error);
        }
    };

    const confirmDelete = async () => {
        const { type, id } = deleteConfig;
        if (!id) return;

        try {
            if (type === 'task') {
                await taskService.deleteTask(id);
                setTasks(await taskService.getTasks(true));
                if (editingTask?.id === id) setEditingTask(null);
            } else if (type === 'habit') {
                await habitService.deleteHabit(id);
                setHabits(await habitService.getHabits());
                setUserData(await habitService.getGamification());
            }
        } catch (error) {
            console.error(error);
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

    if (loading) {
        return (
            <div className="border border-[#F2EFE9]/15 bg-[#141414] p-10 text-center font-mono text-xs uppercase tracking-[0.2em] text-[#9C968E]">
                Initializing workspace...
            </div>
        );
    }

    return (
        <motion.div
            variants={STAGGER_CONTAINER}
            initial="hidden"
            animate="show"
            className="space-y-8 pb-20"
        >
            {/* Editorial Title Row */}
            <motion.header
                variants={STAGGER_ITEM}
                className="flex flex-col justify-between gap-4 border-b border-[#F2EFE9]/15 pb-5 md:flex-row md:items-end"
            >
                <div>
                    <div className="flex items-center gap-2.5">
                        <span className="h-2 w-2 bg-[#D95D24]" />
                        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-[#9C968E]">
                            {format(new Date(), 'EEEE · MMMM d, yyyy')}
                        </span>
                    </div>
                    <h1 className="mt-2 text-3xl font-bold uppercase tracking-[0.14em] text-[#F2EFE9] md:text-4xl">
                        {focusMode ? 'Focus Mode' : 'Command Center'}
                    </h1>
                </div>

                <button
                    type="button"
                    onClick={() => setFocusMode(!focusMode)}
                    className={`inline-flex items-center gap-2 border px-4 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.16em] transition-colors ${
                        focusMode
                            ? 'border-[#D95D24] bg-[#D95D24] text-[#111111]'
                            : 'border-[#F2EFE9]/20 bg-[#151515] text-[#F2EFE9] hover:border-[#D95D24] hover:text-[#D95D24]'
                    }`}
                >
                    <Focus size={14} />
                    <span>{focusMode ? 'Exit Focus' : 'Focus Mode'}</span>
                </button>
            </motion.header>

            {/* Merged S.P.I.D.E.Y. Neural Matrix + Personal Telemetry */}
            <motion.div variants={STAGGER_ITEM}>
                <NeuralCoreDeck
                    userName={currentUser?.displayName || 'Shadow Hunter'}
                    pendingTasksCount={pendingTasks.length}
                    completedTasksCount={completedTasks.length}
                    completedHabitsCount={completedHabitsCount}
                    totalHabitsCount={totalHabitsCount}
                    xp={userData?.xp || 0}
                    streak={userData?.globalStreak || 0}
                    topTask={focusTasks[0] || null}
                    nextTopic={nextTopics[0] || null}
                    learningProgress={learningProgress}
                    onQuickCompleteTask={(taskId) => handleToggleTask(taskId, true)}
                    onQuickStartTopic={handleQuickStartTopic}
                />
            </motion.div>

            {/* Habits, Tasks & Task Editor Hairline Grid */}
            <motion.div
                variants={STAGGER_ITEM}
                className="grid grid-cols-1 items-start gap-8 md:grid-cols-2 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_320px]"
            >
                {/* Habits Section */}
                <section data-spidey-section="habits">
                    <PlotterSectionHeader
                        index="01"
                        title={focusMode ? 'Pending Habits' : 'Daily Habits'}
                        rightLabel={`${completedHabitsCount}/${totalHabitsCount}`}
                    />
                    <div className="space-y-3">
                        {(focusMode ? focusHabits : todaysHabits).map((habit) => (
                            <HabitCard
                                key={habit.id}
                                habit={habit}
                                onToggle={handleToggleHabit}
                                onDelete={(id) =>
                                    setDeleteConfig({
                                        isOpen: true,
                                        type: 'habit',
                                        id,
                                        title: 'Remove this habit?',
                                        message: 'Remove this habit from your dashboard?',
                                    })
                                }
                            />
                        ))}
                        {(focusMode ? focusHabits : todaysHabits).length === 0 && (
                            <p className="border-l border-[#D95D24] py-2 pl-4 font-mono text-xs text-[#9C968E]">
                                All daily habits complete.
                            </p>
                        )}
                    </div>
                </section>

                {/* Tasks Section */}
                <section data-spidey-section="tasks">
                    <PlotterSectionHeader
                        index="02"
                        title={focusMode ? 'Priority Queue' : 'Active Tasks'}
                        rightLabel={`${pendingTasks.length} OPEN`}
                    />
                    <div className="space-y-3">
                        {(focusMode ? focusTasks : pendingTasks.slice(0, 6)).map((task) => (
                            <TaskCard
                                key={task.id}
                                task={task}
                                onToggle={handleToggleTask}
                                onEdit={setEditingTask}
                                onDelete={(id) =>
                                    setDeleteConfig({
                                        isOpen: true,
                                        type: 'task',
                                        id,
                                        title: 'Remove Task',
                                        message: 'Remove this task from your active list?',
                                    })
                                }
                            />
                        ))}
                        {(focusMode ? focusTasks : pendingTasks).length === 0 && (
                            <p className="border-l border-[#D95D24] py-2 pl-4 font-mono text-xs text-[#9C968E]">
                                No pending tasks.
                            </p>
                        )}
                    </div>
                </section>

                {/* Task Editor */}
                <div className="2xl:sticky 2xl:top-6">
                    <PlotterSectionHeader
                        index="03"
                        title={editingTask ? 'Edit Task' : 'New Entry'}
                    />
                    <TaskEditor
                        task={editingTask}
                        onSave={handleSaveTask}
                        onCancel={() => setEditingTask(null)}
                    />
                </div>
            </motion.div>

            {/* Minimal Print-Poster Quote Footer */}
            {!focusMode && (
                <motion.div variants={STAGGER_ITEM}>
                    <AnimeQuote />
                </motion.div>
            )}

            <ConfirmationModal
                isOpen={deleteConfig.isOpen}
                onClose={() => setDeleteConfig({ ...deleteConfig, isOpen: false })}
                onConfirm={confirmDelete}
                title={deleteConfig.title}
                message={deleteConfig.message}
            />
        </motion.div>
    );
};

export default Dashboard;
