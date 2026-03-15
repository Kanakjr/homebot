"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { getDashboardSummary } from "@/lib/api";

export default function AiSummaryBanner() {
  const [summary, setSummary] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);

  const fetchSummary = useCallback(async (force = false) => {
    if (force) setRegenerating(true);
    else setLoading(true);
    try {
      const result = await getDashboardSummary(force);
      setSummary(result.summary);
    } catch {
      setSummary(null);
    } finally {
      setLoading(false);
      setRegenerating(false);
    }
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-r from-cyber-yellow/[0.06] via-white/[0.02] to-purple-500/[0.06] p-5 backdrop-blur-sm">
      <div className="absolute inset-0 bg-gradient-to-r from-cyber-yellow/5 to-transparent opacity-50" />
      <div className="relative flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <div className="h-2 w-2 rounded-full bg-cyber-yellow animate-pulse" />
            <span className="text-xs font-medium text-cyber-yellow/80 uppercase tracking-wider">
              AI Summary
            </span>
          </div>

          <AnimatePresence mode="wait">
            {loading ? (
              <motion.div
                key="skeleton"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-2"
              >
                <div className="h-4 w-3/4 rounded bg-white/5 animate-pulse" />
                <div className="h-4 w-1/2 rounded bg-white/5 animate-pulse" />
              </motion.div>
            ) : summary ? (
              <motion.p
                key="summary"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.5, ease: "easeOut" }}
                className="text-sm leading-relaxed text-neutral-300"
              >
                {summary}
              </motion.p>
            ) : (
              <motion.p
                key="fallback"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-sm text-neutral-500"
              >
                Welcome home. Everything is running smoothly.
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        <button
          onClick={() => fetchSummary(true)}
          disabled={regenerating}
          className="shrink-0 rounded-lg p-2 text-neutral-500 hover:text-cyber-yellow hover:bg-white/5 transition-colors disabled:opacity-40"
          aria-label="Regenerate summary"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`h-4 w-4 ${regenerating ? "animate-spin" : ""}`}
          >
            <path d="M12 3l1.912 5.813a2 2 0 001.272 1.278L21 12l-5.816 1.91a2 2 0 00-1.272 1.277L12 21l-1.912-5.813a2 2 0 00-1.272-1.278L3 12l5.816-1.91a2 2 0 001.272-1.277z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
