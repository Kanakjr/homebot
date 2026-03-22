"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { ChatMessage } from "@/lib/types";

export interface ChatSession {
  id: number;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
  preview: string;
}

const SESSIONS_KEY = "homebot-chat-sessions";
const MSGS_PREFIX = "homebot-chat-msgs-";

function loadSessions(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(SESSIONS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveSessions(sessions: ChatSession[]) {
  localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
}

export function loadMessages(chatId: number): ChatMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(MSGS_PREFIX + chatId);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveMessages(chatId: number, messages: ChatMessage[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(MSGS_PREFIX + chatId, JSON.stringify(messages));
}

function deriveTitle(messages: ChatMessage[]): string {
  const first = messages.find((m) => m.role === "user");
  if (!first) return "New Chat";
  const text = first.content.trim();
  return text.length > 40 ? text.slice(0, 40) + "..." : text;
}

function derivePreview(messages: ChatMessage[]): string {
  const last = messages[messages.length - 1];
  if (!last) return "";
  const text = last.content.trim();
  return text.length > 60 ? text.slice(0, 60) + "..." : text;
}

export function useChatSessions() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const initialized = useRef(false);

  useEffect(() => {
    if (!initialized.current) {
      setSessions(loadSessions());
      initialized.current = true;
    }
  }, []);

  const persist = useCallback((next: ChatSession[]) => {
    setSessions(next);
    saveSessions(next);
  }, []);

  const createSession = useCallback((): number => {
    const id = Date.now();
    const session: ChatSession = {
      id,
      title: "New Chat",
      createdAt: id,
      updatedAt: id,
      messageCount: 0,
      preview: "",
    };
    const next = [session, ...loadSessions()];
    persist(next);
    return id;
  }, [persist]);

  const updateSession = useCallback(
    (chatId: number, messages: ChatMessage[]) => {
      if (messages.length === 0) return;
      const current = loadSessions();
      const idx = current.findIndex((s) => s.id === chatId);
      const updated: ChatSession = {
        id: chatId,
        title: deriveTitle(messages),
        createdAt: idx >= 0 ? current[idx].createdAt : chatId,
        updatedAt: Date.now(),
        messageCount: messages.length,
        preview: derivePreview(messages),
      };
      let next: ChatSession[];
      if (idx >= 0) {
        next = [...current];
        next[idx] = updated;
      } else {
        next = [updated, ...current];
      }
      next.sort((a, b) => b.updatedAt - a.updatedAt);
      persist(next);
    },
    [persist],
  );

  const deleteSession = useCallback(
    (chatId: number) => {
      const next = loadSessions().filter((s) => s.id !== chatId);
      persist(next);
      localStorage.removeItem(MSGS_PREFIX + chatId);
    },
    [persist],
  );

  return { sessions, createSession, updateSession, deleteSession };
}
