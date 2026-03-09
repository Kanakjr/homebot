"use client";

import { useState, useEffect, useCallback } from "react";
import { getThreads, clearHistory } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ThreadInfo } from "@/lib/types";

interface ThreadPanelProps {
  activeChatId: number;
  onSelect: (chatId: number) => void;
  onNew: () => void;
  refreshTrigger?: number;
}

function formatTime(ts: string): string {
  const d = new Date(ts + "Z");
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + "..." : s;
}

export default function ThreadPanel({
  activeChatId,
  onSelect,
  onNew,
  refreshTrigger = 0,
}: ThreadPanelProps) {
  const [threads, setThreads] = useState<ThreadInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    getThreads()
      .then((data) => setThreads(data.threads))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh, refreshTrigger]);

  const handleDelete = async (e: React.MouseEvent, chatId: number) => {
    e.stopPropagation();
    await clearHistory(chatId).catch(() => {});
    refresh();
    if (chatId === activeChatId) {
      onNew();
    }
  };

  return (
    <div className="flex h-full flex-col border-r border-white/10 bg-white/[0.02]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <h3 className="text-sm font-mono text-neutral-300">Threads</h3>
        <button
          onClick={onNew}
          className="rounded-md bg-cyber-yellow/20 px-2.5 py-1 text-xs text-cyber-yellow hover:bg-cyber-yellow/30 transition-colors"
        >
          + New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && threads.length === 0 ? (
          <p className="px-4 py-6 text-xs text-neutral-500 text-center">
            Loading...
          </p>
        ) : threads.length === 0 ? (
          <p className="px-4 py-6 text-xs text-neutral-500 text-center">
            No conversations yet.
          </p>
        ) : (
          <div className="py-1">
            {threads.map((t) => (
              <div
                key={t.chat_id}
                onClick={() => onSelect(t.chat_id)}
                className={cn(
                  "group flex cursor-pointer items-start gap-2 px-4 py-2.5 transition-colors",
                  t.chat_id === activeChatId
                    ? "bg-cyber-yellow/10 border-l-2 border-cyber-yellow"
                    : "hover:bg-white/5 border-l-2 border-transparent"
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-neutral-400">
                      #{t.chat_id}
                    </span>
                    <span className="text-[10px] text-neutral-600">
                      {formatTime(t.last_ts)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-neutral-300 truncate">
                    {truncate(t.last_message, 60)}
                  </p>
                  <span className="text-[10px] text-neutral-600">
                    {t.message_count} messages
                  </span>
                </div>
                <button
                  onClick={(e) => handleDelete(e, t.chat_id)}
                  className="shrink-0 rounded p-1 text-neutral-600 opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-500/10 transition-all"
                  title="Delete thread"
                >
                  <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
                    <path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 1 0 .23 1.482l.149-.022.841 10.518A2.75 2.75 0 0 0 7.596 19h4.807a2.75 2.75 0 0 0 2.742-2.53l.841-10.519.149.023a.75.75 0 0 0 .23-1.482A41.03 41.03 0 0 0 14 4.193V3.75A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4ZM8.58 7.72a.75.75 0 0 0-1.5.06l.3 7.5a.75.75 0 1 0 1.5-.06l-.3-7.5Zm4.34.06a.75.75 0 1 0-1.5-.06l-.3 7.5a.75.75 0 1 0 1.5.06l.3-7.5Z" clipRule="evenodd" />
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
