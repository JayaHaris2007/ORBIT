import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useAppData } from '../context/AppDataContext';
import { habitService } from '../services/habitService';
import { taskService } from '../services/taskService';
import { learningService } from '../services/learningService';
import { format, subDays } from 'date-fns';
import YearlyHeatmap from '../components/analytics/YearlyHeatmap';
import MonthlyChart from '../components/analytics/MonthlyChart';
import WeekdayChart from '../components/analytics/WeekdayChart';
import { calculateDailyCompletions, calculateMonthlyStats, calculateWeekdayStats, calculateYearlyTotal } from '../utils/analyticsUtils';
import { buildAsciiBar } from '../utils/asciiUtils';

const Analytics = () => {
    const { currentUser } = useAuth();
    const { revision } = useAppData();
    const [habits, setHabits] = useState([]);
    const [tasks, setTasks] = useState([]);
    const [learningProgress, setLearningProgress] = useState(null);
    const [loading, setLoading] = useState(true);
    const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());

    const last7Days = Array.from({ length: 7 }, (_, i) => {
        const date = subDays(new Date(), 6 - i);
        return {
            date,
            label: format(date, 'EEE'),
            fullDate: format(date, 'yyyy-MM-dd'),
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

    const getWeeklyCompletionRate = () => {
        if (habits.length === 0) return 0;
        const totalOpportunities = habits.length * 7;
        let totalCompleted = 0;
        habits.forEach((habit) => {
            last7Days.forEach((day) => {
                if (habit.completedDates?.includes(day.fullDate)) totalCompleted++;
            });
        });
        return Math.round((totalCompleted / totalOpportunities) * 100);
    };

    const getLongestStreak = () => {
        if (habits.length === 0) return 0;
        return Math.max(...habits.map((h) => h.streak || 0));
    };

    const getTopHabit = () => {
        if (habits.length === 0) return null;
        return habits.reduce((prev, current) => (prev.streak > current.streak ? prev : current));
    };

    if (loading) {
        return (
            <div className="py-16 text-center font-mono text-xs uppercase tracking-[0.18em] text-[#8E867D]">
                // computing telemetry matrix...
            </div>
        );
    }

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
        <div className="mx-auto max-w-6xl space-y-6 pb-12">
            <header className="border-b border-[#F2EFE9]/14 pb-4">
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#D95D24]">
                    05 // telemetry_matrix
                </span>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[#F2EFE9]">Analytics</h1>
            </header>

            {/* Composite Score + 3 Pillars */}
            <section className="ascii-frame grid grid-cols-1 gap-5 bg-[#0A0908] p-5 lg:grid-cols-[290px_minmax(0,1fr)]">
                <div className="flex flex-col justify-between border-b border-[#F2EFE9]/12 pb-5 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-5">
                    <div>
                        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#D95D24]">
                            // composite_index
                        </span>
                        <div className="mt-3 flex items-baseline gap-2 font-mono">
                            <span className="text-5xl font-bold text-[#F2EFE9]">{totalProductivePercent}%</span>
                            <span className="text-[10px] uppercase tracking-[0.14em] text-[#8E867D]">score</span>
                        </div>
                    </div>
                    <div className="mt-4 font-mono">
                        <div className="text-xs tracking-tight text-[#D95D24]">
                            [{buildAsciiBar(totalProductivePercent, 18)}]
                        </div>
                        <p className="mt-2 text-[10px] leading-relaxed text-[#7D756C]">
                            Weighted across habit consistency, task execution, and learning mastery.
                        </p>
                    </div>
                </div>

                <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-3 font-mono">
                    <div className="flex flex-col justify-between border border-[#F2EFE9]/12 bg-[#060606] p-4">
                        <span className="text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">Habits (7d)</span>
                        <div className="my-3">
                            <div className="text-2xl font-bold text-[#F2EFE9]">{habitRegularityPercent}%</div>
                            <div className="mt-0.5 text-[10px] text-[#7D756C]">{habits.length} active</div>
                        </div>
                        <div className="text-[11px] text-[#D95D24]">[{buildAsciiBar(habitRegularityPercent, 12)}]</div>
                    </div>

                    <div className="flex flex-col justify-between border border-[#F2EFE9]/12 bg-[#060606] p-4">
                        <span className="text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">Tasks</span>
                        <div className="my-3">
                            <div className="text-2xl font-bold text-[#F2EFE9]">{taskCompletionPercent}%</div>
                            <div className="mt-0.5 text-[10px] text-[#7D756C]">
                                {completedTasksCount}/{totalTasksCount} done
                            </div>
                        </div>
                        <div className="text-[11px] text-[#F2EFE9]">[{buildAsciiBar(taskCompletionPercent, 12)}]</div>
                    </div>

                    <div className="flex flex-col justify-between border border-[#F2EFE9]/12 bg-[#060606] p-4">
                        <span className="text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">Learning</span>
                        <div className="my-3">
                            <div className="text-2xl font-bold text-[#F2EFE9]">{learningPercent}%</div>
                            <div className="mt-0.5 text-[10px] text-[#7D756C]">
                                {completedTopicsCount}/{totalTopicsCount} mastered
                            </div>
                        </div>
                        <div className="text-[11px] text-[#D95D24]">[{buildAsciiBar(learningPercent, 12)}]</div>
                    </div>
                </div>
            </section>

            {/* Quick KPI Strip */}
            <div className="grid grid-cols-2 gap-3.5 md:grid-cols-4 font-mono">
                <div className="border border-[#F2EFE9]/12 bg-[#0A0908] p-4">
                    <div className="text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">Weekly Sync</div>
                    <div className="mt-1.5 text-2xl font-bold text-[#F2EFE9]">{habitRegularityPercent}%</div>
                </div>
                <div className="border border-[#F2EFE9]/12 bg-[#0A0908] p-4">
                    <div className="text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">Max Streak</div>
                    <div className="mt-1.5 text-2xl font-bold text-[#D95D24]">{getLongestStreak()}d</div>
                </div>
                <div className="border border-[#F2EFE9]/12 bg-[#0A0908] p-4">
                    <div className="text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">Yearly Logs</div>
                    <div className="mt-1.5 text-2xl font-bold text-[#F2EFE9]">{yearlyTotal}</div>
                </div>
                <div className="border border-[#F2EFE9]/12 bg-[#0A0908] p-4">
                    <div className="text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">Top Habit</div>
                    <div className="mt-1.5 truncate text-base font-semibold text-[#F2EFE9]">
                        {topHabit ? topHabit.name : '—'}
                    </div>
                </div>
            </div>

            {/* Learning Breakdown */}
            <section data-spidey-section="learning" className="border border-[#F2EFE9]/12 bg-[#0A0908] p-5">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-[#F2EFE9]/10 pb-3 font-mono text-[10px] uppercase tracking-[0.16em]">
                    <span className="text-[#F2EFE9]">
                        <span className="text-[#D95D24]">//</span> Roadmap Mastery
                    </span>
                    <div className="flex items-center gap-3 text-[#8E867D]">
                        <span>{learningProgress?.roadmapCount ?? 0} tracks</span>
                        <span>{inProgressTopicsCount} active</span>
                        <span className="text-[#D95D24]">{completedTopicsCount}/{totalTopicsCount} done</span>
                    </div>
                </div>

                {perRoadmap.length > 0 ? (
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        {perRoadmap.map((rm) => {
                            const pct = Math.round(rm.percent ?? 0);
                            return (
                                <div key={rm.roadmapId} className="border border-[#F2EFE9]/10 bg-[#060606] p-3.5 font-mono">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="truncate font-sans text-sm font-medium text-[#F2EFE9]">
                                            {rm.roadmapName}
                                        </span>
                                        <span className="text-xs font-bold text-[#D95D24]">{pct}%</span>
                                    </div>
                                    <div className="mt-2 text-[11px] text-[#D95D24]">
                                        [{buildAsciiBar(pct, 16)}]
                                    </div>
                                    <div className="mt-1 text-[10px] text-[#7D756C]">
                                        {rm.completed}/{rm.total} topics
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    <p className="font-mono text-xs text-[#7D756C]">
                        // no roadmaps tracked yet
                    </p>
                )}
            </section>

            {/* Yearly Heatmap */}
            <div className="border border-[#F2EFE9]/12 bg-[#0A0908] p-5">
                <div className="mb-5 flex items-center justify-between font-mono text-xs">
                    <span className="uppercase tracking-[0.16em] text-[#8E867D]">
                        <span className="text-[#D95D24]">//</span> Yearly Activity Matrix
                    </span>
                    <div className="flex items-center gap-2 text-[11px]">
                        <button
                            type="button"
                            onClick={() => setSelectedYear((y) => y - 1)}
                            className="border border-[#F2EFE9]/14 px-2 py-0.5 text-[#8E867D] hover:border-[#D95D24] hover:text-[#F2EFE9]"
                        >
                            [&lt;]
                        </button>
                        <span className="px-1 text-[#F2EFE9]">{selectedYear}</span>
                        <button
                            type="button"
                            onClick={() => setSelectedYear((y) => Math.min(new Date().getFullYear(), y + 1))}
                            disabled={selectedYear >= new Date().getFullYear()}
                            className="border border-[#F2EFE9]/14 px-2 py-0.5 text-[#8E867D] hover:border-[#D95D24] hover:text-[#F2EFE9] disabled:opacity-30"
                        >
                            [&gt;]
                        </button>
                    </div>
                </div>
                <YearlyHeatmap dailyData={dailyCompletions} year={selectedYear} />
            </div>

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
                <div className="border border-[#F2EFE9]/12 bg-[#0A0908] p-5">
                    <h3 className="mb-3 font-mono text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">
                        <span className="text-[#D95D24]">//</span> Monthly Volume
                    </h3>
                    <MonthlyChart data={monthlyStats} />
                </div>
                <div className="border border-[#F2EFE9]/12 bg-[#0A0908] p-5">
                    <h3 className="mb-3 font-mono text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">
                        <span className="text-[#D95D24]">//</span> Day Consistency
                    </h3>
                    <WeekdayChart data={weekdayStats} />
                </div>
            </div>

            {/* Weekly ASCII Progression Grid */}
            <div className="overflow-x-auto border border-[#F2EFE9]/12 bg-[#0A0908] p-5">
                <h3 className="mb-4 font-mono text-[10px] uppercase tracking-[0.16em] text-[#8E867D]">
                    <span className="text-[#D95D24]">//</span> 7-Day Discipline Grid
                </h3>

                <table className="w-full min-w-[580px] font-mono text-xs">
                    <thead>
                        <tr className="border-b border-[#F2EFE9]/12 text-[#8E867D]">
                            <th className="w-1/3 py-2.5 text-left text-[10px] uppercase tracking-[0.14em]">Habit</th>
                            {last7Days.map((day) => {
                                const isToday = day.fullDate === format(new Date(), 'yyyy-MM-dd');
                                return (
                                    <th key={day.fullDate} className="px-2 py-2.5 text-center">
                                        <div className="text-[9px] uppercase">{day.label}</div>
                                        <div className={`mt-0.5 inline-block px-1.5 text-[10px] ${isToday ? 'bg-[#D95D24] font-bold text-[#060606]' : 'text-[#8E867D]'}`}>
                                            {format(day.date, 'd')}
                                        </div>
                                    </th>
                                );
                            })}
                            <th className="py-2.5 text-right text-[10px] uppercase tracking-[0.14em]">Streak</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-[#F2EFE9]/8">
                        {habits.map((habit) => (
                            <tr key={habit.id} className="hover:bg-[#110F0D]">
                                <td className="py-3 pr-3 font-sans text-sm text-[#F2EFE9]">{habit.name}</td>
                                {last7Days.map((day) => {
                                    const isCompleted = habit.completedDates?.includes(day.fullDate);
                                    return (
                                        <td key={day.fullDate} className="px-2 py-3 text-center">
                                            <span className={isCompleted ? 'text-[#D95D24] font-bold' : 'text-[#3B3631]'}>
                                                {isCompleted ? '[█]' : '[·]'}
                                            </span>
                                        </td>
                                    );
                                })}
                                <td className="py-3 text-right text-[#E87D42]">
                                    {habit.streak || 0}d
                                </td>
                            </tr>
                        ))}
                        {habits.length === 0 && (
                            <tr>
                                <td colSpan={9} className="py-8 text-center text-[#6E675F]">
                                    // no habits initialized
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
