import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const ConfirmationModal = ({ isOpen, onClose, onConfirm, title, message, type = 'danger', confirmString }) => {
    const [inputValue, setInputValue] = useState('');

    const handleClose = () => {
        setInputValue('');
        onClose();
    };

    const isConfirmDisabled = Boolean(
        confirmString &&
        inputValue.trim().toLowerCase() !== confirmString.trim().toLowerCase()
    );

    if (!isOpen) return null;

    return (
        <AnimatePresence>
            <div role="dialog" aria-modal="true" className="fixed inset-0 z-[100] flex items-center justify-center bg-black/85 p-4">
                <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 4 }}
                    transition={{ duration: 0.16 }}
                    className="ascii-frame relative w-full max-w-md bg-[#0A0908] p-6"
                >
                    <div className="mb-4 flex items-center justify-between border-b border-[#F2EFE9]/12 pb-3 font-mono text-[10px] uppercase tracking-[0.16em]">
                        <span className={type === 'danger' ? 'text-[#D95D24]' : 'text-[#F2EFE9]'}>
                            {type === 'danger' ? '// confirm_destructive_action' : '// confirm_action'}
                        </span>
                        <button
                            type="button"
                            onClick={handleClose}
                            className="text-[#8E867D] hover:text-[#F2EFE9]"
                        >
                            [x]
                        </button>
                    </div>

                    <h3 className="text-lg font-semibold tracking-wide text-[#F2EFE9]">{title}</h3>
                    <p className="mt-2 font-mono text-xs leading-relaxed text-[#8E867D]">{message}</p>

                    {confirmString && (
                        <div className="mt-5 border border-[#F2EFE9]/12 bg-[#060606] p-3">
                            <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-[#8E867D]">
                                Type <span className="select-all text-[#D95D24]">{confirmString}</span> to confirm
                            </p>
                            <input
                                type="text"
                                value={inputValue}
                                onChange={(e) => setInputValue(e.target.value)}
                                onKeyDown={async (e) => {
                                    if (e.key === 'Enter' && !isConfirmDisabled) {
                                        e.preventDefault();
                                        await onConfirm();
                                        handleClose();
                                    }
                                }}
                                autoFocus
                                className="w-full border border-[#F2EFE9]/18 bg-[#0C0B0A] px-3 py-2 font-mono text-xs text-[#F2EFE9] outline-none focus:border-[#D95D24]"
                                placeholder={confirmString}
                            />
                        </div>
                    )}

                    <div className="mt-6 flex gap-2.5 font-mono text-xs uppercase tracking-[0.14em]">
                        <button
                            type="button"
                            onClick={handleClose}
                            className="flex-1 border border-[#F2EFE9]/16 bg-[#060606] px-4 py-2.5 text-[#8E867D] hover:border-[#F2EFE9]/40 hover:text-[#F2EFE9]"
                        >
                            [cancel]
                        </button>
                        <button
                            type="button"
                            onClick={async () => {
                                await onConfirm();
                                handleClose();
                            }}
                            disabled={isConfirmDisabled}
                            className={`flex-1 border px-4 py-2.5 font-semibold transition-colors ${
                                isConfirmDisabled
                                    ? 'cursor-not-allowed border-[#F2EFE9]/10 bg-[#151311] text-[#5C564F]'
                                    : 'border-[#D95D24] bg-[#D95D24] text-[#060606] hover:bg-[#E86B30]'
                            }`}
                        >
                            [confirm]
                        </button>
                    </div>
                </motion.div>
            </div>
        </AnimatePresence>
    );
};

export default ConfirmationModal;
