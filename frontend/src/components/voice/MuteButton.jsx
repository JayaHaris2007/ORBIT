import { Mic, MicOff, Volume2, VolumeX } from 'lucide-react';

export default function MuteButton({
    isMuted = false,
    onToggle,
    mode = 'audio', // 'audio' (TTS speaker mute) | 'mic' (Live mic mute)
    disabled = false,
    compact = false,
}) {
    const isMic = mode === 'mic';
    const Icon = isMic ? (isMuted ? MicOff : Mic) : (isMuted ? VolumeX : Volume2);
    const label = isMic
        ? (isMuted ? 'Unmute Mic' : 'Mute Mic')
        : (isMuted ? 'Muted' : 'Sound On');
    const shortLabel = isMic
        ? (isMuted ? 'mic:off' : 'mic:on')
        : (isMuted ? 'muted' : 'mute');

    return (
        <button
            type="button"
            onClick={onToggle}
            disabled={disabled}
            aria-pressed={isMuted}
            aria-label={label}
            title={
                isMic
                    ? (isMuted ? 'Microphone muted — click to unmute (M)' : 'Microphone active — click to mute (M)')
                    : (isMuted ? 'Voice output muted — click to unmute' : 'Voice output enabled — click to mute')
            }
            className={`flex h-9 shrink-0 items-center justify-center gap-1.5 border px-2.5 font-mono text-[11px] uppercase tracking-[0.1em] transition-colors ${
                isMuted
                    ? 'border-[#D95D24]/70 bg-[#180E09] text-[#FF944D] hover:border-[#D95D24] hover:bg-[#D95D24]/20'
                    : 'border-[#F2EFE9]/15 bg-[#0A0908] text-[#CFC9BF] hover:border-[#D95D24] hover:text-[#F2EFE9]'
            } ${compact ? 'h-8 px-2 text-[10px]' : ''} disabled:cursor-not-allowed disabled:opacity-40`}
        >
            <Icon size={13} strokeWidth={1.9} className={isMuted ? 'text-[#D95D24]' : 'text-[#A8A096]'} />
            <span className="hidden sm:inline">{shortLabel}</span>
        </button>
    );
}
