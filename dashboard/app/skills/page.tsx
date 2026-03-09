"use client";

import { useEffect, useState, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import MagicCard from "@/components/magicui/magic-card";
import {
  getSkills,
  createSkill,
  updateSkill,
  deleteSkill,
  toggleSkill,
} from "@/lib/api";
import type { SkillDetail, SkillCreate, SkillUpdate } from "@/lib/types";
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
        colors[type] || "bg-white/10 text-neutral-400",
      )}
    >
      {type}
    </span>
  );
}

const EMPTY_FORM: SkillCreate = {
  id: "",
  name: "",
  description: "",
  trigger: { type: "manual" },
  mode: "static",
  ai_prompt: "",
  actions: [],
  notify: false,
};

function SkillForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial: SkillCreate;
  onSave: (data: SkillCreate) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<SkillCreate>(initial);
  const isNew = !initial.id;

  const set = (key: keyof SkillCreate, value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <div className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-5">
      <h3 className="text-sm font-bold text-white font-mono">
        {isNew ? "Create Skill" : "Edit Skill"}
      </h3>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="text-xs text-neutral-400">ID (slug)</label>
          <input
            value={form.id}
            onChange={(e) => set("id", e.target.value.replace(/\s+/g, "_").toLowerCase())}
            disabled={!isNew}
            placeholder="my_skill"
            className="mt-1 w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-neutral-600 outline-none focus:border-cyber-yellow/50 disabled:opacity-50"
          />
        </div>
        <div>
          <label className="text-xs text-neutral-400">Name</label>
          <input
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
            placeholder="My Skill"
            className="mt-1 w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-neutral-600 outline-none focus:border-cyber-yellow/50"
          />
        </div>
      </div>

      <div>
        <label className="text-xs text-neutral-400">Description</label>
        <textarea
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
          rows={2}
          placeholder="What does this skill do?"
          className="mt-1 w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-neutral-600 outline-none focus:border-cyber-yellow/50 resize-none"
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label className="text-xs text-neutral-400">Trigger type</label>
          <select
            value={(form.trigger as Record<string, string>)?.type || "manual"}
            onChange={(e) => set("trigger", { type: e.target.value })}
            className="mt-1 w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white outline-none focus:border-cyber-yellow/50"
          >
            <option value="manual">manual</option>
            <option value="schedule">schedule</option>
            <option value="state_change">state_change</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-neutral-400">Mode</label>
          <select
            value={form.mode}
            onChange={(e) => set("mode", e.target.value)}
            className="mt-1 w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white outline-none focus:border-cyber-yellow/50"
          >
            <option value="static">static</option>
            <option value="ai">ai</option>
          </select>
        </div>
        <div className="flex items-end">
          <label className="flex items-center gap-2 text-xs text-neutral-400 cursor-pointer pb-1.5">
            <input
              type="checkbox"
              checked={form.notify}
              onChange={(e) => set("notify", e.target.checked)}
              className="accent-cyber-yellow"
            />
            Notify on trigger
          </label>
        </div>
      </div>

      <div>
        <label className="text-xs text-neutral-400">AI Prompt (for AI mode)</label>
        <textarea
          value={form.ai_prompt}
          onChange={(e) => set("ai_prompt", e.target.value)}
          rows={3}
          placeholder="Instructions for the AI when this skill is triggered..."
          className="mt-1 w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-neutral-600 outline-none focus:border-cyber-yellow/50 resize-none font-mono text-xs"
        />
      </div>

      <div className="flex items-center justify-end gap-2">
        <button
          onClick={onCancel}
          className="rounded-md px-3 py-1.5 text-xs text-neutral-400 hover:text-white transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={() => onSave(form)}
          disabled={saving || !form.id || !form.name}
          className="rounded-md bg-cyber-yellow/20 px-4 py-1.5 text-xs text-cyber-yellow hover:bg-cyber-yellow/30 disabled:opacity-40 transition-colors"
        >
          {saving ? "Saving..." : isNew ? "Create" : "Update"}
        </button>
      </div>
    </div>
  );
}

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingSkill, setEditingSkill] = useState<SkillDetail | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    getSkills()
      .then(setSkills)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCreate = async (data: SkillCreate) => {
    setSaving(true);
    try {
      await createSkill(data);
      setShowForm(false);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async (data: SkillCreate) => {
    if (!editingSkill) return;
    setSaving(true);
    try {
      const updates: SkillUpdate = {};
      if (data.name !== editingSkill.name) updates.name = data.name;
      if (data.description !== editingSkill.description) updates.description = data.description;
      if (JSON.stringify(data.trigger) !== JSON.stringify(editingSkill.trigger))
        updates.trigger = data.trigger;
      if (data.mode !== editingSkill.mode) updates.mode = data.mode;
      if (data.ai_prompt !== editingSkill.ai_prompt) updates.ai_prompt = data.ai_prompt;
      if (data.notify !== editingSkill.notify) updates.notify = data.notify;

      if (Object.keys(updates).length > 0) {
        await updateSkill(editingSkill.id, updates);
      }
      setEditingSkill(null);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteSkill(id);
      setConfirmDelete(null);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const handleToggle = async (skill: SkillDetail) => {
    try {
      await toggleSkill(skill.id, !skill.active);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-5xl">
      <BlurFade delay={0}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white font-mono">Skills</h1>
            <p className="text-sm text-neutral-400">
              Learned routines and automations.
            </p>
          </div>
          {!showForm && !editingSkill && (
            <button
              onClick={() => setShowForm(true)}
              className="rounded-md bg-cyber-yellow/20 px-3 py-1.5 text-xs text-cyber-yellow hover:bg-cyber-yellow/30 transition-colors"
            >
              + Create Skill
            </button>
          )}
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

      {showForm && (
        <BlurFade delay={0.05}>
          <SkillForm
            initial={EMPTY_FORM}
            onSave={handleCreate}
            onCancel={() => setShowForm(false)}
            saving={saving}
          />
        </BlurFade>
      )}

      {editingSkill && (
        <BlurFade delay={0.05}>
          <SkillForm
            initial={{
              id: editingSkill.id,
              name: editingSkill.name,
              description: editingSkill.description,
              trigger: editingSkill.trigger,
              mode: editingSkill.mode,
              ai_prompt: editingSkill.ai_prompt,
              actions: editingSkill.actions,
              notify: editingSkill.notify,
            }}
            onSave={handleUpdate}
            onCancel={() => setEditingSkill(null)}
            saving={saving}
          />
        </BlurFade>
      )}

      {loading && (
        <p className="text-sm text-neutral-500 animate-pulse">
          Loading skills...
        </p>
      )}

      {!loading && skills.length === 0 && !showForm && (
        <BlurFade delay={0.1}>
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center">
            <p className="text-neutral-400">No skills learned yet.</p>
            <p className="mt-2 text-sm text-neutral-500">
              Create one above, or teach HomeBotAI a routine via the Chat page.
            </p>
          </div>
        </BlurFade>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {skills.map((skill, i) => (
          <BlurFade key={skill.id} delay={0.1 + i * 0.05}>
            <MagicCard className="p-5">
              <div className="flex items-start justify-between">
                <h3 className="text-base font-semibold text-white font-mono">
                  {skill.name}
                </h3>
                <button
                  onClick={() => handleToggle(skill)}
                  className={cn(
                    "relative h-5 w-9 shrink-0 rounded-full transition-colors",
                    skill.active ? "bg-green-500/30" : "bg-white/10",
                  )}
                  aria-label={skill.active ? "Disable" : "Enable"}
                >
                  <span
                    className={cn(
                      "absolute top-0.5 h-4 w-4 rounded-full transition-all",
                      skill.active
                        ? "left-[18px] bg-green-400"
                        : "left-0.5 bg-neutral-500",
                    )}
                  />
                </button>
              </div>
              <p className="mt-2 text-sm text-neutral-400">
                {skill.description}
              </p>
              <div className="mt-3 flex items-center gap-2">
                <TriggerBadge type={skill.trigger?.type as string || "manual"} />
                <span className="text-xs text-neutral-500 font-mono">
                  {skill.mode}
                </span>
              </div>
              {skill.ai_prompt && (
                <p className="mt-2 text-xs text-neutral-500 font-mono truncate">
                  {skill.ai_prompt}
                </p>
              )}
              <div className="mt-3 flex items-center gap-2 border-t border-white/5 pt-3">
                <button
                  onClick={() => {
                    setShowForm(false);
                    setEditingSkill(skill);
                  }}
                  className="text-xs text-neutral-400 hover:text-cyber-yellow transition-colors"
                >
                  Edit
                </button>
                {confirmDelete === skill.id ? (
                  <>
                    <span className="text-xs text-red-400">Delete?</span>
                    <button
                      onClick={() => handleDelete(skill.id)}
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
                  </>
                ) : (
                  <button
                    onClick={() => setConfirmDelete(skill.id)}
                    className="text-xs text-neutral-500 hover:text-red-400 transition-colors"
                  >
                    Delete
                  </button>
                )}
              </div>
            </MagicCard>
          </BlurFade>
        ))}
      </div>
    </div>
  );
}
