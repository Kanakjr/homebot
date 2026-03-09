"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { streamChatEvents, getSnapshotUrl, getHistory, clearHistory } from "@/lib/api";
import type { ChatMessage, StreamEvent, ToolCallInfo } from "@/lib/types";

export function useChat(chatId: number) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentEvents, setCurrentEvents] = useState<StreamEvent[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;
    setMessages([]);
    setHistoryLoaded(false);

    getHistory(chatId).then((data) => {
      if (cancelled) return;
      const restored: ChatMessage[] = data.messages.map((m) => ({
        role: m.role as "user" | "assistant",
        content: m.text,
        timestamp: new Date(m.ts + "Z").getTime(),
      }));
      setMessages(restored);
      setHistoryLoaded(true);
    }).catch(() => {
      if (!cancelled) setHistoryLoaded(true);
    });

    return () => { cancelled = true; };
  }, [chatId]);

  const send = useCallback(
    async (text: string) => {
      if (!text.trim() || isStreaming) return;

      const userMsg: ChatMessage = {
        role: "user",
        content: text,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setCurrentEvents([]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const toolCalls: ToolCallInfo[] = [];
      const images: string[] = [];
      let responseText = "";

      try {
        for await (const raw of streamChatEvents(
          { message: text, chat_id: chatId },
          controller.signal
        )) {
          if (raw.type === "done") break;

          const event: StreamEvent = JSON.parse(raw.data);
          setCurrentEvents((prev) => [...prev, event]);

          if (event.type === "tool_call") {
            toolCalls.push({
              name: event.name ?? "",
              args: event.args ?? {},
            });
          } else if (event.type === "tool_result") {
            const tc = toolCalls.find(
              (t) => t.name === event.name && !t.result
            );
            if (tc) {
              tc.result = event.content;
              tc.duration_ms = event.duration_ms;
            }
          } else if (event.type === "image") {
            if (event.filename) {
              images.push(getSnapshotUrl(event.filename));
            }
          } else if (event.type === "response") {
            responseText = event.content ?? "";
          } else if (event.type === "error") {
            responseText = event.content ?? "An error occurred.";
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          responseText = `Connection error: ${(err as Error).message}`;
        }
      }

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: responseText,
        toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
        images: images.length > 0 ? images : undefined,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setCurrentEvents([]);
      setIsStreaming(false);
      abortRef.current = null;
    },
    [chatId, isStreaming]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
  }, []);

  const clear = useCallback(async () => {
    await clearHistory(chatId).catch(() => {});
    setMessages([]);
    setCurrentEvents([]);
  }, [chatId]);

  return { messages, isStreaming, currentEvents, historyLoaded, send, stop, clear };
}
