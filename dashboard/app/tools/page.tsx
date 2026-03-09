"use client";

import { useEffect, useState } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { getTools } from "@/lib/api";
import type { ToolInfo } from "@/lib/types";

const TOOL_CATEGORIES: Record<string, string[]> = {
  "Home Assistant": [
    "ha_call_service",
    "ha_get_camera_snapshot",
    "ha_trigger_automation",
    "ha_fire_event",
  ],
  Skills: [
    "create_skill",
    "execute_skill",
    "list_skills",
    "update_skill",
    "delete_skill",
    "toggle_skill",
    "get_event_log",
  ],
  Memory: ["remember", "recall"],
  n8n: [
    "n8n_list_workflows",
    "n8n_get_workflow",
    "n8n_create_workflow",
    "n8n_execute_workflow",
    "n8n_toggle_workflow",
  ],
  Sonarr: ["sonarr_search", "sonarr_add_series", "sonarr_list_series", "sonarr_upcoming"],
  Transmission: [
    "transmission_list",
    "transmission_add",
    "transmission_remove",
    "transmission_pause_resume",
  ],
  Jellyseerr: ["jellyseerr_search", "jellyseerr_request"],
};

function categorize(tool: ToolInfo): string {
  for (const [cat, names] of Object.entries(TOOL_CATEGORIES)) {
    if (names.includes(tool.name)) return cat;
  }
  return "Other";
}

export default function ToolsPage() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTools()
      .then(setTools)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const grouped = tools.reduce(
    (acc, tool) => {
      const cat = categorize(tool);
      (acc[cat] ??= []).push(tool);
      return acc;
    },
    {} as Record<string, ToolInfo[]>
  );

  const categoryOrder = [
    "Home Assistant",
    "Skills",
    "Memory",
    "n8n",
    "Sonarr",
    "Transmission",
    "Jellyseerr",
    "Other",
  ];

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-5xl">
      <BlurFade delay={0}>
        <div>
          <h1 className="text-2xl font-bold text-white font-mono">Tools</h1>
          <p className="text-sm text-neutral-400">
            {tools.length > 0
              ? `${tools.length} tools registered`
              : "Loading..."}
          </p>
        </div>
      </BlurFade>

      {loading && (
        <p className="text-sm text-neutral-500 animate-pulse">
          Loading tools...
        </p>
      )}
      {error && <p className="text-sm text-red-400">Error: {error}</p>}

      {categoryOrder
        .filter((cat) => grouped[cat]?.length)
        .map((cat, i) => (
          <BlurFade key={cat} delay={0.1 + i * 0.05}>
            <div>
              <h2 className="text-sm font-mono text-neutral-400 mb-3">
                {cat}
              </h2>
              <div className="space-y-2">
                {grouped[cat].map((tool) => (
                  <div
                    key={tool.name}
                    className="flex items-start gap-4 rounded-lg border border-white/10 bg-white/5 p-4"
                  >
                    <code className="shrink-0 rounded bg-white/10 px-2 py-1 text-xs text-cyber-yellow font-mono">
                      {tool.name}
                    </code>
                    <p className="text-sm text-neutral-300">
                      {tool.description}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </BlurFade>
        ))}
    </div>
  );
}
