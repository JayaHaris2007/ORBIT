import {
    BarChart2,
    Bell,
    CheckSquare,
    GraduationCap,
    ListTodo,
    Settings as SettingsIcon,
} from 'lucide-react';

export const SECTION_META = {
    tasks: {
        id: 'tasks',
        code: '01',
        label: 'Tasks',
        subtitle: 'Active priorities & checklists',
        icon: ListTodo,
        askPrompt: 'Summarize my open tasks and suggest what to tackle first.',
    },
    habits: {
        id: 'habits',
        code: '02',
        label: 'Habits',
        subtitle: 'Daily discipline & streaks',
        icon: CheckSquare,
        askPrompt: 'Give me a quick check-in on my habits today.',
    },
    reminders: {
        id: 'reminders',
        code: '03',
        label: 'Reminders & Memory',
        subtitle: 'Scheduled nudges & long-term memory',
        icon: Bell,
        askPrompt: 'What upcoming reminders and key memories do you have for me?',
    },
    learning: {
        id: 'learning',
        code: '04',
        label: 'Learning',
        subtitle: 'Roadmaps, topics & practice sync',
        icon: GraduationCap,
        askPrompt: 'What should I study next based on my learning roadmaps?',
    },
    analytics: {
        id: 'analytics',
        code: '05',
        label: 'Analytics',
        subtitle: 'Momentum, streaks & completion telemetry',
        icon: BarChart2,
        askPrompt: 'Analyze my recent productivity momentum across habits, tasks, and learning.',
    },
    settings: {
        id: 'settings',
        code: '06',
        label: 'Settings',
        subtitle: 'Preferences, theme, API & runtime',
        icon: SettingsIcon,
        askPrompt: null,
    },
};

export const SECTION_ORDER = ['tasks', 'habits', 'reminders', 'learning', 'analytics', 'settings'];
