import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowUpRight, Check, Mic, Play, Sparkles } from 'lucide-react';
import NeuralBrainCanvas from './NeuralBrainCanvas';
import SpiderMark from '../brand/SpiderMark';
import { useSpideyBrain } from '../../context/SpideyBrainContext';
import { triggerAssistantPrompt } from '../AssistantEntryBriefing';

const EASE_MECH = [0.22, 1, 0.36, 1];

const STATE_META = {
    idle: {
        label: 'Standby',
        badgeClass: 'border-[#F2EFE9]/20 bg-[#181715] text-[#F2EFE9]',
        dotClass: 'bg-[#D95D24]',
        caption: 'Core synchronized. Ready for voice or text commands.',
    },
    listening: {
        label: 'Listening',
        badgeClass: 'border-[#D95D24] bg-[#D95D24] text-[#111111]',
        dotClass: 'bg-[#111111]',
        caption: 'Capturing microphone audio waveform.',
    },
    transcribing: {
        label: 'Transcribing',
        badgeClass: 'border-[#D95D24]/70 bg-[#1B1612] text-[#F2EFE9]',
        dotClass: 'bg-[#D95D24]',
        caption: 'Decoding speech into intent.',
    },
    thinking: {
        label: 'Processing',
        badgeClass: 'border-[#F2EFE9] bg-[#F2EFE9] text-[#111111]',
        dotClass: 'bg-[#D95D24]',
        caption: 'Running tools, memory recall & reasoning.',
    },
    streaming: {
        label: 'Streaming',
        badgeClass: 'border-[#D95D24] bg-[#D95D24] text-[#111111]',
        dotClass: 'bg-[#F2EFE9]',
        caption: 'Streaming response tokens in real time.',
    },
    speaking: {
        label: 'Speaking',
        badgeClass: 'border-[#F2EFE9]/60 bg-[#1C1B19] text-[#F2EFE9]',
        dotClass: 'bg-[#D95D24]',
        caption: 'Synthesizing voice output.',
    },
};

const QUICK_PROMPTS = [
    { label: 'Summarize my day', prompt: "What's pending today?" },
    { label: 'Habit check-in', prompt: 'Check my habits' },
    { label: 'Next to learn', prompt: 'What should I study next?' },
];

function getEditorialGreeting() {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
}

export default function NeuralCoreDeck({
    userName = 'Shadow Hunter',
    pendingTasksCount = 0,
    completedTasksCount = 0,
    completedHabitsCount = 0,
    totalHabitsCount = 0,
    xp = 0,
    streak = 0,
    topTask = null,
    nextTopic = null,
    learningProgress = null,
    onQuickCompleteTask,
    onQuickStartTopic,
}) {
    const brain = useSpideyBrain();
    const activeState = brain?.brainState || 'idle';
    const meta = useMemo(() => STATE_META[activeState] || STATE_META.idle, [activeState]);

    const level = Math.floor(xp / 100) + 1;
    const habitPct = totalHabitsCount > 0 ? Math.round((completedHabitsCount / totalHabitsCount) * 100) : 0;
    const learnPct = Math.round(learningProgress?.percentage ?? learningProgress?.overall_percentage ?? 0);
    const learnCompleted = learningProgress?.completed_topics ?? learningProgress?.completed ?? 0;
    const learnTotal = learningProgress?.total_topics ?? learningProgress?.total ?? 0;

    const toggleVoiceInChat = () => window.dispatchEvent(new CustomEvent('spidey:open_listen'));
    const isVoiceRunning = activeState === 'listening' || activeState === 'transcribing' || activeState === 'speaking';

    return (
        <motion.section
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.36, ease: EASE_MECH }}
            className="border border-[#F2EFE9]/15 bg-[#141414]"
        >
            {/* Top Editorial Strip */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#F2EFE9]/15 px-5 py-3">
                <div className="flex items-center gap-3">
                    <span className="bg-[#D95D24] px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#111111]">
                        00 · CORE
                    </span>
                    <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#F2EFE9]">
                        S.P.I.D.E.Y. Neural Matrix &amp; Personal Telemetry
                    </span>
                </div>
                <div className={`inline-flex items-center gap-2 border px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em] ${meta.badgeClass}`}>
                    <span className={`h-1.5 w-1.5 ${meta.dotClass}`} />
                    <span>{meta.label}</span>
                </div>
            </div>

            {/* Merged Split Grid: Left 3D Sphere / Right Personal Status & Controls */}
            <div className="grid grid-cols-1 lg:grid-cols-[340px_minmax(0,1fr)] lg:divide-x lg:divide-[#F2EFE9]/15">
                {/* Left: Interactive 3D Neural Core */}
                <div className="relative flex flex-col justify-between border-b border-[#F2EFE9]/15 bg-[#111111] p-4 lg:border-b-0">
                    <div className="flex items-center justify-between">
                        <SpiderMark size={26} state={activeState} />
                        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
                            Three.js Cortex
                        </span>
                    </div>

                    <div className="relative mx-auto my-2 flex h-[230px] w-full max-w-[290px] items-center justify-center">
                        <div className="pointer-events-none absolute inset-4 rounded-full border border-[#F2EFE9]/10" />
                        <div className="pointer-events-none absolute inset-10 rounded-full border border-[#D95D24]/20" />
                        <NeuralBrainCanvas
                            size="hero"
                            className="h-full w-full"
                            onClick={() => brain?.triggerPulse?.(1.3)}
                        />
                    </div>

                    <div className="flex items-center justify-between border-t border-[#F2EFE9]/10 pt-3 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9C968E]">
                        <span>Hover to tilt</span>
                        <span>Click core to pulse</span>
                    </div>
                </div>

                {/* Right: Unified "About My Thing" + AI Controls */}
                <div className="flex flex-col justify-between divide-y divide-[#F2EFE9]/15">
                    {/* Row 1: Greeting + Voice Action Bar */}
                    <div className="flex flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center">
                        <div>
                            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#D95D24]">
                                {getEditorialGreeting()}, {userName}
                            </p>
                            <h2 className="mt-1 text-xl font-bold tracking-tight text-[#F2EFE9] md:text-2xl">
                                {pendingTasksCount > 0
                                    ? `${pendingTasksCount} ${pendingTasksCount === 1 ? 'task' : 'tasks'} open · ${completedHabitsCount}/${totalHabitsCount} habits logged`
                                    : 'All clear for today'}
                            </h2>
                            <p className="mt-1 text-xs text-[#9C968E]">{meta.caption}</p>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                            <button
                                type="button"
                                onClick={toggleVoiceInChat}
                                className={`inline-flex items-center gap-2 border px-3.5 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.14em] transition-colors ${
                                    isVoiceRunning
                                        ? 'border-[#F2EFE9] bg-[#F2EFE9] text-[#111111]'
                                        : 'border-[#D95D24] bg-[#D95D24] text-[#111111] hover:bg-[#C44E19]'
                                }`}
                            >
                                <Mic size={13} />
                                <span>{isVoiceRunning ? 'Stop Voice' : 'Voice Discussion'}</span>
                            </button>
                        </div>
                    </div>

                    {/* Row 2: 4-Cell Personal Telemetry Matrix */}
                    <div className="grid grid-cols-2 divide-y divide-[#F2EFE9]/15 sm:grid-cols-4 sm:divide-x sm:divide-y-0">
                        <Link to="/habits" className="group block p-4 transition-colors hover:bg-[#191816]">
                            <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
                                <span>Habits</span>
                                <ArrowUpRight size={12} className="opacity-0 transition-opacity group-hover:opacity-100" />
                            </div>
                            <p className="mt-2 font-mono text-2xl font-bold text-[#F2EFE9]">
                                {completedHabitsCount}
                                <span className="text-sm text-[#9C968E]">/{totalHabitsCount}</span>
                            </p>
                            <div className="mt-2 h-[2px] w-full bg-[#F2EFE9]/10">
                                <div
                                    className="h-full bg-[#D95D24] transition-all duration-300"
                                    style={{ width: `${habitPct}%` }}
                                />
                            </div>
                        </Link>

                        <Link to="/todos" className="group block border-l border-[#F2EFE9]/15 p-4 transition-colors hover:bg-[#191816] sm:border-l-0">
                            <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
                                <span>Tasks</span>
                                <ArrowUpRight size={12} className="opacity-0 transition-opacity group-hover:opacity-100" />
                            </div>
                            <p className="mt-2 font-mono text-2xl font-bold text-[#F2EFE9]">
                                {pendingTasksCount}
                                <span className="ml-1.5 text-[11px] font-normal text-[#9C968E]">open</span>
                            </p>
                            <p className="mt-1.5 font-mono text-[10px] text-[#9C968E]">
                                {completedTasksCount} completed
                            </p>
                        </Link>

                        <Link to="/analytics" className="group block p-4 transition-colors hover:bg-[#191816]">
                            <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
                                <span>Momentum</span>
                                <ArrowUpRight size={12} className="opacity-0 transition-opacity group-hover:opacity-100" />
                            </div>
                            <p className="mt-2 font-mono text-2xl font-bold text-[#D95D24]">
                                {streak}
                                <span className="ml-1 text-xs font-normal text-[#F2EFE9]">d</span>
                            </p>
                            <p className="mt-1.5 font-mono text-[10px] text-[#9C968E]">
                                LVL {level} · {xp} XP
                            </p>
                        </Link>

                        <Link to="/learning" className="group block border-l border-[#F2EFE9]/15 p-4 transition-colors hover:bg-[#191816] sm:border-l-0">
                            <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
                                <span>Learning</span>
                                <ArrowUpRight size={12} className="opacity-0 transition-opacity group-hover:opacity-100" />
                            </div>
                            <p className="mt-2 font-mono text-2xl font-bold text-[#F2EFE9]">
                                {learnPct}
                                <span className="text-sm text-[#9C968E]">%</span>
                            </p>
                            <p className="mt-1.5 font-mono text-[10px] text-[#9C968E]">
                                {learnCompleted}/{learnTotal} topics
                            </p>
                        </Link>
                    </div>

                    {/* Row 3: Next Actionable Priority + Next Study Topic */}
                    <div className="grid grid-cols-1 divide-y divide-[#F2EFE9]/15 sm:grid-cols-2 sm:divide-x sm:divide-y-0">
                        <div className="flex items-center justify-between gap-3 p-4">
                            <div className="min-w-0">
                                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
                                    Top Priority Task
                                </span>
                                {topTask ? (
                                    <div className="mt-1 flex items-center gap-2">
                                        <span className="truncate text-sm font-semibold text-[#F2EFE9]">
                                            {topTask.title}
                                        </span>
                                        <span className={`shrink-0 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase ${
                                            topTask.priority === 'high'
                                                ? 'bg-[#D95D24] text-[#111111]'
                                                : 'border border-[#F2EFE9]/20 text-[#9C968E]'
                                        }`}>
                                            {topTask.priority}
                                        </span>
                                    </div>
                                ) : (
                                    <p className="mt-1 font-mono text-xs text-[#9C968E]">No pending tasks</p>
                                )}
                            </div>
                            {topTask && onQuickCompleteTask && (
                                <button
                                    type="button"
                                    onClick={() => onQuickCompleteTask(topTask.id)}
                                    title="Mark task complete"
                                    className="grid h-8 w-8 shrink-0 place-items-center border border-[#F2EFE9]/25 bg-transparent text-[#F2EFE9] transition-colors hover:border-[#D95D24] hover:bg-[#D95D24] hover:text-[#111111]"
                                >
                                    <Check size={14} strokeWidth={2.5} />
                                </button>
                            )}
                        </div>

                        <div className="flex items-center justify-between gap-3 p-4">
                            <div className="min-w-0">
                                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
                                    Up Next in Learning
                                </span>
                                {nextTopic ? (
                                    <p className="mt-1 truncate text-sm font-semibold text-[#F2EFE9]">
                                        {nextTopic.name || nextTopic.title}
                                    </p>
                                ) : (
                                    <p className="mt-1 font-mono text-xs text-[#9C968E]">
                                        No queued study topic
                                    </p>
                                )}
                            </div>
                            {nextTopic && onQuickStartTopic && (
                                <button
                                    type="button"
                                    onClick={() => onQuickStartTopic(nextTopic)}
                                    title="Start learning topic"
                                    className="inline-flex shrink-0 items-center gap-1 border border-[#F2EFE9]/25 px-2.5 py-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#F2EFE9] transition-colors hover:border-[#D95D24] hover:text-[#D95D24]"
                                >
                                    <Play size={11} />
                                    <span>Start</span>
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Row 4: Quick Prompts */}
                    <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-3">
                        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#9C968E]">
                            Quick Commands
                        </span>
                        <div className="flex flex-wrap items-center gap-2">
                            {QUICK_PROMPTS.map((item) => (
                                <button
                                    key={item.label}
                                    type="button"
                                    onClick={() => triggerAssistantPrompt(item.prompt)}
                                    className="inline-flex items-center gap-1.5 border border-[#F2EFE9]/15 bg-[#181715] px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-[#F2EFE9] transition-colors hover:border-[#D95D24] hover:text-[#D95D24]"
                                >
                                    <Sparkles size={10} className="text-[#D95D24]" />
                                    <span>{item.label}</span>
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </motion.section>
    );
}
