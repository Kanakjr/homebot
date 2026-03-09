"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { editDashboard } from "@/lib/api";
import type { DashboardConfig } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AssistantMessage {
  role: "user" | "assistant";
  text: string;
}

interface DashboardAssistantProps {
  onConfigUpdate: (config: DashboardConfig) => void;
}

const STORAGE_KEY = "dashboard-assistant-open";

export default function DashboardAssistant({ onConfigUpdate }: DashboardAssistantProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<AssistantMessage[]>([
    {
      role: "assistant",
      text: "Hi! I can customize your dashboard. Try something like \"add a camera widget\" or \"remove the weather card\".",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "true") setOpen(true);
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(open));
  }, [open]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);

    try {
      const result = await editDashboard(text);
      onConfigUpdate(result.config);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: result.message },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: `Error: ${(err as Error).message}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, onConfigUpdate]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {/* Floating trigger button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-4 right-4 z-50 flex h-12 w-12 items-center justify-center rounded-full bg-cyber-yellow/90 text-black shadow-lg shadow-cyber-yellow/20 hover:bg-cyber-yellow transition-colors sm:bottom-6 sm:right-6"
          aria-label="Open dashboard assistant"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-5 w-5"
          >
            <path d="M12 3l1.912 5.813a2 2 0 001.272 1.278L21 12l-5.816 1.91a2 2 0 00-1.272 1.277L12 21l-1.912-5.813a2 2 0 00-1.272-1.278L3 12l5.816-1.91a2 2 0 001.272-1.277z" />
          </svg>
        </button>
      )}

      {/* Panel */}
      {open && (
        <div className="fixed inset-x-0 bottom-0 z-50 flex flex-col border-t border-white/10 bg-neutral-950/95 shadow-2xl backdrop-blur-xl sm:inset-x-auto sm:bottom-6 sm:right-6 sm:w-[380px] sm:rounded-2xl sm:border">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-cyber-yellow" />
              <h4 className="text-sm font-medium text-white">
                Dashboard Editor
              </h4>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="rounded-md p-1 text-neutral-400 hover:text-white transition-colors"
              aria-label="Close"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                className="h-4 w-4"
              >
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3" style={{ maxHeight: 340 }}>
            {messages.map((msg, i) => (
              <div
                key={i}
                className={cn(
                  "text-sm leading-relaxed",
                  msg.role === "user"
                    ? "text-neutral-300 ml-6 text-right"
                    : "text-neutral-400 mr-6",
                )}
              >
                {msg.role === "assistant" && (
                  <span className="text-cyber-yellow text-xs font-medium mr-1">
                    AI
                  </span>
                )}
                {msg.text}
              </div>
            ))}
            {loading && (
              <div className="text-xs text-neutral-500 animate-pulse">
                Thinking...
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-white/10 px-3 py-3">
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
                placeholder="Describe dashboard changes..."
                className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/40 transition-colors"
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className={cn(
                  "rounded-lg bg-cyber-yellow/90 px-3 py-2 text-sm font-medium text-black hover:bg-cyber-yellow transition-colors",
                  (loading || !input.trim()) && "opacity-40 cursor-not-allowed",
                )}
              >
                Send
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
