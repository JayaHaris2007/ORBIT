import { Square } from 'lucide-react';

export default function StopButton({ state = 'idle', onStop }) {
    if (state === 'idle') return null;

    return (
        <button
            type="button"
            onClick={onStop}
            aria-label="Stop current voice turn"
            title="Stop voice turn (discard transient audio)"
            className="flex h-9 w-9 items-center justify-center border border-[#D95D24] bg-[#D95D24] text-[#111111] transition-colors hover:bg-[#C44E19]"
        >
            <Square size={13} className="fill-current" />
        </button>
    );
}
