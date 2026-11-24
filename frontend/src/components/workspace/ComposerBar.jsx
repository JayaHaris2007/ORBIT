import { memo, useMemo, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import MuteButton from '../voice/MuteButton';
import StopButton from '../voice/StopButton';
import LiveButton from '../voice/LiveButton';

const ComposerBar = memo(function ComposerBar({
    prompt,
    onPromptChange,
    onSubmitPrompt,
    slashCommands,
    onExecuteSlashCommand,
    chatId,
    loading,
    error,
    voiceError,
    speakEnabled,
    engineReady,
    onToggleSpeak,
    ttsError,
    isMicMuted = false,
    onToggleMicMute,
    isVoiceActive,
    onVoiceStop,
    liveActive,
    voiceState,
    onToggleLive,
}) {
    const textareaRef = useRef(null);

    const slashSuggestions = useMemo(() => {
        const trimmed = prompt.trim().toLowerCase();
        if (!trimmed.startsWith('/')) return [];
        return slashCommands.filter(
            (item) => item.cmd.startsWith(trimmed) || item.desc.toLowerCase().includes(trimmed.slice(1))
        );
    }, [prompt, slashCommands]);

    const handleSendSubmit = (e) => {
        e.preventDefault();
        onSubmitPrompt(prompt);
    };

    const handleComposerKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (slashSuggestions.length === 1 && prompt.trim().startsWith('/')) {
                onExecuteSlashCommand(slashSuggestions[0]);
                return;
            }
            onSubmitPrompt(prompt);
            return;
        }
        if (!e.ctrlKey && !e.metaKey && !e.altKey) {
            if (e.key.length === 1 || e.key === 'Backspace') {
                window.dispatchEvent(
                    new CustomEvent('spidey:keystroke', {
                        detail: { key: e.key, isDelete: e.key === 'Backspace' },
                    })
                );
            }
        }
    };

    return (
        <div className="relative z-20 w-full shrink-0 px-4 pb-5 pt-2 sm:px-6 sm:pb-7">
            <div className="relative mx-auto w-full max-w-2xl">
                <AnimatePresence>
                    {slashSuggestions.length > 0 && (
                        <motion.div
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 4 }}
                            className="ascii-frame absolute bottom-full left-0 right-0 z-30 mb-2 bg-[#090807]/95 p-1.5 shadow-2xl backdrop-blur-md"
                        >
                            {slashSuggestions.map((item) => (
                                <button
                                    key={item.cmd}
                                    type="button"
                                    onClick={() => {
                                        onExecuteSlashCommand(item);
                                        textareaRef.current?.focus();
                                    }}
                                    className="flex w-full items-center justify-between px-3 py-2 text-left text-xs transition-colors hover:bg-[#D95D24]/16"
                                >
                                    <span className="font-mono font-medium text-[#D95D24]">{item.cmd}</span>
                                    <span className="text-[#8E867D]">{item.desc}</span>
                                </button>
                            ))}
                        </motion.div>
                    )}
                </AnimatePresence>

                <form
                    onSubmit={handleSendSubmit}
                    className="flex items-center gap-2 border border-[#F2EFE9]/16 bg-[#090807]/85 px-3.5 py-2 backdrop-blur-md transition-colors focus-within:border-[#D95D24]"
                >
                    <textarea
                        ref={textareaRef}
                        value={prompt}
                        onChange={(e) => onPromptChange(e.target.value)}
                        onKeyDown={handleComposerKeyDown}
                        rows={1}
                        maxLength={2000}
                        placeholder="Ask ORBIT anything… or type /"
                        className="max-h-28 min-h-[34px] flex-1 resize-none bg-transparent py-1.5 text-[14px] leading-relaxed text-[#F2EFE9] outline-none placeholder:text-[#7D756C]"
                        disabled={!chatId}
                    />

                    <MuteButton
                        mode="audio"
                        isMuted={!speakEnabled}
                        onToggle={onToggleSpeak}
                        disabled={!engineReady && Boolean(ttsError)}
                    />

                    {(liveActive || voiceState !== 'idle') && onToggleMicMute && (
                        <MuteButton
                            mode="mic"
                            isMuted={isMicMuted}
                            onToggle={onToggleMicMute}
                        />
                    )}

                    <StopButton
                        state={isVoiceActive ? 'speaking' : 'idle'}
                        onStop={onVoiceStop}
                    />

                    <LiveButton
                        active={liveActive}
                        state={voiceState}
                        onClick={onToggleLive}
                        disabled={!chatId || loading}
                    />

                    <button
                        type="submit"
                        disabled={loading || !prompt.trim() || !chatId}
                        className="h-9 shrink-0 border border-[#D95D24] bg-[#D95D24] px-4 font-mono text-xs font-semibold text-[#060606] transition-colors hover:bg-[#E86B30] disabled:opacity-30"
                        aria-label="Send message"
                    >
                        Send
                    </button>
                </form>

                {(error || voiceError) && (
                    <p className="mt-2 text-center font-mono text-[11px] text-[#D95D24]">
                        {error || voiceError}
                    </p>
                )}
            </div>
        </div>
    );
});

export default ComposerBar;
