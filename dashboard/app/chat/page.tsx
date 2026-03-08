"use client";

import { BlurFade } from "@/components/magicui/blur-fade";
import ChatWidget from "@/components/ChatWidget";

export default function ChatPage() {
  return (
    <div className="flex h-full flex-col p-6 lg:p-8">
      <BlurFade delay={0}>
        <div className="mb-4">
          <h1 className="text-2xl font-bold text-white font-mono">AI Chat</h1>
          <p className="text-sm text-neutral-400">
            Talk to HomeBotAI -- control devices, ask questions, create skills
          </p>
        </div>
      </BlurFade>

      <BlurFade delay={0.1} className="flex-1 min-h-0">
        <ChatWidget className="h-full" />
      </BlurFade>
    </div>
  );
}
