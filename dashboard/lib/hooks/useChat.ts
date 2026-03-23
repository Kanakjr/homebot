"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { streamDeepAgentEvents, getSnapshotUrl } from "@/lib/api";
import { loadMessages, saveMessages } from "@/lib/hooks/useChatSessions";
import type { ChatMessage, StreamEvent, ToolCallInfo } from "@/lib/types";

export function useChat(
  chatId: number,
  onMessagesChange?: (chatId: number, messages: ChatMessage[]) => void,
) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentEvents, setCurrentEvents] = useState<StreamEvent[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const saved = loadMessages(chatId);
    setMessages(saved);
  }, [chatId]);

  const onChangeCb = useRef(onMessagesChange);
  onChangeCb.current = onMessagesChange;

  useEffect(() => {
    if (chatId === 0) return;
    saveMessages(chatId, messages);
    onChangeCb.current?.(chatId, messages);
  }, [chatId, messages]);

  const send = useCallback(
    async (text: string, model?: string) => {
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
      let uiSpec: { root: string; elements: Record<string, unknown> } | undefined;

      try {
        const stream = streamDeepAgentEvents(
          { message: text, thread_id: String(chatId), model: model || undefined },
          controller.signal
        );

        for await (const raw of stream) {
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
          } else if (event.type === "ui_spec") {
            if (event.spec) {
              uiSpec = event.spec;
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
        uiSpec,
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
    if (chatId !== 0) saveMessages(chatId, []);
  }, [chatId]);

  return { messages, isStreaming, currentEvents, send, stop, clear };
}
