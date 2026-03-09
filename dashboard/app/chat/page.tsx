"use client";

import { useState, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import ChatWidget from "@/components/ChatWidget";
import ThreadPanel from "@/components/ThreadPanel";
import { cn } from "@/lib/utils";

export default function ChatPage() {
  const [chatId, setChatId] = useState(0);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [showThreads, setShowThreads] = useState(false);

  const handleNewThread = useCallback(() => {
    setChatId(Date.now());
    setShowThreads(false);
  }, []);

  const handleThreadSelect = useCallback((id: number) => {
    setChatId(id);
    setShowThreads(false);
  }, []);

  const handleConversationUpdate = useCallback(() => {
    setRefreshTrigger((n) => n + 1);
  }, []);

  return (
    <div className="flex h-full">
      {/* Desktop thread panel */}
      <div className="hidden w-64 lg:block">
        <ThreadPanel
          activeChatId={chatId}
          onSelect={handleThreadSelect}
          onNew={handleNewThread}
          refreshTrigger={refreshTrigger}
        />
      </div>

      {/* Mobile thread drawer */}
      {showThreads && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setShowThreads(false)}
        />
      )}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-64 transition-transform duration-300 lg:hidden",
          showThreads ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <ThreadPanel
          activeChatId={chatId}
          onSelect={handleThreadSelect}
          onNew={handleNewThread}
          refreshTrigger={refreshTrigger}
        />
      </div>

      <div className="flex flex-1 flex-col p-4 sm:p-6 lg:p-8 min-w-0">
        <BlurFade delay={0}>
          <div className="mb-4 flex items-center justify-between gap-2">
            <div className="flex items-center gap-3 min-w-0">
              <button
                onClick={() => setShowThreads(true)}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-neutral-400 hover:bg-white/10 hover:text-white transition-colors lg:hidden"
                aria-label="Show threads"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 6.75h12M8.25 12h12m-12 5.25h12M3.75 6.75h.007v.008H3.75V6.75zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zM3.75 12h.007v.008H3.75V12zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm-.375 5.25h.007v.008H3.75v-.008zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
                </svg>
              </button>
              <div className="min-w-0">
                <h1 className="text-xl sm:text-2xl font-bold text-white font-mono">AI Chat</h1>
                <p className="text-xs sm:text-sm text-neutral-400 truncate">
                  Talk to HomeBotAI -- control devices, ask questions, create skills
                </p>
              </div>
            </div>
            <span className="hidden text-xs font-mono text-neutral-600 sm:block">
              thread #{chatId}
            </span>
          </div>
        </BlurFade>

        <BlurFade delay={0.1} className="flex-1 min-h-0">
          <ChatWidget
            className="h-full"
            chatId={chatId}
            onConversationUpdate={handleConversationUpdate}
          />
        </BlurFade>
      </div>
    </div>
  );
}
