import { memo } from 'react';
import { MessageSquare } from 'lucide-react';
import { SECTION_META, SECTION_ORDER } from './sectionMeta';
import MuteButton from '../voice/MuteButton';
import LiveButton from '../voice/LiveButton';

const SHORT_LABELS = {
    tasks: 'Tasks',
    habits: 'Habits',
    reminders: 'Reminders',
    learning: 'Learning',
    analytics: 'Analytics',
    settings: 'Settings',
};

const TopNavbar = memo(function TopNavbar({
    activeSection,
    liveOpen,
    voiceState,
    isMicMuted,
    onToggleMicMute,
    speakEnabled,
    engineReady,
    ttsError,
    onToggleSpeak,
    onOpenDrawer,
    onSelectSection,
    onToggleLive,
    chatId,
    loading,
    online,
}) {
    const isChatActive = !activeSection && !liveOpen;
    const isTtsUnavailable = !engineReady && Boolean(ttsError);

    return (
        <header className="relative z-40 flex h-12 w-full shrink-0 items-center justify-between gap-2 border-b border-[#F2EFE9]/12 bg-[#070606]/92 px-3 backdrop-blur-md sm:px-4">
            {/* LEFT: Chat Drawer Toggle + ORBIT Brand */}
            <div className="flex shrink-0 items-center gap-2.5">
                <button
                    type="button"
                    onClick={onOpenDrawer}
                    aria-label="Open chat history"
                    title="Chat History"
                    className="flex h-8 w-8 items-center justify-center border border-[#F2EFE9]/14 bg-[#0A0908] text-[#CFC9BF] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9]"
                >
                    <span className="flex flex-col gap-[3.5px]">
                        <span className="block h-[1.5px] w-3.5 bg-current" />
                        <span className="block h-[1.5px] w-3.5 bg-current" />
                        <span className="block h-[1.5px] w-2.5 bg-current" />
                    </span>
                </button>

                <button
                    type="button"
                    onClick={() => onSelectSection(null)}
                    title="Return to ORBIT Chat"
                    className="flex items-center gap-2 select-none transition-opacity hover:opacity-90"
                >
                    <img
                        src="/logo.png"
                        alt="ORBIT"
                        className="h-6 w-6 rounded-full object-cover"
                    />
                    <span className="hidden font-mono text-xs font-semibold tracking-[0.24em] text-[#F2EFE9] md:inline">
                        ORBIT
                    </span>
                </button>
            </div>

            {/* CENTER: Core Workspace Sections */}
            <nav
                aria-label="Workspace sections"
                className="flex min-w-0 flex-1 items-center justify-start gap-1 overflow-x-auto py-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden lg:justify-center"
            >
                <button
                    type="button"
                    onClick={() => onSelectSection(null)}
                    className={`flex h-8 shrink-0 items-center gap-1.5 border px-2.5 font-mono text-[11px] uppercase tracking-[0.1em] transition-colors ${
                        isChatActive
                            ? 'border-[#D95D24] bg-[#D95D24]/18 font-medium text-[#F2EFE9]'
                            : 'border-transparent text-[#8E867D] hover:border-[#F2EFE9]/14 hover:bg-[#0D0C0B] hover:text-[#F2EFE9]'
                    }`}
                >
                    <MessageSquare size={12} strokeWidth={1.9} className={isChatActive ? 'text-[#D95D24]' : ''} />
                    <span>Chat</span>
                </button>

                {SECTION_ORDER.map((secKey) => {
                    const meta = SECTION_META[secKey];
                    if (!meta) return null;
                    const Icon = meta.icon;
                    const active = activeSection === secKey;
                    return (
                        <button
                            key={secKey}
                            type="button"
                            onClick={() => onSelectSection(active ? null : secKey)}
                            className={`flex h-8 shrink-0 items-center gap-1.5 border px-2.5 font-mono text-[11px] uppercase tracking-[0.1em] transition-colors ${
                                active
                                    ? 'border-[#D95D24] bg-[#D95D24]/18 font-medium text-[#F2EFE9]'
                                    : 'border-transparent text-[#8E867D] hover:border-[#F2EFE9]/14 hover:bg-[#0D0C0B] hover:text-[#F2EFE9]'
                            }`}
                        >
                            <Icon size={12} strokeWidth={1.9} className={active ? 'text-[#D95D24]' : ''} />
                            <span>{SHORT_LABELS[secKey] || meta.label}</span>
                        </button>
                    );
                })}
            </nav>

            {/* RIGHT: Mute Controls + Live Voice Toggle + Status */}
            <div className="flex shrink-0 items-center gap-1.5">
                {liveOpen || voiceState !== 'idle' ? (
                    <MuteButton
                        mode="mic"
                        isMuted={isMicMuted}
                        onToggle={onToggleMicMute}
                        compact
                    />
                ) : null}

                <MuteButton
                    mode="audio"
                    isMuted={!speakEnabled}
                    onToggle={onToggleSpeak}
                    disabled={isTtsUnavailable}
                    compact
                />

                <LiveButton
                    active={liveOpen}
                    state={voiceState}
                    onClick={onToggleLive}
                    disabled={!chatId || loading}
                    compact
                />

                <span
                    title={online ? 'Backend online' : 'Backend offline'}
                    className={`ml-1 hidden h-2 w-2 shrink-0 rounded-full sm:inline-block ${
                        online ? 'bg-[#D95D24]' : 'bg-[#5C564F]'
                    }`}
                />
            </div>
        </header>
    );
});

export default TopNavbar;
