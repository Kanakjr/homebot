"use client";

import { useState, useCallback, useRef } from "react";
import { streamChatEvents, getSnapshotUrl } from "@/lib/api";
import type { ChatMessage, StreamEvent, ToolCallInfo } from "@/lib/types";

export function useChat(chatId: number = 0) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentEvents, setCurrentEvents] = useState<StreamEvent[]>([]);
  const abortRef = useRef<AbortController | null>(null);

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

  const clear = useCallback(() => {
    setMessages([]);
    setCurrentEvents([]);
  }, []);

  return { messages, isStreaming, currentEvents, send, stop, clear };
}
