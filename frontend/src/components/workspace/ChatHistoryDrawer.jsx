import { memo, useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { format } from 'date-fns';

const formatWhen = (value) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : format(date, 'MMM d');
};

const ChatHistoryDrawer = memo(function ChatHistoryDrawer({
    open,
    onClose,
    chats,
    chatId,
    chatSearch,
    onSearchChange,
    confirmingId,
    onConfirmingChange,
    onStartChat,
    onSelectChat,
    onDeleteChat,
    displayName,
    online,
}) {
    const filteredChats = useMemo(() => {
        const q = chatSearch.trim().toLowerCase();
        if (!q) return chats;
        return chats.filter((c) => (c.title || 'New session').toLowerCase().includes(q));
    }, [chats, chatSearch]);

    return (
        <AnimatePresence>
            {open && (
                <>
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                        className="fixed inset-0 z-40 bg-black/70 backdrop-blur-[2px]"
                    />
                    <motion.aside
                        initial={{ x: '-100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '-100%' }}
                        transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                        className="fixed inset-y-0 left-0 z-50 flex w-[272px] flex-col border-r border-[#F2EFE9]/12 bg-[#080807]"
                    >
                        <div className="flex items-center justify-between px-5 py-4">
                            <div className="flex items-center gap-2.5">
                                <img
                                    src="/logo.png"
                                    alt="ORBIT"
                                    className="h-5 w-5 rounded-full object-cover"
                                />
                                <span className="font-mono text-xs font-semibold tracking-[0.22em] text-[#F2EFE9]">
                                    ORBIT
                                </span>
                            </div>
                            <button
                                type="button"
                                onClick={onClose}
                                className="font-mono text-xs text-[#7D756C] hover:text-[#F2EFE9]"
                            >
                                [×]
                            </button>
                        </div>

                        <div className="space-y-2.5 px-4 pb-3">
                            <button
                                type="button"
                                onClick={onStartChat}
                                className="w-full border border-[#D95D24]/70 bg-[#D95D24]/12 py-2 font-mono text-xs text-[#F2EFE9] transition-colors hover:bg-[#D95D24] hover:text-[#060606]"
                            >
                                + New chat
                            </button>
                            <input
                                type="text"
                                value={chatSearch}
                                onChange={(e) => onSearchChange(e.target.value)}
                                placeholder="Search chats…"
                                className="w-full border border-[#F2EFE9]/12 bg-[#060606] px-3 py-1.5 font-mono text-xs text-[#F2EFE9] outline-none placeholder:text-[#5C564F] focus:border-[#D95D24]"
                            />
                        </div>

                        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
                            <div className="space-y-0.5">
                                {filteredChats.map((chat) => {
                                    const isActive = chat.id === chatId;
                                    const confirming = confirmingId === chat.id;
                                    return (
                                        <div
                                            key={chat.id}
                                            className={`group flex items-center gap-1 px-2.5 py-2 transition-colors ${
                                                isActive
                                                    ? 'border-l-2 border-[#D95D24] bg-[#140E0A] text-[#F2EFE9]'
                                                    : 'text-[#8E867D] hover:bg-[#0F0E0D] hover:text-[#F2EFE9]'
                                            }`}
                                        >
                                            <button
                                                type="button"
                                                onClick={() => onSelectChat(chat.id)}
                                                className="min-w-0 flex-1 text-left"
                                            >
                                                <div className="truncate text-xs">{chat.title || 'New chat'}</div>
                                                <div className="mt-0.5 font-mono text-[10px] text-[#5C564F]">
                                                    {formatWhen(chat.updated_at)}
                                                </div>
                                            </button>
                                            {confirming ? (
                                                <div className="flex shrink-0 items-center gap-1 font-mono text-[10px]">
                                                    <button
                                                        type="button"
                                                        onClick={() => onDeleteChat(chat.id)}
                                                        className="bg-[#D95D24] px-1.5 py-0.5 text-[#060606]"
                                                    >
                                                        yes
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => onConfirmingChange('')}
                                                        className="px-1.5 py-0.5 text-[#8E867D]"
                                                    >
                                                        no
                                                    </button>
                                                </div>
                                            ) : (
                                                <button
                                                    type="button"
                                                    onClick={() => onConfirmingChange(chat.id)}
                                                    className="px-1 font-mono text-[10px] text-[#5C564F] opacity-0 transition-opacity hover:text-[#D95D24] group-hover:opacity-100"
                                                >
                                                    ×
                                                </button>
                                            )}
                                        </div>
                                    );
                                })}
                                {!filteredChats.length && (
                                    <p className="px-2 py-6 text-center font-mono text-[11px] text-[#5C564F]">
                                        No chats found
                                    </p>
                                )}
                            </div>
                        </div>

                        <div className="flex items-center justify-between border-t border-[#F2EFE9]/10 px-4 py-3 font-mono text-[11px] text-[#7D756C]">
                            <span className="truncate">{displayName || 'Local'}</span>
                            <span className={online ? 'text-[#D95D24]' : 'text-[#5C564F]'}>
                                {online ? '● online' : '○ offline'}
                            </span>
                        </div>
                    </motion.aside>
                </>
            )}
        </AnimatePresence>
    );
});

export default ChatHistoryDrawer;
