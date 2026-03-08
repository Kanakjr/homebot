"use client";

import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { useChat } from "@/lib/hooks/useChat";
import type { StreamEvent, ToolCallInfo } from "@/lib/types";

function ToolCallBubble({ tc }: { tc: ToolCallInfo }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-xs font-mono">
      <div className="flex items-center gap-2 text-cyber-yellow">
        <span>tool</span>
        <span className="text-white">{tc.name}</span>
        {tc.duration_ms != null && (
          <span className="text-neutral-500 ml-auto">{tc.duration_ms}ms</span>
        )}
      </div>
      {tc.args && Object.keys(tc.args).length > 0 && (
        <pre className="mt-1 text-neutral-400 overflow-x-auto">
          {JSON.stringify(tc.args, null, 2)}
        </pre>
      )}
      {tc.result && (
        <div className="mt-1 text-neutral-500 truncate">
          {tc.result.slice(0, 200)}
        </div>
      )}
    </div>
  );
}

function StreamingIndicator({ events }: { events: StreamEvent[] }) {
  const latest = events[events.length - 1];
  if (!latest) return null;

  if (latest.type === "thinking") {
    return (
      <div className="flex items-center gap-2 text-sm text-neutral-400 animate-pulse">
        <div className="h-2 w-2 rounded-full bg-cyber-yellow animate-pulse" />
        Thinking...
      </div>
    );
  }

  if (latest.type === "tool_call") {
    return (
      <div className="rounded-lg border border-cyber-yellow/20 bg-cyber-yellow/5 p-3 text-xs font-mono">
        <span className="text-cyber-yellow">calling</span>{" "}
        <span className="text-white">{latest.name}</span>
      </div>
    );
  }

  if (latest.type === "tool_result") {
    return (
      <div className="flex items-center gap-2 text-sm text-neutral-400">
        <div className="h-2 w-2 rounded-full bg-green-400" />
        {latest.name} completed
      </div>
    );
  }

  return null;
}

interface ChatWidgetProps {
  className?: string;
  chatId?: number;
  compact?: boolean;
}

export default function ChatWidget({
  className,
  chatId = 0,
  compact = false,
}: ChatWidgetProps) {
  const { messages, isStreaming, currentEvents, send, stop, clear } =
    useChat(chatId);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, currentEvents]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    send(input);
    setInput("");
  };

  return (
    <div
      className={cn(
        "flex flex-col rounded-xl border border-white/10 bg-white/5",
        compact ? "h-80" : "h-full",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2">
        <h3 className="text-sm font-mono text-neutral-300">AI Chat</h3>
        <button
          onClick={clear}
          className="text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
        >
          Clear
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && !isStreaming && (
          <p className="text-sm text-neutral-500 text-center py-8">
            Ask HomeBotAI anything about your home.
          </p>
        )}

        {messages.map((msg, i) => (
          <div key={i} className="space-y-2">
            {msg.role === "user" ? (
              <div className="flex justify-end">
                <div className="max-w-[80%] rounded-lg bg-cyber-yellow/10 border border-cyber-yellow/20 px-3 py-2 text-sm text-white">
                  {msg.content}
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {msg.toolCalls?.map((tc, j) => (
                  <ToolCallBubble key={j} tc={tc} />
                ))}
                <div className="max-w-[90%] rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-neutral-200">
                  {msg.content}
                </div>
              </div>
            )}
          </div>
        ))}

        {isStreaming && <StreamingIndicator events={currentEvents} />}
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 border-t border-white/10 p-3"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          disabled={isStreaming}
          className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/50 transition-colors"
        />
        {isStreaming ? (
          <button
            type="button"
            onClick={stop}
            className="rounded-lg bg-red-500/20 px-4 py-2 text-sm text-red-400 hover:bg-red-500/30 transition-colors"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim()}
            className="rounded-lg bg-cyber-yellow/20 px-4 py-2 text-sm text-cyber-yellow hover:bg-cyber-yellow/30 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        )}
      </form>
    </div>
  );
}
