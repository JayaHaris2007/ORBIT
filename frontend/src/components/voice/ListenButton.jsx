export default function ListenButton({
    state = 'idle',
    cloudStt = false,
    onClick,
    disabled = false,
}) {
    const isListening = state === 'listening';
    const isBusy = state === 'transcribing' || state === 'thinking';

    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled || isBusy}
            aria-label={
                isListening
                    ? 'Listening to speech...'
                    : isBusy
                    ? `${state}...`
                    : 'Start voice input (Listen)'
            }
            title={
                isListening
                    ? 'Listening (click to stop)'
                    : isBusy
                    ? `${state}...`
                    : cloudStt
                    ? 'Listen (Cloud STT)'
                    : 'Listen (Voice Input)'
            }
            className={`relative flex h-9 shrink-0 items-center justify-center border px-2.5 font-mono text-[11px] uppercase tracking-[0.1em] transition-colors ${
                isListening
                    ? 'border-[#D95D24] bg-[#D95D24] font-semibold text-[#060606]'
                    : isBusy
                    ? 'border-[#D95D24]/60 bg-[#1B110B] text-[#E87D42]'
                    : 'border-[#F2EFE9]/15 bg-[#0A0908] text-[#A8A096] hover:border-[#D95D24] hover:text-[#F2EFE9]'
            } disabled:opacity-40`}
        >
            {isListening ? '[rec]' : isBusy ? '[...]' : '[mic]'}
        </button>
    );
}
