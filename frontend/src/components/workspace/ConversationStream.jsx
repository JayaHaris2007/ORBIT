import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import { motion } from 'framer-motion';
import { cleanAssistantText } from '../../utils/textUtils';
import { SECTION_META } from './sectionMeta';

const QUICK_HINTS = [
    "What's pending today?",
    'Open my learning',
    'Check my habits',
    'Summarize my day',
];

const ConversationStream = memo(function ConversationStream({
    isHero,
    messages,
    loading,
    chatId,
    liveOpen,
    voiceState,
    voiceTranscript,
    voiceCaption,
    onSubmitPrompt,
    onOpenSection,
    conversationEndRef,
}) {
    if (isHero) {
        return (
            <div className="flex min-h-0 w-full flex-1 flex-col items-center justify-center px-6 pb-8">
                <div className="text-center">
                    <img
                        src="/logo.png"
                        alt="ORBIT"
                        className="mx-auto mb-3.5 h-12 w-12 rounded-full object-cover"
                    />
                    <h1 className="font-mono text-2xl font-medium tracking-[0.42em] text-[#F2EFE9] sm:text-3xl">
                        ORBIT
                    </h1>
                    <p
                        className={`mt-3 font-mono text-xs transition-colors ${
                            liveOpen || voiceState !== 'idle'
                                ? 'text-[#FF944D]'
                                : 'text-[#A8A096]'
                        }`}
                    >
                        {voiceTranscript && voiceState !== 'idle'
                            ? `“${voiceTranscript}”`
                            : voiceCaption}
                    </p>
                </div>

                <div className="mt-8 flex max-w-xl flex-wrap items-center justify-center gap-2.5">
                    {QUICK_HINTS.map((hint) => (
                        <button
                            key={hint}
                            type="button"
                            onClick={() => onSubmitPrompt(hint)}
                            disabled={loading || !chatId}
                            className="border border-[#F2EFE9]/14 bg-[#070606]/78 px-3.5 py-1.5 text-xs text-[#CFC9BF] backdrop-blur-[2px] transition-colors hover:border-[#D95D24] hover:bg-[#120B07]/90 hover:text-[#F2EFE9] disabled:opacity-35"
                        >
                            {hint}
                        </button>
                    ))}
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-0 w-full flex-1 overflow-y-auto px-5 pb-4 pt-6 sm:px-8">
            <div className="mx-auto max-w-2xl space-y-5">
                {messages.slice(-40).map((item, index) => {
                    const isUser = item.role === 'user';
                    return (
                        <motion.div
                            key={`${item.role}-${item.id || index}`}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.16 }}
                            className={isUser ? 'flex justify-end' : 'flex justify-start'}
                        >
                            <div className={`max-w-[88%] ${isUser ? 'text-right' : 'w-full'}`}>
                                {isUser ? (
                                    <div
                                        className={`inline-block border border-[#D95D24]/45 bg-[#120B07]/85 px-4 py-2.5 text-left text-[14px] leading-relaxed text-[#F2EFE9] backdrop-blur-[3px] ${
                                            item.pending ? 'opacity-65' : ''
                                        }`}
                                    >
                                        <span className="whitespace-pre-wrap">{item.content}</span>
                                        {item.failed && (
                                            <p className="mt-1 font-mono text-[10px] text-[#D95D24]">
                                                Could not send — try again
                                            </p>
                                        )}
                                    </div>
                                ) : (
                                    <div className="border-l-2 border-[#D95D24]/60 bg-[#070606]/78 px-4 py-3 backdrop-blur-[3px]">
                                        <div className="assistant-message text-[14.5px] leading-[1.7] text-[#F2EFE9]">
                                            <ReactMarkdown>{cleanAssistantText(item.content)}</ReactMarkdown>
                                            {item.streaming && <span className="ascii-cursor ml-1" />}
                                        </div>

                                        {Array.isArray(item.relatedSections) && item.relatedSections.length > 0 && (
                                            <div className="mt-3 flex flex-wrap gap-2">
                                                {item.relatedSections.map((secKey) => {
                                                    const secMeta = SECTION_META[secKey];
                                                    if (!secMeta) return null;
                                                    return (
                                                        <button
                                                            key={secKey}
                                                            type="button"
                                                            onClick={() => onOpenSection(secKey)}
                                                            className="border border-[#D95D24]/55 bg-[#120B07]/90 px-3 py-1 font-mono text-[11px] text-[#FF944D] transition-colors hover:bg-[#D95D24] hover:text-[#060606]"
                                                        >
                                                            Open {secMeta.label} →
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </motion.div>
                    );
                })}

                {loading && !messages.some((m) => m.streaming) && (
                    <div className="inline-block border-l-2 border-[#D95D24] bg-[#070606]/78 px-4 py-2 font-mono text-xs text-[#CFC9BF] backdrop-blur-[3px]">
                        Thinking<span className="ascii-cursor ml-1.5" />
                    </div>
                )}
                <div ref={conversationEndRef} />
            </div>
        </div>
    );
});

export default ConversationStream;
