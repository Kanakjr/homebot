"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import {
  getNotificationRules,
  updateNotificationRule,
  getDeviceAliases,
  setDeviceAlias,
  deleteDeviceAlias,
  getNetwork,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  NotificationRule,
  DeviceAlias,
  NetworkClient,
} from "@/lib/types";

/* ---------- toggle switch ---------- */

function Toggle({
  checked,
  onChange,
  color = "cyber-yellow",
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  color?: string;
}) {
  const bg = checked
    ? color === "emerald" ? "bg-emerald-500/80" : "bg-cyber-yellow/80"
    : "bg-white/10";
  return (
    <button
      onClick={() => onChange(!checked)}
      className={cn("relative h-6 w-11 shrink-0 rounded-full transition-colors", bg)}
    >
      <div
        className={cn(
          "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-[22px]" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

/* ---------- notification rule card ---------- */

function RuleCard({
  rule,
  onToggle,
}: {
  rule: NotificationRule;
  onToggle: (id: string, enabled: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-neutral-200">{rule.name}</p>
        <p className="text-[11px] text-neutral-500 font-mono mt-0.5">
          {rule.rule_type} | cooldown: {rule.cooldown_seconds}s
          {rule.config && Object.keys(rule.config).length > 0 && (
            <>
              {" | "}
              {Object.entries(rule.config)
                .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
                .join(", ")}
            </>
          )}
        </p>
      </div>
      <Toggle checked={rule.enabled} onChange={(v) => onToggle(rule.id, v)} />
    </div>
  );
}

/* ---------- alias row ---------- */

function AliasRow({
  alias,
  onDelete,
  onTogglePresence,
}: {
  alias: DeviceAlias;
  onDelete: (mac: string) => void;
  onTogglePresence: (mac: string, val: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5 gap-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-neutral-200">{alias.alias}</p>
        <p className="text-[11px] text-neutral-500 font-mono mt-0.5">
          {alias.mac}
          {alias.device_type && <> | {alias.device_type}</>}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={() => onTogglePresence(alias.mac, !alias.is_presence)}
          title={alias.is_presence ? "Tracking presence" : "Not tracking presence"}
          className={cn(
            "rounded-md px-2 py-1 text-[11px] font-mono transition-colors border",
            alias.is_presence
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
              : "border-white/5 bg-white/[0.02] text-neutral-500 hover:text-neutral-300",
          )}
        >
          {alias.is_presence ? "presence" : "no presence"}
        </button>
        <button
          onClick={() => onDelete(alias.mac)}
          className="rounded-md px-2 py-1 text-xs text-red-400 hover:bg-red-400/10 transition-colors"
        >
          Remove
        </button>
      </div>
    </div>
  );
}

/* ---------- client dropdown ---------- */

function ClientDropdown({
  clients,
  aliasedMacs,
  onSelect,
}: {
  clients: NetworkClient[];
  aliasedMacs: Set<string>;
  onSelect: (client: NetworkClient) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = clients.filter((c) => {
    const q = search.toLowerCase();
    return (
      c.friendly_name.toLowerCase().includes(q) ||
      c.mac.toLowerCase().includes(q) ||
      c.ip.toLowerCase().includes(q)
    );
  });

  return (
    <div ref={ref} className="relative flex-1">
      <input
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="Search or select a client..."
        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/40"
      />
      {open && (
        <div className="absolute z-50 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-white/10 bg-neutral-900 shadow-lg">
          {filtered.length === 0 ? (
            <p className="px-3 py-2 text-xs text-neutral-500">No clients found</p>
          ) : (
            filtered.map((c) => {
              const isAliased = aliasedMacs.has(c.mac.toUpperCase());
              return (
                <button
                  key={c.mac}
                  onClick={() => {
                    onSelect(c);
                    setSearch("");
                    setOpen(false);
                  }}
                  className={cn(
                    "flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-white/5 transition-colors",
                    isAliased ? "opacity-50" : "",
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-neutral-200 truncate">{c.friendly_name}</p>
                    <p className="text-[10px] text-neutral-500 font-mono">
                      {c.mac} | {c.ip} | {c.connection_type}
                      {c.deco_device && <> | {c.deco_device}</>}
                    </p>
                  </div>
                  {isAliased && (
                    <span className="ml-2 shrink-0 text-[10px] text-neutral-500">aliased</span>
                  )}
                  <span
                    className={cn(
                      "ml-2 h-2 w-2 shrink-0 rounded-full",
                      c.state === "home" ? "bg-emerald-400" : "bg-neutral-600",
                    )}
                  />
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- presence summary ---------- */

function PresenceSummary({ aliases }: { aliases: DeviceAlias[] }) {
  const tracked = aliases.filter((a) => a.is_presence);
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-neutral-200">
            Presence Tracking
          </h3>
          <p className="mt-1 text-[11px] text-neutral-500 leading-relaxed max-w-md">
            Devices marked as &quot;presence&quot; trigger automations when they connect or disconnect
            from the Deco mesh -- Welcome Home and Left Home notifications use this
            to detect arrivals and departures.
          </p>
        </div>
      </div>
      {tracked.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {tracked.map((a) => (
            <span
              key={a.mac}
              className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-400 font-mono"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              {a.alias}
            </span>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-xs text-neutral-500">
          No presence devices configured. Toggle &quot;presence&quot; on a device alias above.
        </p>
      )}
    </div>
  );
}

/* ---------- main page ---------- */

export default function SettingsPage() {
  const [rules, setRules] = useState<NotificationRule[]>([]);
  const [aliases, setAliases] = useState<DeviceAlias[]>([]);
  const [clients, setClients] = useState<NetworkClient[]>([]);
  const [loading, setLoading] = useState(true);

  const [selectedClient, setSelectedClient] = useState<NetworkClient | null>(null);
  const [newAlias, setNewAlias] = useState("");
  const [newType, setNewType] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [rulesRes, aliasesRes, networkRes] = await Promise.all([
        getNotificationRules(),
        getDeviceAliases(),
        getNetwork(1),
      ]);
      setRules(rulesRes.rules);
      setAliases(aliasesRes.aliases);
      setClients(networkRes.clients);
    } catch {
      /* silently fail */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleToggleRule = async (id: string, enabled: boolean) => {
    setRules((prev) => prev.map((r) => (r.id === id ? { ...r, enabled } : r)));
    await updateNotificationRule(id, { enabled });
  };

  const handleSelectClient = (client: NetworkClient) => {
    setSelectedClient(client);
    setNewAlias(client.friendly_name);
    setNewType(client.connection_type === "wireless" ? "wireless" : "wired");
  };

  const handleAddAlias = async () => {
    if (!selectedClient || !newAlias.trim()) return;
    await setDeviceAlias(
      selectedClient.mac,
      newAlias.trim(),
      newType.trim(),
      "",
      false,
    );
    setSelectedClient(null);
    setNewAlias("");
    setNewType("");
    fetchData();
  };

  const handleDeleteAlias = async (mac: string) => {
    setAliases((prev) => prev.filter((a) => a.mac !== mac));
    await deleteDeviceAlias(mac);
  };

  const handleTogglePresence = async (mac: string, val: boolean) => {
    setAliases((prev) =>
      prev.map((a) => (a.mac === mac ? { ...a, is_presence: val } : a)),
    );
    const existing = aliases.find((a) => a.mac === mac);
    if (existing) {
      await setDeviceAlias(
        mac,
        existing.alias,
        existing.device_type,
        existing.icon,
        val,
      );
    }
  };

  const aliasedMacs = new Set(aliases.map((a) => a.mac.toUpperCase()));

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-8 max-w-3xl">
      <BlurFade delay={0}>
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white font-mono">
            Settings
          </h1>
          <p className="text-xs sm:text-sm text-neutral-400">
            Notifications, device aliases, and presence tracking
          </p>
        </div>
      </BlurFade>

      {loading && !rules.length ? (
        <div className="flex items-center justify-center py-20 text-neutral-500 animate-pulse">
          Loading settings...
        </div>
      ) : (
        <>
          {/* --- Notification Rules --- */}
          <BlurFade delay={0.05}>
            <div>
              <h2 className="mb-3 text-sm font-medium text-neutral-300">
                Notification Rules
              </h2>
              <div className="space-y-2">
                {rules.map((rule) => (
                  <RuleCard
                    key={rule.id}
                    rule={rule}
                    onToggle={handleToggleRule}
                  />
                ))}
                {rules.length === 0 && (
                  <p className="text-sm text-neutral-500">
                    No notification rules configured.
                  </p>
                )}
              </div>
            </div>
          </BlurFade>

          {/* --- Device Aliases --- */}
          <BlurFade delay={0.1}>
            <div>
              <h2 className="mb-1 text-sm font-medium text-neutral-300">
                Device Aliases
              </h2>
              <p className="mb-3 text-[11px] text-neutral-500">
                Give friendly names to Deco network clients.
                Select from connected devices or search by name, MAC, or IP.
              </p>

              <div className="space-y-2">
                {aliases.map((alias) => (
                  <AliasRow
                    key={alias.mac}
                    alias={alias}
                    onDelete={handleDeleteAlias}
                    onTogglePresence={handleTogglePresence}
                  />
                ))}
              </div>

              {/* add new alias */}
              <div className="mt-3 space-y-2">
                <div className="flex flex-col gap-2 sm:flex-row">
                  <ClientDropdown
                    clients={clients}
                    aliasedMacs={aliasedMacs}
                    onSelect={handleSelectClient}
                  />
                  {selectedClient && (
                    <span className="self-center text-[11px] text-neutral-500 font-mono shrink-0">
                      {selectedClient.mac}
                    </span>
                  )}
                </div>
                {selectedClient && (
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <input
                      value={newAlias}
                      onChange={(e) => setNewAlias(e.target.value)}
                      placeholder="Friendly name"
                      className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/40"
                    />
                    <input
                      value={newType}
                      onChange={(e) => setNewType(e.target.value)}
                      placeholder="Type (optional)"
                      className="w-36 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/40"
                    />
                    <button
                      onClick={handleAddAlias}
                      className="shrink-0 rounded-lg bg-cyber-yellow/20 px-4 py-2 text-sm font-mono text-cyber-yellow hover:bg-cyber-yellow/30 transition-colors"
                    >
                      Add
                    </button>
                    <button
                      onClick={() => {
                        setSelectedClient(null);
                        setNewAlias("");
                        setNewType("");
                      }}
                      className="shrink-0 rounded-lg border border-white/10 px-3 py-2 text-sm text-neutral-400 hover:text-white hover:bg-white/5 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            </div>
          </BlurFade>

          {/* --- Presence Tracking --- */}
          <BlurFade delay={0.15}>
            <PresenceSummary aliases={aliases} />
          </BlurFade>
        </>
      )}
    </div>
  );
}
