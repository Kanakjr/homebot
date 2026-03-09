"use client";

import { useState, useEffect, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { getMemory, addMemory, deleteMemory } from "@/lib/api";
import type { MemoryFact } from "@/lib/types";

export default function MemoryPage() {
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const refresh = useCallback(() => {
    setLoading(true);
    getMemory()
      .then((data) => {
        setFacts(data.facts);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleAdd = async () => {
    if (!newKey.trim() || !newValue.trim()) return;
    setSaving(true);
    try {
      await addMemory(newKey.trim(), newValue.trim());
      setNewKey("");
      setNewValue("");
      setShowAdd(false);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (key: string) => {
    try {
      await deleteMemory(key);
      setConfirmDelete(null);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const filtered = facts.filter((f) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return f.key.toLowerCase().includes(q) || f.value.toLowerCase().includes(q);
  });

  return (
    <div className="p-6 lg:p-8 space-y-6 max-w-5xl">
      <BlurFade delay={0}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white font-mono">Memory</h1>
            <p className="text-sm text-neutral-400">
              {facts.length} stored fact{facts.length !== 1 ? "s" : ""} and
              preferences
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              className="text-xs text-neutral-500 hover:text-neutral-300 font-mono transition-colors"
            >
              Refresh
            </button>
            {!showAdd && (
              <button
                onClick={() => setShowAdd(true)}
                className="rounded-md bg-cyber-yellow/20 px-3 py-1.5 text-xs text-cyber-yellow hover:bg-cyber-yellow/30 transition-colors"
              >
                + Add Fact
              </button>
            )}
          </div>
        </div>
      </BlurFade>

      {error && (
        <div className="flex items-center justify-between rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-2">
          <p className="text-sm text-red-400">{error}</p>
          <button
            onClick={() => setError(null)}
            className="text-xs text-red-400/60 hover:text-red-400"
          >
            dismiss
          </button>
        </div>
      )}

      {showAdd && (
        <BlurFade delay={0.05}>
          <div className="rounded-xl border border-white/10 bg-white/5 p-5 space-y-3">
            <h3 className="text-sm font-bold text-white font-mono">
              Add Fact
            </h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="text-xs text-neutral-400">Key</label>
                <input
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  placeholder="preferred_temperature"
                  className="mt-1 w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-neutral-600 outline-none focus:border-cyber-yellow/50"
                />
              </div>
              <div>
                <label className="text-xs text-neutral-400">Value</label>
                <input
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  placeholder="22 degrees celsius"
                  className="mt-1 w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-neutral-600 outline-none focus:border-cyber-yellow/50"
                />
              </div>
            </div>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => {
                  setShowAdd(false);
                  setNewKey("");
                  setNewValue("");
                }}
                className="rounded-md px-3 py-1.5 text-xs text-neutral-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleAdd}
                disabled={saving || !newKey.trim() || !newValue.trim()}
                className="rounded-md bg-cyber-yellow/20 px-4 py-1.5 text-xs text-cyber-yellow hover:bg-cyber-yellow/30 disabled:opacity-40 transition-colors"
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </BlurFade>
      )}

      <BlurFade delay={0.1}>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search facts..."
          className="w-full max-w-md rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/50 transition-colors"
        />
      </BlurFade>

      {loading && (
        <p className="text-sm text-neutral-500 animate-pulse">
          Loading memory...
        </p>
      )}

      {!loading && filtered.length === 0 && (
        <BlurFade delay={0.15}>
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center">
            <p className="text-neutral-400">
              {facts.length === 0
                ? "No facts stored yet."
                : "No facts match your search."}
            </p>
            <p className="mt-2 text-sm text-neutral-500">
              The AI stores preferences and facts here automatically, or you can
              add them manually.
            </p>
          </div>
        </BlurFade>
      )}

      <div className="space-y-2">
        {filtered.map((fact, i) => (
          <BlurFade key={fact.key} delay={0.12 + i * 0.02}>
            <div className="group flex items-start gap-3 rounded-lg border border-white/10 bg-white/5 px-4 py-3 transition-all hover:border-white/20">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-mono text-cyber-yellow">
                  {fact.key}
                </p>
                <p className="mt-1 text-sm text-neutral-300 break-words">
                  {fact.value}
                </p>
              </div>
              <div className="shrink-0">
                {confirmDelete === fact.key ? (
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleDelete(fact.key)}
                      className="text-xs text-red-400 hover:text-red-300 font-bold transition-colors"
                    >
                      Yes
                    </button>
                    <button
                      onClick={() => setConfirmDelete(null)}
                      className="text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
                    >
                      No
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDelete(fact.key)}
                    className="rounded p-1 text-neutral-600 opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-500/10 transition-all"
                    title="Delete"
                  >
                    <svg
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      className="h-3.5 w-3.5"
                    >
                      <path
                        fillRule="evenodd"
                        d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 1 0 .23 1.482l.149-.022.841 10.518A2.75 2.75 0 0 0 7.596 19h4.807a2.75 2.75 0 0 0 2.742-2.53l.841-10.519.149.023a.75.75 0 0 0 .23-1.482A41.03 41.03 0 0 0 14 4.193V3.75A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4ZM8.58 7.72a.75.75 0 0 0-1.5.06l.3 7.5a.75.75 0 1 0 1.5-.06l-.3-7.5Zm4.34.06a.75.75 0 1 0-1.5-.06l-.3 7.5a.75.75 0 1 0 1.5.06l.3-7.5Z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </button>
                )}
              </div>
            </div>
          </BlurFade>
        ))}
      </div>
    </div>
  );
}
