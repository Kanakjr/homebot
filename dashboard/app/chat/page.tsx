"use client";

import { useState, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import ChatWidget from "@/components/ChatWidget";

export default function ChatPage() {
  const [chatId, setChatId] = useState(0);

  const handleNewChat = useCallback(() => {
    setChatId(Date.now());
  }, []);

  return (
    <div className="flex h-full">
      <div className="flex flex-1 flex-col p-4 sm:p-6 lg:p-8 min-w-0">
        <BlurFade delay={0}>
          <div className="mb-4 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <h1 className="text-xl sm:text-2xl font-bold text-white font-mono">
                AI Chat
              </h1>
              <p className="text-xs sm:text-sm text-neutral-400 truncate">
                Talk to HomeBotAI -- control devices, manage media, ask questions
              </p>
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
          <ChatWidget className="h-full" chatId={chatId} />
        </BlurFade>
      </div>
    </div>
  );
}
