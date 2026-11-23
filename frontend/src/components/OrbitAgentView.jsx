import { useState } from 'react';
import { useOrbitAgent } from '../hooks/useOrbitAgent';

export default function OrbitAgentView({ activeChatId }) {
  const {
    messages,
    reminders,
    connected,
    isLoading,
    isRecording,
    sendMessage,
    startVoiceCapture,
    stopVoiceCapture,
    addReminder,
    toggleReminder,
    deleteReminder,
  } = useOrbitAgent(activeChatId);

  const [inputText, setInputText] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [newRemindAt, setNewRemindAt] = useState('');
  const [showReminderForm, setShowReminderForm] = useState(false);

  const handleSend = (e) => {
    e.preventDefault();
    if (!inputText.trim()) return;
    sendMessage(inputText.trim());
    setInputText('');
  };

  const handleCreateReminder = (e) => {
    e.preventDefault();
    if (!newTitle.trim() || !newRemindAt.trim()) return;
    addReminder(newTitle.trim(), newRemindAt.trim());
    setNewTitle('');
    setNewRemindAt('');
    setShowReminderForm(false);
  };

  return (
    <div className="flex h-full flex-col bg-[#060606] text-[#F2EFE9]">
      {/* Top Status Bar */}
      <div className="flex items-center justify-between border-b border-[#F2EFE9]/12 bg-[#0B0A09] px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em]">
        <span className={connected ? 'text-[#D95D24]' : 'text-[#8E867D]'}>
          {connected ? '● ws:live' : '○ ws:reconnecting'}
        </span>
        <span className="text-[#8E867D]">// orbit007_agent</span>
      </div>

      {/* Main Content Area: Split Reminders & Chat */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {/* Active Reminders Strip */}
        <div className="border-b border-[#F2EFE9]/12 bg-[#090807] px-4 py-3">
          <div className="mb-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.14em]">
            <span className="text-[#D95D24]">
              // live_reminders [{reminders.length}]
            </span>
            <button
              type="button"
              onClick={() => setShowReminderForm(!showReminderForm)}
              className="border border-[#F2EFE9]/16 bg-[#060606] px-2 py-0.5 text-[#F2EFE9] hover:border-[#D95D24] hover:text-[#D95D24]"
            >
              {showReminderForm ? '[cancel]' : '[+ add]'}
            </button>
          </div>

          {showReminderForm && (
            <form onSubmit={handleCreateReminder} className="my-2 flex flex-col gap-2 border border-[#D95D24]/45 bg-[#060606] p-2.5">
              <input
                type="text"
                placeholder="Reminder title..."
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                className="w-full border border-[#F2EFE9]/15 bg-[#0C0B0A] px-2.5 py-1.5 font-mono text-xs text-[#F2EFE9] outline-none focus:border-[#D95D24]"
              />
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="When (e.g. 5:00 PM or tomorrow)"
                  value={newRemindAt}
                  onChange={(e) => setNewRemindAt(e.target.value)}
                  className="flex-1 border border-[#F2EFE9]/15 bg-[#0C0B0A] px-2.5 py-1.5 font-mono text-xs text-[#F2EFE9] outline-none focus:border-[#D95D24]"
                />
                <button
                  type="submit"
                  disabled={!newTitle.trim() || !newRemindAt.trim()}
                  className="border border-[#D95D24] bg-[#D95D24] px-3 py-1 font-mono text-[10px] font-semibold uppercase text-[#060606] disabled:opacity-40"
                >
                  [save]
                </button>
              </div>
            </form>
          )}

          <div className="max-h-28 space-y-1 overflow-y-auto pr-1">
            {reminders.length === 0 ? (
              <p className="py-1 font-mono text-[11px] text-[#6E675F]">// no active reminders</p>
            ) : (
              reminders.map((r) => (
                <div
                  key={r.id}
                  className={`flex items-center justify-between gap-2 border px-2.5 py-1.5 font-mono text-xs ${
                    r.completed
                      ? 'border-[#F2EFE9]/10 bg-[#060606] text-[#6E675F] line-through'
                      : 'border-[#F2EFE9]/14 bg-[#0D0C0B] text-[#F2EFE9]'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => toggleReminder(r.id, !r.completed)}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    <span className={r.completed ? 'text-[#6E675F]' : 'text-[#D95D24]'}>
                      {r.completed ? '[x]' : '[ ]'}
                    </span>
                    <span className="truncate">{r.title || r.text}</span>
                    <span className="shrink-0 text-[10px] text-[#8E867D]">
                      ({r.remind_at || r.run_at})
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteReminder(r.id)}
                    className="text-[10px] text-[#8E867D] hover:text-[#D95D24]"
                  >
                    [rm]
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Message History */}
        <div className="flex-1 space-y-3 overflow-y-auto p-4 text-sm">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center font-mono text-[#7C756C]">
              <p className="text-xs uppercase tracking-[0.16em]">// orbit007 session ready</p>
              <p className="mt-1.5 text-[11px]">
                Say &ldquo;remind me to check server at 6pm&rdquo; or start speaking.
              </p>
            </div>
          ) : (
            messages.map((m, idx) => {
              const isUser = m.role === 'user';
              return (
                <div
                  key={idx}
                  className={`border-l-2 pl-3.5 py-1.5 ${
                    isUser
                      ? 'border-[#D95D24] bg-[#130C08]/60'
                      : 'border-[#F2EFE9]/25'
                  }`}
                >
                  <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-[#8E867D]">
                    {isUser ? '> user' : '// orbit007'}
                  </div>
                  <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-[#F2EFE9]">
                    {m.content}
                    {m.streaming && <span className="ascii-cursor ml-1" />}
                  </div>
                </div>
              );
            })
          )}
          {isLoading && !messages.some((m) => m.streaming) && (
            <div className="font-mono text-xs text-[#D95D24]">
              // processing<span className="ascii-cursor ml-1" />
            </div>
          )}
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="border-t border-[#F2EFE9]/12 bg-[#0B0A09] p-3">
        <form onSubmit={handleSend} className="flex items-center gap-2">
          <button
            type="button"
            onClick={isRecording ? stopVoiceCapture : startVoiceCapture}
            className={`border px-2.5 py-2 font-mono text-[11px] uppercase transition-colors ${
              isRecording
                ? 'border-[#D95D24] bg-[#D95D24] font-semibold text-[#060606]'
                : 'border-[#F2EFE9]/15 bg-[#060606] text-[#8E867D] hover:border-[#D95D24] hover:text-[#F2EFE9]'
            }`}
          >
            {isRecording ? '[rec]' : '[mic]'}
          </button>

          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder={isRecording ? 'Streaming PCM audio...' : 'Type a command for ORBIT007...'}
            disabled={isLoading}
            className="flex-1 border border-[#F2EFE9]/15 bg-[#060606] px-3 py-2 font-mono text-xs text-[#F2EFE9] placeholder:text-[#665F57] outline-none focus:border-[#D95D24]"
          />

          <button
            type="submit"
            disabled={isLoading || !inputText.trim()}
            className="border border-[#D95D24] bg-[#D95D24] px-3.5 py-2 font-mono text-[11px] font-semibold uppercase text-[#060606] hover:bg-[#E86B30] disabled:opacity-35"
          >
            [send]
          </button>
        </form>
      </div>
    </div>
  );
}
