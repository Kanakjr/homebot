"use client";

import { useState, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import ChatWidget from "@/components/ChatWidget";
import ThreadPanel from "@/components/ThreadPanel";

export default function ChatPage() {
  const [chatId, setChatId] = useState(0);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleNewThread = useCallback(() => {
    setChatId(Date.now());
  }, []);

  const handleThreadSelect = useCallback((id: number) => {
    setChatId(id);
  }, []);

  const handleConversationUpdate = useCallback(() => {
    setRefreshTrigger((n) => n + 1);
  }, []);

  return (
    <div className="flex h-full">
      <div className="hidden w-64 lg:block">
        <ThreadPanel
          activeChatId={chatId}
          onSelect={handleThreadSelect}
          onNew={handleNewThread}
          refreshTrigger={refreshTrigger}
        />
      </div>
      <div className="flex flex-1 flex-col p-6 lg:p-8 min-w-0">
        <BlurFade delay={0}>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-white font-mono">AI Chat</h1>
              <p className="text-sm text-neutral-400">
                Talk to HomeBotAI -- control devices, ask questions, create skills
              </p>
            </div>
            <span className="text-xs font-mono text-neutral-600">
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
