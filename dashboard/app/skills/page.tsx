"use client";

import { useEffect, useState } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import MagicCard from "@/components/magicui/magic-card";
import { getSkills } from "@/lib/api";
import type { SkillInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

function TriggerBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    manual: "bg-blue-500/10 text-blue-400",
    schedule: "bg-purple-500/10 text-purple-400",
    state_change: "bg-orange-500/10 text-orange-400",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-mono",
        colors[type] || "bg-white/10 text-neutral-400"
      )}
    >
      {type}
    </span>
  );
}

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSkills()
      .then(setSkills)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 lg:p-8 space-y-6 max-w-5xl">
      <BlurFade delay={0}>
        <div>
          <h1 className="text-2xl font-bold text-white font-mono">Skills</h1>
          <p className="text-sm text-neutral-400">
            Learned routines and automations. Teach new skills via the chat.
          </p>
        </div>
      </BlurFade>

      {loading && (
        <p className="text-sm text-neutral-500 animate-pulse">
          Loading skills...
        </p>
      )}
      {error && <p className="text-sm text-red-400">Error: {error}</p>}

      {!loading && skills.length === 0 && (
        <BlurFade delay={0.1}>
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center">
            <p className="text-neutral-400">No skills learned yet.</p>
            <p className="mt-2 text-sm text-neutral-500">
              Go to the Chat page and teach HomeBotAI a routine, e.g. &quot;When
              I say goodnight, turn off all lights and set the fan to
              auto.&quot;
            </p>
          </div>
        </BlurFade>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {skills.map((skill, i) => (
          <BlurFade key={skill.name} delay={0.1 + i * 0.05}>
            <MagicCard className="p-5">
              <div className="flex items-start justify-between">
                <h3 className="text-base font-semibold text-white font-mono">
                  {skill.name}
                </h3>
                <span
                  className={cn(
                    "text-xs font-mono",
                    skill.active ? "text-green-400" : "text-neutral-500"
                  )}
                >
                  {skill.active ? "active" : "disabled"}
                </span>
              </div>
              <p className="mt-2 text-sm text-neutral-400">
                {skill.description}
              </p>
              <div className="mt-3 flex items-center gap-2">
                <TriggerBadge type={skill.trigger_type} />
                <span className="text-xs text-neutral-500 font-mono">
                  {skill.mode}
                </span>
              </div>
            </MagicCard>
          </BlurFade>
        ))}
      </div>
    </div>
  );
}
