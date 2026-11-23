import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useAppData } from '../context/AppDataContext';
import { habitService } from '../services/habitService';
import { Activity, BookOpen, Droplets, Moon, Sun, Zap, Coffee, Music, Code } from 'lucide-react';
import HabitCard from '../components/HabitCard';
import { AnimatePresence, motion } from 'framer-motion';
import ConfirmationModal from '../components/ConfirmationModal';
import { localDateKey } from '../utils/dateUtils';
import { buildAsciiBar } from '../utils/asciiUtils';

const icons = [
    { name: 'Activity', component: Activity },
    { name: 'BookOpen', component: BookOpen },
    { name: 'Droplets', component: Droplets },
    { name: 'Moon', component: Moon },
    { name: 'Sun', component: Sun },
    { name: 'Zap', component: Zap },
    { name: 'Coffee', component: Coffee },
    { name: 'Music', component: Music },
    { name: 'Code', component: Code },
];

const Habits = () => {
    const { currentUser } = useAuth();
    const { revision } = useAppData();
    const [habits, setHabits] = useState([]);

    const [isModalOpen, setIsModalOpen] = useState(false);
    const [habitBeingEdited, setHabitBeingEdited] = useState(null);
    const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
    const [habitToDelete, setHabitToDelete] = useState(null);

    const [newHabitName, setNewHabitName] = useState('');
    const [selectedIcon, setSelectedIcon] = useState('Activity');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (currentUser) {
            habitService.getHabits().then((data) => {
                setHabits(data);
                setLoading(false);
            }).catch((error) => {
                console.error('Error loading habits:', error);
                setLoading(false);
            });
        }
    }, [currentUser, revision]);

    const handleAddHabit = async (e) => {
        e.preventDefault();
        if (!newHabitName.trim()) return;
        try {
            if (habitBeingEdited) {
                await habitService.updateHabit(habitBeingEdited.id, {
                    name: newHabitName,
                    icon: selectedIcon,
                    dailyGoal: 1,
                });
            } else {
                await habitService.addHabit(currentUser.uid, {
                    name: newHabitName,
                    icon: selectedIcon,
                    dailyGoal: 1,
                });
            }
            setNewHabitName('');
            setSelectedIcon('Activity');
            setIsModalOpen(false);
            setHabitBeingEdited(null);
            setHabits(await habitService.getHabits());
        } catch (error) {
            console.error('Error adding habit:', error);
        }
    };

    const openEditHabit = (habit) => {
        setHabitBeingEdited(habit);
        setNewHabitName(habit.name);
        setSelectedIcon(habit.icon || 'Activity');
        setIsModalOpen(true);
    };

    const handleToggleHabit = async (habit) => {
        const today = localDateKey();
        try {
            await habitService.toggleHabitCompletion(habit.id, currentUser.uid, today, habit.completedDates || []);
            setHabits(await habitService.getHabits());
        } catch (error) {
            console.error('Error toggling habit:', error);
        }
    };

    const confirmDeleteHabit = async () => {
        if (habitToDelete) {
            try {
                await habitService.deleteHabit(habitToDelete);
                setHabits(await habitService.getHabits());
                setHabitToDelete(null);
            } catch (error) {
                console.error('Error deleting habit:', error);
            }
        }
    };

    if (loading) {
        return (
            <div className="py-16 text-center font-mono text-xs uppercase tracking-[0.18em] text-[#8E867D]">
                // loading discipline matrix...
            </div>
        );
    }

    const today = localDateKey();
    const doneToday = habits.filter((h) => h.completedDates?.includes(today)).length;
    const pct = habits.length > 0 ? Math.round((doneToday / habits.length) * 100) : 0;

    return (
        <div className="mx-auto max-w-6xl space-y-6 pb-12">
            {/* ASCII Discipline Header */}
            <div className="flex flex-col justify-between gap-4 border-b border-[#F2EFE9]/14 pb-4 md:flex-row md:items-end">
                <div>
                    <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#D95D24]">
                        02 // daily_discipline
                    </span>
                    <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[#F2EFE9]">Habits</h1>
                </div>

                <div className="flex flex-wrap items-center gap-4 font-mono text-xs">
                    <div className="border border-[#F2EFE9]/12 bg-[#0B0A09] px-3 py-1.5">
                        <span className="text-[#8E867D]">TODAY </span>
                        <span className="text-[#D95D24]">[{buildAsciiBar(pct, 12)}]</span>
                        <span className="ml-2 text-[#F2EFE9]">{doneToday}/{habits.length}</span>
                    </div>
                    <button
                        type="button"
                        onClick={() => {
                            setHabitBeingEdited(null);
                            setNewHabitName('');
                            setSelectedIcon('Activity');
                            setIsModalOpen(true);
                        }}
                        className="border border-[#D95D24] bg-[#D95D24] px-3.5 py-1.5 font-semibold uppercase tracking-[0.12em] text-[#060606] hover:bg-[#E86B30]"
                    >
                        [+ new_habit]
                    </button>
                </div>
            </div>

            <div data-spidey-section="habits" className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
                <AnimatePresence>
                    {habits.map((habit) => (
                        <HabitCard
                            key={habit.id}
                            habit={habit}
                            onToggle={handleToggleHabit}
                            onEdit={openEditHabit}
                            onDelete={(id) => {
                                setHabitToDelete(id);
                                setIsDeleteModalOpen(true);
                            }}
                        />
                    ))}
                </AnimatePresence>

                {habits.length === 0 && (
                    <div className="col-span-full border border-[#F2EFE9]/12 bg-[#0A0908] py-16 text-center font-mono text-xs uppercase tracking-[0.14em] text-[#7D756C]">
                        // no habits tracked yet — click [+ new_habit] to start a streak
                    </div>
                )}
            </div>

            <ConfirmationModal
                isOpen={isDeleteModalOpen}
                onClose={() => setIsDeleteModalOpen(false)}
                onConfirm={confirmDeleteHabit}
                title="Remove this habit?"
                message="This will remove the habit and its streak history."
            />

            <AnimatePresence>
                {isModalOpen && (
                    <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4">
                        <motion.div
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 4 }}
                            className="ascii-frame relative w-full max-w-md bg-[#0A0908] p-6"
                        >
                            <div className="mb-5 flex items-center justify-between border-b border-[#F2EFE9]/12 pb-3 font-mono text-[10px] uppercase tracking-[0.16em]">
                                <span className="text-[#D95D24]">
                                    {habitBeingEdited ? '// edit_habit' : '// new_habit'}
                                </span>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setIsModalOpen(false);
                                        setHabitBeingEdited(null);
                                    }}
                                    className="text-[#8E867D] hover:text-[#F2EFE9]"
                                >
                                    [x]
                                </button>
                            </div>

                            <form onSubmit={handleAddHabit} className="space-y-5">
                                <div>
                                    <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">
                                        Habit Name
                                    </label>
                                    <input
                                        type="text"
                                        value={newHabitName}
                                        onChange={(e) => setNewHabitName(e.target.value)}
                                        className="w-full border border-[#F2EFE9]/15 bg-[#060606] px-3.5 py-2.5 text-sm text-[#F2EFE9] placeholder:text-[#5C564F] focus:border-[#D95D24] focus:outline-none"
                                        placeholder="e.g. Deep work 60 min"
                                        autoFocus
                                    />
                                </div>

                                <div>
                                    <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">
                                        Symbol
                                    </label>
                                    <div className="grid grid-cols-5 gap-2">
                                        {icons.map(({ name, component: Icon }) => (
                                            <button
                                                key={name}
                                                type="button"
                                                onClick={() => setSelectedIcon(name)}
                                                className={`flex items-center justify-center border p-2.5 transition-colors ${
                                                    selectedIcon === name
                                                        ? 'border-[#D95D24] bg-[#D95D24] text-[#060606]'
                                                        : 'border-[#F2EFE9]/12 bg-[#060606] text-[#8E867D] hover:border-[#F2EFE9]/35 hover:text-[#F2EFE9]'
                                                }`}
                                            >
                                                <Icon size={17} />
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                <button
                                    type="submit"
                                    disabled={!newHabitName.trim()}
                                    className="w-full border border-[#D95D24] bg-[#D95D24] py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-[#060606] hover:bg-[#E86B30] disabled:opacity-40"
                                >
                                    {habitBeingEdited ? '[save_habit]' : '[+ add_habit]'}
                                </button>
                            </form>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default Habits;
