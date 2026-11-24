export default function LiveButton({
    active = false,
    state = 'idle',
    onClick,
    disabled = false,
    compact = false,
}) {
    const isBusy = state === 'connecting' || state === 'transcribing' || state === 'thinking';

    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            aria-pressed={active}
            aria-label={active ? 'End Live Mode (Ctrl+Space)' : 'Start Live Mode (Ctrl+Space)'}
            title={active ? 'End Live Mode (Ctrl+Space)' : 'Start Live Mode (Ctrl+Space)'}
            className={`relative flex shrink-0 items-center justify-center gap-1.5 border font-mono uppercase tracking-[0.1em] transition-colors ${
                compact ? 'h-8 px-2 text-[10px]' : 'h-9 px-2.5 text-[11px]'
            } ${
                active
                    ? 'border-[#D95D24] bg-[#D95D24] font-semibold text-[#060606] hover:bg-[#E86B30]'
                    : isBusy
                    ? 'border-[#D95D24]/60 bg-[#1B110B] text-[#E87D42]'
                    : 'border-[#F2EFE9]/15 bg-[#0A0908] text-[#A8A096] hover:border-[#D95D24] hover:text-[#F2EFE9]'
            } disabled:opacity-40`}
        >
            <span
                className={`h-1.5 w-1.5 rounded-full ${
                    active ? 'animate-pulse bg-[#060606]' : 'bg-[#D95D24]'
                }`}
            />
            <span>{active ? 'live' : 'live'}</span>
        </button>
    );
}
