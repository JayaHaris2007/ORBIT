import { Mic, Loader2 } from 'lucide-react';

export default function ListenButton({
    state = 'idle',
    cloudStt = false,
    onClick,
    disabled = false,
}) {
    const isListening = state === 'listening';
    const isBusy = state === 'transcribing' || state === 'thinking';

    return (
        <div className="relative inline-flex items-center">
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
                        ? `${state.charAt(0).toUpperCase() + state.slice(1)}...`
                        : 'Listen (Voice Input)'
                }
                className={`relative flex h-9 w-9 items-center justify-center border transition-colors ${
                    isListening
                        ? 'border-[#D95D24] bg-[#D95D24] text-[#111111]'
                        : isBusy
                        ? 'border-[#D95D24]/60 bg-[#1B1511] text-[#D95D24]'
                        : 'border-[#F2EFE9]/15 bg-[#151515] text-[#9C968E] hover:border-[#D95D24] hover:text-[#F2EFE9]'
                } disabled:opacity-40`}
            >
                {isBusy ? (
                    <Loader2 size={15} className="animate-spin text-[#D95D24]" />
                ) : (
                    <Mic size={15} />
                )}

                {cloudStt && (
                    <span
                        className="absolute -top-1 -right-1 flex h-3.5 items-center bg-[#D95D24] px-1 font-mono text-[8px] font-bold uppercase tracking-tighter text-[#111111]"
                        title="Cloud STT active"
                    >
                        cloud
                    </span>
                )}
            </button>
        </div>
    );
}
