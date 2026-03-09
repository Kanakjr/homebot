"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { useEntities } from "@/lib/hooks/useEntities";
import { takeCameraSnapshot, getSnapshotUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CameraState {
  entityId: string;
  friendlyName: string;
  state: string;
  filename: string | null;
  loading: boolean;
  lastRefresh: number;
}

function CameraCard({ cam, onRefresh }: { cam: CameraState; onRefresh: () => void }) {
  const imgUrl = cam.filename
    ? `${getSnapshotUrl(cam.filename)}?t=${cam.lastRefresh}`
    : null;

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 overflow-hidden">
      <div className="relative aspect-video bg-black/50">
        {imgUrl ? (
          <img
            src={imgUrl}
            alt={cam.friendlyName}
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-neutral-500 text-sm">
            {cam.loading ? "Fetching snapshot..." : "No snapshot available"}
          </div>
        )}
        {cam.loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyber-yellow border-t-transparent" />
          </div>
        )}
      </div>
      <div className="flex items-center justify-between px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-neutral-200 truncate">
            {cam.friendlyName}
          </p>
          <p className="text-xs text-neutral-500 font-mono truncate">
            {cam.entityId}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span
            className={cn(
              "text-xs font-mono",
              cam.state === "streaming" || cam.state === "idle"
                ? "text-green-400"
                : "text-red-400/50",
            )}
          >
            {cam.state}
          </span>
          <button
            onClick={onRefresh}
            disabled={cam.loading}
            className="rounded-md bg-cyber-yellow/20 px-2.5 py-1 text-xs text-cyber-yellow hover:bg-cyber-yellow/30 disabled:opacity-50 transition-colors"
          >
            Snapshot
          </button>
        </div>
      </div>
    </div>
  );
}

export default function CamerasPage() {
  const { data, loading: entitiesLoading } = useEntities(60_000);
  const [cameras, setCameras] = useState<CameraState[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!data?.domains?.camera) return;
    setCameras((prev) => {
      const existing = new Map(prev.map((c) => [c.entityId, c]));
      return data.domains.camera.entities.map((e) => {
        const ex = existing.get(e.entity_id);
        return {
          entityId: e.entity_id,
          friendlyName: e.friendly_name,
          state: e.state,
          filename: ex?.filename ?? null,
          loading: ex?.loading ?? false,
          lastRefresh: ex?.lastRefresh ?? 0,
        };
      });
    });
  }, [data]);

  const refreshCamera = useCallback(async (entityId: string) => {
    setCameras((prev) =>
      prev.map((c) => (c.entityId === entityId ? { ...c, loading: true } : c)),
    );
    try {
      const result = await takeCameraSnapshot(entityId);
      setCameras((prev) =>
        prev.map((c) =>
          c.entityId === entityId
            ? { ...c, filename: result.filename, loading: false, lastRefresh: Date.now() }
            : c,
        ),
      );
    } catch {
      setCameras((prev) =>
        prev.map((c) => (c.entityId === entityId ? { ...c, loading: false } : c)),
      );
    }
  }, []);

  const refreshAll = useCallback(() => {
    cameras.forEach((c) => {
      if (c.state !== "unavailable") refreshCamera(c.entityId);
    });
  }, [cameras, refreshCamera]);

  useEffect(() => {
    if (cameras.length > 0 && cameras.every((c) => !c.filename && !c.loading)) {
      refreshAll();
    }
    // only on initial camera list load
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameras.length]);

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(refreshAll, 15_000);
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh, refreshAll]);

  return (
    <div className="p-6 lg:p-8 space-y-6 max-w-5xl">
      <BlurFade delay={0}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white font-mono">Cameras</h1>
            <p className="text-sm text-neutral-400">
              {cameras.length === 0 && !entitiesLoading
                ? "No cameras found"
                : `${cameras.length} camera${cameras.length !== 1 ? "s" : ""}`}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-neutral-400 cursor-pointer">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="accent-cyber-yellow"
              />
              Auto-refresh (15s)
            </label>
            <button
              onClick={refreshAll}
              className="rounded-md bg-cyber-yellow/20 px-3 py-1.5 text-xs text-cyber-yellow hover:bg-cyber-yellow/30 transition-colors"
            >
              Refresh All
            </button>
          </div>
        </div>
      </BlurFade>

      {entitiesLoading && cameras.length === 0 && (
        <p className="text-sm text-neutral-500 animate-pulse">Loading...</p>
      )}

      <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
        {cameras.map((cam, i) => (
          <BlurFade key={cam.entityId} delay={0.1 + i * 0.05}>
            <CameraCard
              cam={cam}
              onRefresh={() => refreshCamera(cam.entityId)}
            />
          </BlurFade>
        ))}
      </div>
    </div>
  );
}
