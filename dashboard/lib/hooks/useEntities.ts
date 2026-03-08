"use client";

import { useState, useEffect, useCallback } from "react";
import { getEntities } from "@/lib/api";
import type { EntitiesResponse } from "@/lib/types";

export function useEntities(pollIntervalMs: number = 30_000) {
  const [data, setData] = useState<EntitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const result = await getEntities();
      setData(result);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    if (pollIntervalMs <= 0) return;

    const interval = setInterval(refresh, pollIntervalMs);
    return () => clearInterval(interval);
  }, [refresh, pollIntervalMs]);

  // Refresh on window focus
  useEffect(() => {
    const onFocus = () => refresh();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  return { data, error, loading, refresh };
}
