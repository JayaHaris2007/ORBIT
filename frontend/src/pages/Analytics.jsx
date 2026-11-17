import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useAppData } from '../context/AppDataContext';
import { habitService } from '../services/habitService';
import { taskService } from '../services/taskService';
import { learningService } from '../services/learningService';
import { format, subDays } from 'date-fns';
import { motion } from 'framer-motion';
import { Flame, Calendar, Trophy, BarChart3, Grid, ChevronLeft, ChevronRight, BookOpen, CheckSquare, Activity } from 'lucide-react';
import YearlyHeatmap from '../components/analytics/YearlyHeatmap';
import MonthlyChart from '../components/analytics/MonthlyChart';
import WeekdayChart from '../components/analytics/WeekdayChart';
import { calculateDailyCompletions, calculateMonthlyStats, calculateWeekdayStats, calculateYearlyTotal } from '../utils/analyticsUtils';

const Analytics = () => {
    const { currentUser } = useAuth();
    const { revision } = useAppData();
    const [habits, setHabits] = useState([]);
    const [tasks, setTasks] = useState([]);
    const [learningProgress, setLearningProgress] = useState(null);
    const [loading, setLoading] = useState(true);
    const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());

    // Generate last 7 days for weekly view
    const last7Days = Array.from({ length: 7 }, (_, i) => {
        const date = subDays(new Date(), 6 - i); // 6 days ago to today
        return {
            date,
            label: format(date, 'EEE'), // Mon, Tue...
            fullDate: format(date, 'yyyy-MM-dd')
        };
    });

    useEffect(() => {
        if (!currentUser) return;
        let active = true;
        Promise.all([
            habitService.getHabits().catch(() => []),
            taskService.getTasks(true).catch(() => []),
            learningService.getProgress().catch(() => null),
        ])
            .then(([habitData, taskData, progressData]) => {
                if (!active) return;
                setHabits(Array.isArray(habitData) ? habitData : []);
                setTasks(Array.isArray(taskData) ? taskData : []);
                setLearningProgress(progressData);
                setLoading(false);
            })
            .catch((error) => {
                console.error('Error loading analytics:', error);
                if (active) setLoading(false);
            });
        return () => {
            active = false;
        };
    }, [currentUser, revision]);

    // Calculate overall completion rate for the week
    const getWeeklyCompletionRate = () => {
        if (habits.length === 0) return 0;

        let totalOpportunities = habits.length * 7;
        let totalCompleted = 0;

        habits.forEach(habit => {
            last7Days.forEach(day => {
                if (habit.completedDates?.includes(day.fullDate)) {
                    totalCompleted++;
                }
            });
        });

        return Math.round((totalCompleted / totalOpportunities) * 100);
    };

    const getLongestStreak = () => {
        if (habits.length === 0) return 0;
        return Math.max(...habits.map(h => h.streak || 0));
    };

    const getTopHabit = () => {
        if (habits.length === 0) return null;
        return habits.reduce((prev, current) => (prev.streak > current.streak) ? prev : current);
    }

    if (loading) return <div className="p-10 text-center animate-pulse text-textMuted">Analyzing data...</div>;

    const topHabit = getTopHabit();
    const dailyCompletions = calculateDailyCompletions(habits, selectedYear);
    const monthlyStats = calculateMonthlyStats(habits, selectedYear);
    const weekdayStats = calculateWeekdayStats(habits);
    const yearlyTotal = calculateYearlyTotal(habits, selectedYear);

    const habitRegularityPercent = getWeeklyCompletionRate();
    const completedTasksCount = tasks.filter((t) => t.completed).length;
    const totalTasksCount = tasks.length;
    const taskCompletionPercent = totalTasksCount > 0 ? Math.round((completedTasksCount / totalTasksCount) * 100) : 0;

    const totalTopicsCount = learningProgress?.topicCount ?? 0;
    const completedTopicsCount = learningProgress?.completedTopics ?? 0;
    const inProgressTopicsCount = learningProgress?.inProgressTopics ?? 0;
    const learningPercent = Math.round(learningProgress?.completionPercent ?? 0);
    const perRoadmap = learningProgress?.perRoadmap ?? [];

    const activePillars = [
        habits.length > 0 ? habitRegularityPercent : null,
        totalTasksCount > 0 ? taskCompletionPercent : null,
        totalTopicsCount > 0 ? learningPercent : null,
    ].filter((v) => v !== null);

    const totalProductivePercent = activePillars.length > 0
        ? Math.round(activePillars.reduce((sum, val) => sum + val, 0) / activePillars.length)
        : 0;

    return (
        <div className="space-y-8 pb-20">
            <header className="border-b border-[#F2EFE9]/15 pb-5">
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#D95D24]">06 · Telemetry</span>
                <h1 className="mt-1 text-3xl font-bold uppercase tracking-[0.14em] text-[#F2EFE9]">
                    Analytics
                </h1>
            </header>

            {/* Total Productive Percentage + 3 Pillars */}
            <section className="grid grid-cols-1 gap-6 border border-[#F2EFE9]/15 bg-[#151515] p-6 lg:grid-cols-[300px_minmax(0,1fr)]">
                <div className="flex flex-col justify-between border-b border-[#F2EFE9]/10 pb-6 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-6">
                    <div>
                        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[#D95D24]">
                            <Activity size={13} />
                            <span>Total Productivity</span>
                        </div>
                        <div className="mt-3 flex items-baseline gap-2">
                            <span className="font-mono text-5xl font-bold tracking-tight text-[#F2EFE9]">
                                {totalProductivePercent}%
                            </span>
                            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#9C968E]">
                                Composite
                            </span>
                        </div>
                    </div>

                    <div className="mt-5">
                        <div className="h-2 w-full bg-[#111111] border border-[#F2EFE9]/10">
                            <div
                                className="h-full bg-[#D95D24] transition-all duration-500"
                                style={{ width: `${totalProductivePercent}%` }}
                            />
                        </div>
                        <p className="mt-2 font-mono text-[10px] leading-relaxed text-[#9C968E]">
                            Combined score across habit regularity, task completion, and learning progress.
                        </p>
                    </div>
                </div>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <div className="flex flex-col justify-between border border-[#F2EFE9]/10 bg-[#111111] p-4">
                        <div className="flex items-center justify-between">
                            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
                                Habits Regular
                            </span>
                            <Flame size={14} className="text-[#D95D24]" />
                        </div>
                        <div className="my-3">
                            <div className="font-mono text-2xl font-bold text-[#F2EFE9]">
                                {habitRegularityPercent}%
                            </div>
                            <div className="mt-0.5 font-mono text-[10px] text-[#9C968E]">
                                7-day consistency ({habits.length} active)
                            </div>
                        </div>
                        <div className="h-1.5 w-full bg-[#1C1C1C]">
                            <div
                                className="h-full bg-[#D95D24] transition-all duration-500"
                                style={{ width: `${habitRegularityPercent}%` }}
                            />
                        </div>
                    </div>

                    <div className="flex flex-col justify-between border border-[#F2EFE9]/10 bg-[#111111] p-4">
                        <div className="flex items-center justify-between">
                            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
                                Task Completion
                            </span>
                            <CheckSquare size={14} className="text-[#D95D24]" />
                        </div>
                        <div className="my-3">
                            <div className="font-mono text-2xl font-bold text-[#F2EFE9]">
                                {taskCompletionPercent}%
                            </div>
                            <div className="mt-0.5 font-mono text-[10px] text-[#9C968E]">
                                {completedTasksCount}/{totalTasksCount} tasks completed
                            </div>
                        </div>
                        <div className="h-1.5 w-full bg-[#1C1C1C]">
                            <div
                                className="h-full bg-[#F2EFE9] transition-all duration-500"
                                style={{ width: `${taskCompletionPercent}%` }}
                            />
                        </div>
                    </div>

                    <div className="flex flex-col justify-between border border-[#F2EFE9]/10 bg-[#111111] p-4">
                        <div className="flex items-center justify-between">
                            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
                                Learning Progress
                            </span>
                            <BookOpen size={14} className="text-[#D95D24]" />
                        </div>
                        <div className="my-3">
                            <div className="font-mono text-2xl font-bold text-[#F2EFE9]">
                                {learningPercent}%
                            </div>
                            <div className="mt-0.5 font-mono text-[10px] text-[#9C968E]">
                                {completedTopicsCount}/{totalTopicsCount} topics mastered
                            </div>
                        </div>
                        <div className="h-1.5 w-full bg-[#1C1C1C]">
                            <div
                                className="h-full bg-[#D95D24] transition-all duration-500"
                                style={{ width: `${learningPercent}%` }}
                            />
                        </div>
                    </div>
                </div>
            </section>

            {/* Learning Progress Breakdown */}
            <section data-spidey-section="learning" className="border border-[#F2EFE9]/15 bg-[#151515] p-6">
                <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-[#F2EFE9]/10 pb-4">
                    <div className="flex items-center gap-2">
                        <BookOpen size={15} className="text-[#D95D24]" />
                        <h3 className="font-mono text-xs font-bold uppercase tracking-[0.18em] text-[#F2EFE9]">
                            Learning Progress
                        </h3>
                    </div>
                    <div className="flex flex-wrap items-center gap-4 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9C968E]">
                        <span>{learningProgress?.roadmapCount ?? 0} Roadmaps</span>
                        <span>{inProgressTopicsCount} In Progress</span>
                        <span className="text-[#D95D24] font-bold">{completedTopicsCount}/{totalTopicsCount} Done</span>
                    </div>
                </div>

                {perRoadmap.length > 0 ? (
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                        {perRoadmap.map((rm) => {
                            const pct = Math.round(rm.percent ?? 0);
                            return (
                                <div key={rm.roadmapId} className="border border-[#F2EFE9]/10 bg-[#111111] p-4">
                                    <div className="flex items-center justify-between gap-3">
                                        <span className="truncate text-sm font-semibold text-[#F2EFE9]">
                                            {rm.roadmapName}
                                        </span>
                                        <span className="shrink-0 font-mono text-xs font-bold text-[#D95D24]">
                                            {pct}%
                                        </span>
                                    </div>
                                    <div className="mt-2.5 h-1.5 w-full bg-[#1C1C1C]">
                                        <div
                                            className="h-full bg-[#D95D24] transition-all duration-500"
                                            style={{ width: `${pct}%` }}
                                        />
                                    </div>
                                    <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9C968E]">
                                        {rm.completed} of {rm.total} topics completed
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    <p className="border-l border-[#D95D24] py-2 pl-4 font-mono text-xs text-[#9C968E]">
                        No learning roadmaps tracked yet. Add a roadmap in Learning to track mastery here.
                    </p>
                )}
            </section>

            {/* Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-4 gap-6">
                <div className="glass-card p-6 flex flex-col items-center justify-center text-center space-y-2 group hover:border-white/20 transition-colors">
                    <div className="p-3 bg-white/10 text-white rounded-full mb-2 group-hover:bg-white group-hover:text-black transition-colors">
                        <Trophy size={20} />
                    </div>
                    <h3 className="text-textMuted text-xs uppercase tracking-widest">Weekly Sync</h3>
                    <p className="text-2xl font-bold text-white font-mono">{getWeeklyCompletionRate()}%</p>
                </div>

                <div className="glass-card p-6 flex flex-col items-center justify-center text-center space-y-2 group hover:border-white/20 transition-colors">
                    <div className="p-3 bg-white/10 text-white rounded-full mb-2 group-hover:bg-white group-hover:text-black transition-colors">
                        <Flame size={20} />
                    </div>
                    <h3 className="text-textMuted text-xs uppercase tracking-widest">Max Streak</h3>
                    <p className="text-2xl font-bold text-white font-mono">{getLongestStreak()} days</p>
                </div>

                <div className="glass-card p-6 flex flex-col items-center justify-center text-center space-y-2 group hover:border-white/20 transition-colors">
                    <div className="p-3 bg-white/10 text-white rounded-full mb-2 group-hover:bg-white group-hover:text-black transition-colors">
                        <Calendar size={20} />
                    </div>
                    <h3 className="text-textMuted text-xs uppercase tracking-widest">Yearly Activity</h3>
                    <p className="text-2xl font-bold text-white font-mono">{yearlyTotal}</p>
                </div>

                <div className="glass-card p-6 flex flex-col items-center justify-center text-center space-y-2 group hover:border-white/20 transition-colors">
                    <div className="p-3 bg-white/10 text-white rounded-full mb-2 group-hover:bg-white group-hover:text-black transition-colors">
                        <BarChart3 size={20} />
                    </div>
                    <h3 className="text-textMuted text-xs uppercase tracking-widest">Habit you&apos;re strongest with</h3>
                    <p className="text-lg font-bold text-white truncate w-full px-2">{topHabit ? topHabit.name : 'N/A'}</p>
                </div>
            </div>

            {/* Yearly Heatmap */}
            <div className="glass-card">
                <div className="flex items-center justify-between mb-6">
                    <h3 className="text-xs font-bold uppercase tracking-widest px-2 text-textMuted flex items-center gap-2">
                        <Grid size={14} />
                        Yearly Overview
                    </h3>
                    <div className="flex items-center gap-3 text-xs text-textMuted font-mono">
                        <button type="button" aria-label="Previous year" onClick={() => setSelectedYear((year) => year - 1)} className="rounded-lg border border-white/10 p-2 text-textMuted hover:border-orange-400/30 hover:text-orange-300"><ChevronLeft size={14} /></button>
                        <span>{selectedYear}</span>
                        <button type="button" aria-label="Next year" onClick={() => setSelectedYear((year) => Math.min(new Date().getFullYear(), year + 1))} disabled={selectedYear >= new Date().getFullYear()} className="rounded-lg border border-white/10 p-2 text-textMuted hover:border-orange-400/30 hover:text-orange-300 disabled:opacity-30"><ChevronRight size={14} /></button>
                    </div>
                </div>
                <YearlyHeatmap dailyData={dailyCompletions} year={selectedYear} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Monthly Performance */}
                <div className="glass-card">
                    <h3 className="text-xs font-bold uppercase tracking-widest mb-2 px-2 text-textMuted">Monthly Volume</h3>
                    <MonthlyChart data={monthlyStats} />
                </div>

                {/* Weekday Performance */}
                <div className="glass-card">
                    <h3 className="text-xs font-bold uppercase tracking-widest mb-2 px-2 text-textMuted">Day Consistency</h3>
                    <WeekdayChart data={weekdayStats} />
                </div>
            </div>

            {/* Weekly Heatmap Table */}
            <div className="glass-card overflow-x-auto">
                <h3 className="text-xs font-bold uppercase tracking-widest mb-6 px-2 text-textMuted">Weekly Progression</h3>

                <table className="w-full min-w-[600px]">
                    <thead>
                        <tr>
                            <th className="text-left py-3 px-4 text-textMuted font-medium w-1/3 text-xs uppercase tracking-wider">Habit</th>
                            {last7Days.map(day => (
                                <th key={day.fullDate} className="text-center py-3 px-2 text-textMuted font-medium">
                                    <div className="flex flex-col items-center">
                                        <span className="text-[10px] uppercase tracking-wider">{day.label}</span>
                                        <span className={`text-xs mt-1 px-1.5 rounded font-mono ${day.fullDate === format(new Date(), 'yyyy-MM-dd') ? 'bg-white text-black' : ''
                                            }`}>
                                            {format(day.date, 'd')}
                                        </span>
                                    </div>
                                </th>
                            ))}
                            <th className="text-center py-3 px-4 text-textMuted font-medium text-xs uppercase tracking-wider">Streak</th>
                        </tr>
                    </thead>
                    <tbody>
                        {habits.map(habit => (
                            <tr key={habit.id} className="border-t border-white/5 hover:bg-white/5 transition-colors">
                                <td className="py-4 px-4 font-medium text-white">{habit.name}</td>

                                {last7Days.map(day => {
                                    const isCompleted = habit.completedDates?.includes(day.fullDate);
                                    return (
                                        <td key={day.fullDate} className="py-4 px-2 text-center">
                                            <div className="flex justify-center">
                                                <motion.div
                                                    initial={{ scale: 0.8, opacity: 0 }}
                                                    animate={{ scale: 1, opacity: 1 }}
                                                    className={`w-6 h-6 rounded flex items-center justify-center transition-all ${isCompleted
                                                        ? 'bg-white shadow-[0_0_10px_rgba(255,255,255,0.3)]'
                                                        : 'bg-white/5 border border-white/5'
                                                        }`}
                                                >
                                                    {isCompleted && <div className="w-2 h-2 bg-black rounded-full" />}
                                                </motion.div>
                                            </div>
                                        </td>
                                    );
                                })}
                                <td className="py-4 px-4 text-center">
                                    <span className="inline-flex items-center px-2 py-1 rounded bg-white/5 border border-white/5 text-xs text-white uppercase tracking-wider font-mono">
                                        <Flame size={10} className="text-white mr-1.5" />
                                        {habit.streak}
                                    </span>
                                </td>
                            </tr>
                        ))}
                        {habits.length === 0 && (
                            <tr>
                                <td colSpan={9} className="py-8 text-center text-textMuted text-sm italic">
                                    No habits initialized.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default Analytics;
