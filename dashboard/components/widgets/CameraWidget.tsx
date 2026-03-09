"use client";

import { useState, useCallback, useEffect } from "react";
import { takeCameraSnapshot, getSnapshotUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CameraWidgetProps {
  config: { entity_id: string };
}

export default function CameraWidget({ config }: CameraWidgetProps) {
  const [filename, setFilename] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ts, setTs] = useState(0);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const result = await takeCameraSnapshot(config.entity_id);
      setFilename(result.filename);
      setTs(Date.now());
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [config.entity_id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const imgUrl = filename ? `${getSnapshotUrl(filename)}?t=${ts}` : null;

  return (
    <div className="space-y-2">
      <div className="relative aspect-video rounded-lg bg-black/40 overflow-hidden">
        {imgUrl ? (
          <img
            src={imgUrl}
            alt={config.entity_id}
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-neutral-500 text-xs">
            {loading ? "Loading..." : "No snapshot"}
          </div>
        )}
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/30">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-cyber-yellow border-t-transparent" />
          </div>
        )}
      </div>
      <button
        onClick={refresh}
        disabled={loading}
        className={cn(
          "w-full rounded-md bg-white/5 py-1.5 text-xs text-neutral-400 hover:text-white hover:bg-white/10 transition-colors",
          loading && "opacity-50",
        )}
      >
        Refresh Snapshot
      </button>
    </div>
  );
}
