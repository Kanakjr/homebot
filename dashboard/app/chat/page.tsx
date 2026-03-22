"use client";

import { useState, useCallback, useEffect } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import ChatWidget from "@/components/ChatWidget";
import {
  useChatSessions,
  type ChatSession,
} from "@/lib/hooks/useChatSessions";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

function formatTime(ts: number): string {
  const now = Date.now();
  const diffMin = Math.floor((now - ts) / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return new Date(ts).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function HistoryPanel({
  sessions,
  activeChatId,
  onSelect,
  onNew,
  onDelete,
}: {
  sessions: ChatSession[];
  activeChatId: number;
  onSelect: (id: number) => void;
  onNew: () => void;
  onDelete: (id: number) => void;
}) {
  return (
    <div className="flex h-full flex-col border-r border-white/10 bg-white/[0.02]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <h3 className="text-sm font-mono text-neutral-300">History</h3>
        <button
          onClick={onNew}
          className="rounded-md bg-cyber-yellow/20 px-2.5 py-1 text-xs text-cyber-yellow hover:bg-cyber-yellow/30 transition-colors"
        >
          + New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 ? (
          <p className="px-4 py-6 text-xs text-neutral-500 text-center">
            No conversations yet.
          </p>
        ) : (
          <div className="py-1">
            {sessions.map((s) => (
              <div
                key={s.id}
                onClick={() => onSelect(s.id)}
                className={cn(
                  "group flex cursor-pointer items-start gap-2 px-4 py-2.5 transition-colors",
                  s.id === activeChatId
                    ? "bg-cyber-yellow/10 border-l-2 border-cyber-yellow"
                    : "hover:bg-white/5 border-l-2 border-transparent",
                )}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-neutral-200 truncate">
                    {s.title}
                  </p>
                  <div className="mt-0.5 flex items-center gap-2">
                    <span className="text-[10px] text-neutral-600">
                      {formatTime(s.updatedAt)}
                    </span>
                    {s.messageCount > 0 && (
                      <span className="text-[10px] text-neutral-600">
                        {s.messageCount} msgs
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(s.id);
                  }}
                  className="shrink-0 rounded p-1 text-neutral-600 opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-500/10 transition-all"
                  title="Delete"
                >
                  <svg
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className="h-3.5 w-3.5"
                  >
                    <path
                      fillRule="evenodd"
                      d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 1 0 .23 1.482l.149-.022.841 10.518A2.75 2.75 0 0 0 7.596 19h4.807a2.75 2.75 0 0 0 2.742-2.53l.841-10.519.149.023a.75.75 0 0 0 .23-1.482A41.03 41.03 0 0 0 14 4.193V3.75A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4ZM8.58 7.72a.75.75 0 0 0-1.5.06l.3 7.5a.75.75 0 1 0 1.5-.06l-.3-7.5Zm4.34.06a.75.75 0 1 0-1.5-.06l-.3 7.5a.75.75 0 1 0 1.5.06l.3-7.5Z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { sessions, createSession, updateSession, deleteSession } =
    useChatSessions();
  const [chatId, setChatId] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(true);

  useEffect(() => {
    if (chatId !== 0) return;
    if (sessions.length > 0) {
      setChatId(sessions[0].id);
    }
  }, [sessions, chatId]);

  const handleNewChat = useCallback(() => {
    const id = createSession();
    setChatId(id);
  }, [createSession]);

  const handleSelect = useCallback((id: number) => {
    setChatId(id);
  }, []);

  const handleDelete = useCallback(
    (id: number) => {
      deleteSession(id);
      if (id === chatId) {
        const remaining = sessions.filter((s) => s.id !== id);
        setChatId(remaining.length > 0 ? remaining[0].id : 0);
      }
    },
    [chatId, deleteSession, sessions],
  );

  const handleMessagesChange = useCallback(
    (cid: number, messages: ChatMessage[]) => {
      updateSession(cid, messages);
    },
    [updateSession],
  );

  return (
    <div className="flex h-full">
      {/* Mobile history toggle */}
      <button
        onClick={() => setHistoryOpen((v) => !v)}
        className="fixed bottom-4 right-4 z-30 flex h-10 w-10 items-center justify-center rounded-full bg-cyber-yellow/20 text-cyber-yellow shadow-lg lg:hidden"
        aria-label="Toggle history"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          className="h-5 w-5"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
          />
        </svg>
      </button>

      {/* History sidebar */}
      <div
        className={cn(
          "shrink-0 transition-all duration-200 overflow-hidden",
          historyOpen ? "w-60" : "w-0",
          "max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:z-20 max-lg:bg-true-black",
          !historyOpen && "max-lg:pointer-events-none",
        )}
      >
        <div className="h-full w-60">
          <HistoryPanel
            sessions={sessions}
            activeChatId={chatId}
            onSelect={(id) => {
              handleSelect(id);
              if (window.innerWidth < 1024) setHistoryOpen(false);
            }}
            onNew={() => {
              handleNewChat();
              if (window.innerWidth < 1024) setHistoryOpen(false);
            }}
            onDelete={handleDelete}
          />
        </div>
      </div>

      {/* Overlay for mobile when history is open */}
      {historyOpen && (
        <div
          className="fixed inset-0 z-10 bg-black/50 lg:hidden"
          onClick={() => setHistoryOpen(false)}
        />
      )}

      {/* Main chat area */}
      <div className="flex flex-1 flex-col p-4 sm:p-6 lg:p-8 min-w-0">
        <BlurFade delay={0}>
          <div className="mb-4 flex items-center justify-between gap-2">
            <div className="flex items-center gap-3 min-w-0">
              <button
                onClick={() => setHistoryOpen((v) => !v)}
                className="hidden lg:flex h-8 w-8 items-center justify-center rounded-lg text-neutral-400 hover:bg-white/10 hover:text-white transition-colors"
                aria-label="Toggle history"
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  className="h-4 w-4"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"
                  />
                </svg>
              </button>
              <div className="min-w-0">
                <h1 className="text-xl sm:text-2xl font-bold text-white font-mono">
                  AI Chat
                </h1>
                <p className="text-xs sm:text-sm text-neutral-400 truncate">
                  Talk to HomeBotAI -- control devices, manage media, ask
                  questions
                </p>
              </div>
            </div>
            <button
              onClick={handleNewChat}
              className="shrink-0 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-mono text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
            >
              New Chat
            </button>
          </div>
        </BlurFade>

        <BlurFade delay={0.1} className="flex-1 min-h-0">
          <ChatWidget
            className="h-full"
            chatId={chatId}
            onMessagesChange={handleMessagesChange}
          />
        </BlurFade>
      </div>
    </div>
  );
}
