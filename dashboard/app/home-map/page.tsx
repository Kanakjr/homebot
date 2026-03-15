"use client";

import { useState, useEffect, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { useEntities } from "@/lib/hooks/useEntities";
import { getFloorplanConfig, toggleEntity, takeCameraSnapshot, getSnapshotUrl } from "@/lib/api";
import type { FloorplanConfig, EntityInfo } from "@/lib/types";
import FloorplanMap from "@/components/FloorplanMap";

export default function HomeMapPage() {
  const { data: entities, loading: entitiesLoading } = useEntities(10_000);
  const [floorplanConfig, setFloorplanConfig] = useState<FloorplanConfig | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [snapshotUrl, setSnapshotUrl] = useState<string | null>(null);

  useEffect(() => {
    getFloorplanConfig()
      .then(setFloorplanConfig)
      .catch((err) => setError(err.message))
      .finally(() => setConfigLoading(false));
  }, []);

  const flatEntities: Record<string, EntityInfo> = {};
  if (entities) {
    for (const group of Object.values(entities.domains)) {
      for (const e of group.entities) {
        flatEntities[e.entity_id] = e;
      }
    }
  }

  const handleDeviceClick = useCallback(
    async (svgId: string) => {
      if (!floorplanConfig) return;
      const mapping = floorplanConfig.devices.find((d) => d.svg_id === svgId);
      if (!mapping) return;

      const { entity_id, type } = mapping;

      if (type === "light" || type === "switch" || type === "fan") {
        try {
          await toggleEntity(entity_id);
        } catch (err) {
          setError((err as Error).message);
        }
      } else if (type === "camera") {
        try {
          const res = await takeCameraSnapshot(entity_id);
          setSnapshotUrl(getSnapshotUrl(res.filename));
          setSelectedDevice(svgId);
        } catch (err) {
          setError((err as Error).message);
        }
      } else {
        setSelectedDevice(svgId === selectedDevice ? null : svgId);
      }
    },
    [floorplanConfig, selectedDevice],
  );

  const loading = entitiesLoading || configLoading;

  const selectedMapping = floorplanConfig?.devices.find((d) => d.svg_id === selectedDevice);
  const selectedEntity = selectedMapping ? flatEntities[selectedMapping.entity_id] : null;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6">
      <BlurFade delay={0}>
        <div>
          <h1 className="text-2xl font-bold text-white font-mono">Home Map</h1>
          <p className="text-sm text-neutral-400">
            Interactive floor plan with live device states.
          </p>
        </div>
      </BlurFade>

      {error && (
        <div className="flex items-center justify-between rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-2">
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setError(null)} className="text-xs text-red-400/60 hover:text-red-400">dismiss</button>
        </div>
      )}

      {loading && (
        <p className="text-sm text-neutral-500 animate-pulse">Loading floor plan...</p>
      )}

      {!loading && floorplanConfig && (
        <BlurFade delay={0.1}>
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1 rounded-xl border border-white/10 bg-white/[0.02] p-4 overflow-auto">
              <FloorplanMap
                config={floorplanConfig}
                entities={flatEntities}
                onDeviceClick={handleDeviceClick}
                selectedDevice={selectedDevice}
              />
            </div>

            {selectedDevice && selectedMapping && (
              <div className="w-full lg:w-72 shrink-0 rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
                <h3 className="text-sm font-bold text-white font-mono">{selectedMapping.label}</h3>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-neutral-500">Entity</span>
                    <span className="text-xs text-neutral-300 font-mono">{selectedMapping.entity_id}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-neutral-500">Type</span>
                    <span className="text-xs text-neutral-300 font-mono">{selectedMapping.type}</span>
                  </div>
                  {selectedEntity && (
                    <>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-neutral-500">State</span>
                        <span className={`text-xs font-mono ${selectedEntity.state === "on" || selectedEntity.state === "home" ? "text-green-400" : "text-neutral-400"}`}>
                          {selectedEntity.state}
                        </span>
                      </div>
                      {selectedEntity.brightness != null && (
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-neutral-500">Brightness</span>
                          <span className="text-xs text-neutral-300">{Math.round((selectedEntity.brightness / 255) * 100)}%</span>
                        </div>
                      )}
                    </>
                  )}
                </div>

                {selectedMapping.type === "camera" && snapshotUrl && (
                  <div className="mt-3">
                    <img src={snapshotUrl} alt="Camera snapshot" className="w-full rounded-lg border border-white/10" />
                  </div>
                )}

                {(selectedMapping.type === "light" || selectedMapping.type === "switch" || selectedMapping.type === "fan") && (
                  <button
                    onClick={() => handleDeviceClick(selectedDevice)}
                    className="w-full rounded-lg border border-cyber-yellow/20 bg-cyber-yellow/5 px-3 py-2 text-xs text-cyber-yellow hover:bg-cyber-yellow/15 transition-colors"
                  >
                    Toggle {selectedMapping.label}
                  </button>
                )}

                <button
                  onClick={() => { setSelectedDevice(null); setSnapshotUrl(null); }}
                  className="w-full rounded-md px-3 py-1.5 text-xs text-neutral-500 hover:text-white transition-colors"
                >
                  Close
                </button>
              </div>
            )}
          </div>
        </BlurFade>
      )}
    </div>
  );
}
