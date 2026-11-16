import { useState } from 'react';
import { useOrbitAgent } from '../hooks/useOrbitAgent';
import { Mic, MicOff, Send, CheckCircle2, Circle, Trash2, Plus, Wifi, WifiOff, Loader2 } from 'lucide-react';

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
    <div className="flex h-full flex-col bg-[#111111] text-[#F2EFE9]">
      {/* Top Status Bar */}
      <div className="flex items-center justify-between border-b border-[#F2EFE9]/15 bg-[#141414] px-4 py-2">
        <div className="flex items-center gap-2">
          {connected ? (
            <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-[#F2EFE9]">
              <span className="inline-block h-2 w-2 bg-[#D95D24]" />
              <Wifi size={12} className="text-[#D95D24]" /> LIVE WS
            </span>
          ) : (
            <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9C968E]">
              <WifiOff size={12} /> RECONNECTING
            </span>
          )}
        </div>
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#9C968E]">
          ORBIT007 Agent
        </div>
      </div>

      {/* Main Content Area: Split Reminders & Chat */}
      <div className="flex flex-1 min-h-0 flex-col overflow-hidden">
        {/* Active Reminders Strip */}
        <div className="border-b border-[#F2EFE9]/15 bg-[#131313] px-4 py-2.5">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-[#D95D24]">
              Live Reminders ({reminders.length})
            </span>
            <button
              type="button"
              onClick={() => setShowReminderForm(!showReminderForm)}
              className="flex items-center gap-1 border border-[#F2EFE9]/15 bg-[#151515] px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-[#F2EFE9] transition-colors hover:border-[#D95D24] hover:text-[#D95D24]"
            >
              <Plus size={11} /> {showReminderForm ? 'Cancel' : 'Add'}
            </button>
          </div>

          {showReminderForm && (
            <form onSubmit={handleCreateReminder} className="my-2 flex flex-col gap-2 border border-[#D95D24]/40 bg-[#111111] p-2.5">
              <input
                type="text"
                placeholder="Reminder title..."
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                className="w-full border border-[#F2EFE9]/15 bg-[#151515] px-2.5 py-1.5 text-xs text-[#F2EFE9] outline-none focus:border-[#D95D24]"
              />
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="When (e.g. 5:00 PM or tomorrow)"
                  value={newRemindAt}
                  onChange={(e) => setNewRemindAt(e.target.value)}
                  className="flex-1 border border-[#F2EFE9]/15 bg-[#151515] px-2.5 py-1.5 text-xs text-[#F2EFE9] outline-none focus:border-[#D95D24]"
                />
                <button
                  type="submit"
                  disabled={!newTitle.trim() || !newRemindAt.trim()}
                  className="border border-[#D95D24] bg-[#D95D24] px-3 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#111111] disabled:opacity-40"
                >
                  Save
                </button>
              </div>
            </form>
          )}

          <div className="max-h-28 space-y-1 overflow-y-auto pr-1">
            {reminders.length === 0 ? (
              <p className="py-1 font-mono text-[11px] text-[#9C968E]">No active reminders in database.</p>
            ) : (
              reminders.map((r) => (
                <div
                  key={r.id}
                  className={`flex items-center justify-between gap-2 border px-2 py-1.5 text-xs transition-colors ${
                    r.completed
                      ? 'border-[#F2EFE9]/10 bg-[#111111] text-[#9C968E] line-through'
                      : 'border-[#F2EFE9]/15 bg-[#151515] text-[#F2EFE9]'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => toggleReminder(r.id, !r.completed)}
                    className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                  >
                    {r.completed ? (
                      <CheckCircle2 size={13} className="shrink-0 text-[#9C968E]" />
                    ) : (
                      <Circle size={13} className="shrink-0 text-[#D95D24]" />
                    )}
                    <span className="truncate">{r.title || r.text}</span>
                    <span className="shrink-0 font-mono text-[10px] text-[#9C968E]">
                      ({r.remind_at || r.run_at})
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteReminder(r.id)}
                    className="p-0.5 text-[#9C968E] transition-colors hover:text-[#D95D24]"
                    title="Delete reminder"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Message History */}
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center text-[#9C968E]">
              <p className="font-mono text-xs uppercase tracking-[0.14em]">No messages in session</p>
              <p className="mt-1 text-[11px] text-[#9C968E]/70">
                Say &ldquo;remind me to check server at 6pm&rdquo; or start speaking.
              </p>
            </div>
          ) : (
            messages.map((m, idx) => {
              const isUser = m.role === 'user';
              return (
                <div
                  key={idx}
                  className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
                >
                  <div
                    className={`max-w-[88%] border px-3 py-2 text-xs leading-relaxed ${
                      isUser
                        ? 'border-[#D95D24]/60 bg-[#1B1511] text-[#F2EFE9]'
                        : 'border-[#F2EFE9]/14 bg-[#161616] text-[#F2EFE9]'
                    }`}
                  >
                    <div className="mb-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-[#9C968E]">
                      {m.role}
                    </div>
                    <div>
                      {m.content}
                      {m.streaming && <span className="ml-0.5 inline-block h-3 w-1.5 bg-[#D95D24] align-middle animate-pulse" />}
                    </div>
                  </div>
                </div>
              );
            })
          )}
          {isLoading && !messages.some((m) => m.streaming) && (
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-[#D95D24]">
              <Loader2 size={12} className="animate-spin" />
              <span>ORBIT007 Processing</span>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Bar: AudioWorklet Mic + Input */}
      <div className="border-t border-[#F2EFE9]/15 bg-[#141414] p-3">
        <form onSubmit={handleSend} className="flex items-center gap-2">
          <button
            type="button"
            onClick={isRecording ? stopVoiceCapture : startVoiceCapture}
            className={`border p-2.5 transition-colors ${
              isRecording
                ? 'border-[#D95D24] bg-[#D95D24] text-[#111111]'
                : 'border-[#F2EFE9]/15 bg-[#111111] text-[#9C968E] hover:border-[#D95D24] hover:text-[#F2EFE9]'
            }`}
            title={isRecording ? 'Stop voice capture' : 'Start voice capture (AudioWorklet PCM)'}
          >
            {isRecording ? <MicOff size={15} /> : <Mic size={15} />}
          </button>

          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder={isRecording ? 'Streaming audio...' : 'Type a message or command...'}
            disabled={isLoading}
            className="flex-1 border border-[#F2EFE9]/15 bg-[#111111] px-3 py-2 text-xs text-[#F2EFE9] placeholder:text-[#9C968E]/60 outline-none focus:border-[#D95D24]"
          />

          <button
            type="submit"
            disabled={isLoading || !inputText.trim()}
            className="border border-[#D95D24] bg-[#D95D24] p-2.5 text-[#111111] transition-colors hover:bg-[#C44E19] disabled:cursor-not-allowed disabled:opacity-40"
            title="Send"
          >
            <Send size={15} />
          </button>
        </form>
      </div>
    </div>
  );
}
