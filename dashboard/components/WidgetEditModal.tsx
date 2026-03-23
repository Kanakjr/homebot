"use client";

import { useState, useEffect } from "react";
import type { DashboardWidget, WidgetSize } from "@/lib/types";
import { cn } from "@/lib/utils";

interface WidgetEditModalProps {
  widget: DashboardWidget | null;
  open: boolean;
  onClose: () => void;
  onSave: (update: { id: string; title: string; size: WidgetSize }) => void;
}

const SIZE_OPTIONS: { value: WidgetSize; label: string }[] = [
  { value: "sm", label: "Small (1 col)" },
  { value: "md", label: "Medium (2 col)" },
  { value: "lg", label: "Large (3 col)" },
  { value: "full", label: "Full width" },
];

export default function WidgetEditModal({
  widget,
  open,
  onClose,
  onSave,
}: WidgetEditModalProps) {
  const [title, setTitle] = useState("");
  const [size, setSize] = useState<WidgetSize>("md");

  useEffect(() => {
    if (widget && open) {
      setTitle(widget.title);
      setSize(widget.size);
    }
  }, [widget, open]);

  if (!open || !widget) return null;

  const handleSave = () => {
    onSave({ id: widget.id, title: title.trim() || widget.title, size });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-sm rounded-2xl border border-white/10 bg-neutral-950/95 shadow-2xl backdrop-blur-xl overflow-hidden">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
          <h3 className="text-sm font-medium text-white">Edit Widget</h3>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-neutral-400 hover:text-white transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              className="h-4 w-4"
            >
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-4 p-5">
          <div>
            <label className="block text-xs text-neutral-400 mb-1">
              Title
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/40 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs text-neutral-400 mb-1">Size</label>
            <div className="flex gap-2">
              {SIZE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setSize(opt.value)}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-xs transition-all",
                    size === opt.value
                      ? "bg-cyber-yellow/20 text-cyber-yellow border border-cyber-yellow/30"
                      : "bg-white/5 text-neutral-400 border border-transparent hover:bg-white/10",
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="text-[10px] text-neutral-600 font-mono truncate">
            Type: {widget.type} / ID: {widget.id}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-white/10 px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-lg bg-white/5 px-4 py-2 text-sm text-neutral-300 border border-white/10 hover:bg-white/10 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="rounded-lg bg-cyber-yellow/90 px-4 py-2 text-sm font-medium text-black hover:bg-cyber-yellow transition-colors"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
