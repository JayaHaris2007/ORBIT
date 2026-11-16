import { Volume2, VolumeX } from 'lucide-react';

export default function SpeakToggle({ speakEnabled, engineReady, onToggle, disabled = false, error = null }) {
    const isUnavailable = !engineReady && Boolean(error);

    return (
        <div className="relative inline-flex items-center">
            <button
                type="button"
                onClick={onToggle}
                disabled={disabled || isUnavailable}
                aria-pressed={speakEnabled}
                aria-label={
                    isUnavailable
                        ? 'Voice unavailable (TTS engine offline)'
                        : speakEnabled
                        ? 'Mute speech replies'
                        : 'Enable speech replies'
                }
                title={
                    isUnavailable
                        ? 'Voice unavailable'
                        : speakEnabled
                        ? 'Speak replies: ON'
                        : 'Speak replies: OFF'
                }
                className={`group relative flex h-7 items-center gap-1.5 border px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.1em] transition-colors ${
                    isUnavailable
                        ? 'cursor-not-allowed border-[#F2EFE9]/10 bg-[#111111] text-[#9C968E] opacity-50'
                        : speakEnabled
                        ? 'border-[#D95D24] bg-[#D95D24] text-[#111111] hover:bg-[#C44E19]'
                        : 'border-[#F2EFE9]/15 bg-[#151515] text-[#9C968E] hover:border-[#D95D24] hover:text-[#F2EFE9]'
                }`}
            >
                {isUnavailable ? (
                    <>
                        <VolumeX size={12} />
                        <span className="hidden sm:inline">Muted</span>
                    </>
                ) : speakEnabled ? (
                    <>
                        <Volume2 size={12} />
                        <span className="hidden sm:inline">Speak ON</span>
                    </>
                ) : (
                    <>
                        <VolumeX size={12} />
                        <span className="hidden sm:inline">Speak OFF</span>
                    </>
                )}
            </button>
        </div>
    );
}
