"use client";

import { useEffect, useState, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import {
  getServerContainers,
  getServerTunnel,
  getServerBackups,
  addTunnelRoute,
  removeTunnelRoute,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ServerContainer, TunnelRoute, BackupStatus, BackupArchive } from "@/lib/types";

type TabId = "containers" | "tunnel" | "backups";

const TABS: { id: TabId; label: string }[] = [
  { id: "containers", label: "Containers" },
  { id: "tunnel", label: "Tunnel" },
  { id: "backups", label: "Backups" },
];

function StatusDot({ status, health }: { status: string; health: string | null }) {
  let color = "bg-neutral-500";
  let title = status;

  if (status === "running") {
    if (health === "healthy") {
      color = "bg-emerald-400";
      title = "healthy";
    } else if (health === "unhealthy") {
      color = "bg-red-400";
      title = "unhealthy";
    } else if (health === "starting") {
      color = "bg-amber-400 animate-pulse";
      title = "starting";
    } else {
      color = "bg-emerald-400/60";
      title = "running";
    }
  } else if (status === "exited" || status === "dead") {
    color = "bg-red-400";
  } else if (status === "paused") {
    color = "bg-amber-400";
  }

  return (
    <span title={title} className={cn("inline-block h-2 w-2 rounded-full shrink-0", color)} />
  );
}

function ContainerCard({
  container,
  publicUrl,
}: {
  container: ServerContainer;
  publicUrl: string | null;
}) {
  const hostPorts = Object.values(container.ports).filter(Boolean);
  const imageName = container.image.split("/").pop()?.split(":")[0] || container.image;

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 hover:bg-white/[0.05] transition-colors flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <StatusDot status={container.status} health={container.health} />
          <span className="text-sm font-medium text-neutral-200 truncate">
            {container.name}
          </span>
        </div>
        {container.uptime ? (
          <span className="text-[10px] text-neutral-500 font-mono shrink-0">{container.uptime}</span>
        ) : (
          <span className="text-[10px] text-red-400/60 font-mono shrink-0">{container.status}</span>
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[10px] text-neutral-500 font-mono truncate">{imageName}</span>
        {hostPorts.length > 0 && (
          <span className="text-[10px] text-neutral-500 font-mono">
            {hostPorts.map((p, i) => (
              <span key={p}>
                {i > 0 && " "}
                <a
                  href={`http://localhost:${p}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-neutral-400 hover:text-cyber-yellow transition-colors"
                >
                  :{p}
                </a>
              </span>
            ))}
          </span>
        )}
      </div>

      {publicUrl && (
        <a
          href={publicUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 self-start rounded-full border border-cyber-yellow/20 bg-cyber-yellow/10 px-2 py-0.5 text-[10px] text-cyber-yellow font-mono hover:bg-cyber-yellow/20 transition-colors"
        >
          {publicUrl.replace("https://", "")}
          <svg viewBox="0 0 16 16" fill="currentColor" className="h-2.5 w-2.5">
            <path d="M6.22 8.72a.75.75 0 0 0 1.06 1.06l5.22-5.22v1.69a.75.75 0 0 0 1.5 0v-3.5a.75.75 0 0 0-.75-.75h-3.5a.75.75 0 0 0 0 1.5h1.69L6.22 8.72Z" />
            <path d="M3.5 6.75c0-.69.56-1.25 1.25-1.25H7A.75.75 0 0 0 7 4H4.75A2.75 2.75 0 0 0 2 6.75v4.5A2.75 2.75 0 0 0 4.75 14h4.5A2.75 2.75 0 0 0 12 11.25V9a.75.75 0 0 0-1.5 0v2.25c0 .69-.56 1.25-1.25 1.25h-4.5c-.69 0-1.25-.56-1.25-1.25v-4.5Z" />
          </svg>
        </a>
      )}
    </div>
  );
}

function TunnelRouteCard({
  route,
  domain,
  onRemove,
  removing,
}: {
  route: TunnelRoute;
  domain: string;
  onRemove: (sub: string) => void;
  removing: string | null;
}) {
  const sub = route.hostname.replace(`.${domain}`, "");
  const isRemoving = removing === sub;

  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
      <div className="flex-1 min-w-0">
        <a
          href={`https://${route.hostname}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-cyber-yellow hover:underline font-mono"
        >
          {route.hostname}
        </a>
        <p className="text-[10px] text-neutral-500 font-mono mt-0.5 truncate">
          {route.service}
        </p>
      </div>
      <button
        onClick={() => onRemove(sub)}
        disabled={isRemoving}
        className={cn(
          "shrink-0 rounded-md px-2 py-0.5 text-[10px] font-mono transition-colors",
          isRemoving
            ? "text-neutral-600 cursor-not-allowed"
            : "text-red-400 hover:bg-red-400/10",
        )}
      >
        {isRemoving ? "..." : "Remove"}
      </button>
    </div>
  );
}

function AddRouteForm({
  domain,
  onAdd,
}: {
  domain: string;
  onAdd: (sub: string, svc: string) => Promise<void>;
}) {
  const [sub, setSub] = useState("");
  const [svc, setSvc] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  const handleAdd = async () => {
    if (!sub.trim() || !svc.trim()) return;
    setAdding(true);
    setError("");
    try {
      await onAdd(sub.trim(), svc.trim());
      setSub("");
      setSvc("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add route");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 space-y-2">
      <h3 className="text-xs font-medium text-neutral-300">Add Route</h3>
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="flex items-center gap-0 flex-1">
          <input
            value={sub}
            onChange={(e) => setSub(e.target.value)}
            placeholder="subdomain"
            className="w-full rounded-l-lg border border-r-0 border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/40 font-mono"
          />
          <span className="border border-l-0 border-white/10 bg-white/[0.02] px-2 py-1.5 text-xs text-neutral-500 font-mono rounded-r-lg whitespace-nowrap">
            .{domain}
          </span>
        </div>
        <input
          value={svc}
          onChange={(e) => setSvc(e.target.value)}
          placeholder="http://container:port"
          className="flex-1 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/40 font-mono"
        />
        <button
          onClick={handleAdd}
          disabled={adding || !sub.trim() || !svc.trim()}
          className="shrink-0 rounded-lg bg-cyber-yellow/20 px-3 py-1.5 text-xs font-mono text-cyber-yellow hover:bg-cyber-yellow/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {adding ? "Adding..." : "Add"}
        </button>
      </div>
      {error && <p className="text-[11px] text-red-400">{error}</p>}
    </div>
  );
}

function ArchiveRow({ archive }: { archive: BackupArchive }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-white/5 bg-white/[0.02] px-3 py-2">
      <span className="text-[11px] text-neutral-300 font-mono truncate">{archive.name}</span>
      <div className="flex items-center gap-3 shrink-0">
        <span className="text-[10px] text-neutral-500 font-mono">{archive.date}</span>
        <span className="text-[10px] text-neutral-400 font-mono">{archive.size}</span>
      </div>
    </div>
  );
}

function BackupCard({
  title,
  lastRun,
  size,
  archives,
}: {
  title: string;
  lastRun: string | null;
  size?: string | null;
  archives?: BackupArchive[];
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-neutral-200">{title}</h3>
        {size && (
          <span className="text-[11px] text-neutral-500 font-mono">{size}</span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "inline-block h-2 w-2 rounded-full shrink-0",
            lastRun ? "bg-emerald-400" : "bg-neutral-600",
          )}
        />
        <span className="text-xs text-neutral-400 font-mono">
          {lastRun ?? "Never run"}
        </span>
      </div>
      {archives && archives.length > 0 && (
        <div className="space-y-1 pt-1">
          {archives.map((a) => (
            <ArchiveRow key={a.name} archive={a} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function ServerPage() {
  const [containers, setContainers] = useState<ServerContainer[]>([]);
  const [routes, setRoutes] = useState<TunnelRoute[]>([]);
  const [domain, setDomain] = useState("");
  const [backups, setBackups] = useState<BackupStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [removing, setRemoving] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("containers");

  const fetchData = useCallback(async () => {
    try {
      const [cRes, tRes, bRes] = await Promise.all([
        getServerContainers(),
        getServerTunnel(),
        getServerBackups(),
      ]);
      setContainers(cRes.containers);
      setRoutes(tRes.routes);
      setDomain(tRes.domain);
      if ("last_updated" in bRes) {
        setBackups(bRes as BackupStatus);
      }
    } catch {
      /* silently fail on refresh */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const containerPublicUrls = new Map<string, string>();
  for (const r of routes) {
    const svcMatch = r.service.match(/:\/\/([^:/]+)/);
    const portMatch = r.service.match(/:(\d+)\s*$/);
    if (!svcMatch) continue;
    const svcHost = svcMatch[1];
    const svcPort = portMatch ? parseInt(portMatch[1]) : null;

    if (svcHost !== "host.docker.internal") {
      containerPublicUrls.set(svcHost, `https://${r.hostname}`);
    } else if (svcPort) {
      for (const c of containers) {
        if (Object.values(c.ports).includes(svcPort)) {
          containerPublicUrls.set(c.name, `https://${r.hostname}`);
          break;
        }
      }
    }
  }

  const handleRemoveRoute = async (sub: string) => {
    setRemoving(sub);
    try {
      await removeTunnelRoute(sub);
      await fetchData();
    } catch {
      /* ignore */
    } finally {
      setRemoving(null);
    }
  };

  const handleAddRoute = async (sub: string, svc: string) => {
    await addTunnelRoute(sub, svc);
    await fetchData();
  };

  const runningCount = containers.filter((c) => c.status === "running").length;
  const healthyCount = containers.filter((c) => c.health === "healthy").length;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6">
      <BlurFade delay={0}>
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white font-mono">
            Server
          </h1>
          <p className="text-xs sm:text-sm text-neutral-400">
            Docker containers, Cloudflare Tunnel routes, and backups
          </p>
        </div>
      </BlurFade>

      {/* Tab bar */}
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "rounded-full px-3 py-1.5 text-xs font-mono transition-colors whitespace-nowrap",
              activeTab === tab.id
                ? "bg-cyber-yellow/20 text-cyber-yellow"
                : "bg-white/5 text-neutral-400 hover:text-white",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20 text-neutral-500 animate-pulse">
          Loading server status...
        </div>
      ) : (
        <>
          {/* --- Containers Tab --- */}
          {activeTab === "containers" && (
            <BlurFade delay={0.05}>
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-neutral-300">
                    Containers
                  </h2>
                  <div className="flex items-center gap-3 text-[11px] font-mono text-neutral-500">
                    <span className="flex items-center gap-1">
                      <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      {healthyCount}
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400/60" />
                      {runningCount}
                    </span>
                    <span>{containers.length} total</span>
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
                  {containers.map((c) => (
                    <ContainerCard
                      key={c.name}
                      container={c}
                      publicUrl={containerPublicUrls.get(c.name) || null}
                    />
                  ))}
                </div>
              </div>
            </BlurFade>
          )}

          {/* --- Tunnel Tab --- */}
          {activeTab === "tunnel" && (
            <BlurFade delay={0.05}>
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-neutral-300">
                    Tunnel Routes
                  </h2>
                  <span className="text-[11px] font-mono text-neutral-500">
                    {routes.length} published
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
                  {routes.map((r) => (
                    <TunnelRouteCard
                      key={r.hostname}
                      route={r}
                      domain={domain}
                      onRemove={handleRemoveRoute}
                      removing={removing}
                    />
                  ))}
                </div>
                <div className="mt-3">
                  <AddRouteForm domain={domain} onAdd={handleAddRoute} />
                </div>
              </div>
            </BlurFade>
          )}

          {/* --- Backups Tab --- */}
          {activeTab === "backups" && (
            <BlurFade delay={0.05}>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-medium text-neutral-300">
                    Backup Status
                  </h2>
                  {backups && (
                    <span className="text-[10px] text-neutral-500 font-mono">
                      Updated {backups.last_updated.replace("T", " ")}
                    </span>
                  )}
                </div>

                {!backups ? (
                  <div className="rounded-lg border border-white/10 bg-white/[0.03] p-6 text-center">
                    <p className="text-sm text-neutral-500">
                      No backup data yet. Run{" "}
                      <code className="text-xs bg-white/5 px-1.5 py-0.5 rounded font-mono text-neutral-300">
                        homeserver backup
                      </code>{" "}
                      to generate status.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                    <BackupCard
                      title="Local Archives"
                      lastRun={backups.local.last_run}
                      archives={backups.local.archives}
                    />
                    <BackupCard
                      title="Google Drive Mirror"
                      lastRun={backups.gdrive_mirror.last_sync}
                      size={backups.gdrive_mirror.size}
                    />
                    <BackupCard
                      title="Google Drive Snapshots"
                      lastRun={
                        backups.gdrive_snapshots.snapshots.length > 0
                          ? backups.gdrive_snapshots.snapshots[0].date
                          : null
                      }
                      archives={backups.gdrive_snapshots.snapshots}
                    />
                  </div>
                )}

                <div className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
                  <p className="text-[11px] text-neutral-500 font-mono">
                    Daily rsync at 3:00 AM &middot; Weekly snapshot Sun 2:00 AM &middot; Trigger manually via{" "}
                    <code className="text-neutral-400">homeserver backup</code>
                  </p>
                </div>
              </div>
            </BlurFade>
          )}
        </>
      )}
    </div>
  );
}
