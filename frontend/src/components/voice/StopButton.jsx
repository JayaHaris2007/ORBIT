export default function StopButton({ state = 'idle', onStop }) {
    if (state === 'idle') return null;

    return (
        <button
            type="button"
            onClick={onStop}
            aria-label="Stop current voice turn"
            title="Stop voice turn"
            className="flex h-9 shrink-0 items-center justify-center border border-[#D95D24] bg-[#D95D24] px-2.5 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-[#060606] transition-colors hover:bg-[#E86B30]"
        >
            [stop]
        </button>
    );
}
