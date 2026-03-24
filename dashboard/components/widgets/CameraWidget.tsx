"use client";

import { useState, useCallback, useEffect } from "react";
import { takeCameraSnapshot, getSnapshotUrl, getCameraStreamUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CameraWidgetProps {
  config: { entity_id: string };
}

export default function CameraWidget({ config }: CameraWidgetProps) {
  const [filename, setFilename] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ts, setTs] = useState(0);
  const [live, setLive] = useState(false);
  const [imgError, setImgError] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setImgError(false);
    try {
      const result = await takeCameraSnapshot(config.entity_id);
      setFilename(result.filename);
      setTs(Date.now());
    } catch {
      setImgError(true);
    } finally {
      setLoading(false);
    }
  }, [config.entity_id]);

  useEffect(() => {
    if (!live) refresh();
  }, [refresh, live]);

  const imgUrl = filename ? `${getSnapshotUrl(filename)}?t=${ts}` : null;
  const streamUrl = getCameraStreamUrl(config.entity_id);

  return (
    <div className="space-y-2">
      <div className="relative aspect-video rounded-lg bg-black/40 overflow-hidden group">
        {live ? (
          <img
            src={streamUrl}
            alt={config.entity_id}
            className="h-full w-full object-contain"
          />
        ) : imgUrl && !imgError ? (
          <img
            src={imgUrl}
            alt={config.entity_id}
            className="h-full w-full object-contain"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-neutral-500 text-xs">
            {loading ? "Loading..." : "No snapshot"}
          </div>
        )}
        {loading && !live && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/30">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-cyber-yellow border-t-transparent" />
          </div>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); setLive((v) => !v); }}
          className={cn(
            "absolute top-2 right-2 rounded px-2 py-0.5 text-[10px] font-mono transition-colors",
            live
              ? "bg-green-500/30 text-green-400"
              : "bg-white/10 text-neutral-500 opacity-0 group-hover:opacity-100",
          )}
        >
          {live ? "LIVE" : "Live"}
        </button>
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
