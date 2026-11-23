export default function SpeakToggle({ speakEnabled, engineReady, onToggle, disabled = false, error = null }) {
    const isUnavailable = !engineReady && Boolean(error);

    return (
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
            className={`px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors ${
                isUnavailable
                    ? 'cursor-not-allowed border border-[#F2EFE9]/10 text-[#5C564F] opacity-50'
                    : speakEnabled
                    ? 'border border-[#D95D24] bg-[#D95D24]/15 text-[#F2EFE9]'
                    : 'border border-[#F2EFE9]/14 bg-[#0B0A09] text-[#8E867D] hover:border-[#D95D24] hover:text-[#F2EFE9]'
            }`}
        >
            {isUnavailable ? '[tts:off]' : speakEnabled ? '[tts:on]' : '[tts:mute]'}
        </button>
    );
}
