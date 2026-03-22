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
  executeSkill,
  getScenes,
  createScene as apiCreateScene,
  activateScene,
  deleteScene as apiDeleteScene,
  getEntities,
  getModels,
} from "@/lib/api";
import type { SkillDetail, SkillCreate, SkillUpdate, Scene, EntitiesResponse, ModelInfo } from "@/lib/types";
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
  model: null,
};

function SkillForm({
  initial,
  onSave,
  onCancel,
  saving,
  availableModels,
}: {
  initial: SkillCreate;
  onSave: (data: SkillCreate) => void;
  onCancel: () => void;
  saving: boolean;
  availableModels: ModelInfo[];
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

      {form.mode === "ai" && (
        <div>
          <label className="text-xs text-neutral-400">Model override (optional)</label>
          <select
            value={form.model || ""}
            onChange={(e) => set("model", e.target.value || null)}
            className="mt-1 w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white outline-none focus:border-cyber-yellow/50"
          >
            <option value="">System default</option>
            {availableModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.provider})
              </option>
            ))}
          </select>
          <p className="mt-1 text-[10px] text-neutral-600">
            Leave as default to use the system model, or pick a specific model for this skill.
          </p>
        </div>
      )}

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

function ScenesSection() {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [sceneName, setSceneName] = useState("");
  const [selectedEntities, setSelectedEntities] = useState<string[]>([]);
  const [entitySearch, setEntitySearch] = useState("");
  const [allEntities, setAllEntities] = useState<EntitiesResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [activatingId, setActivatingId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    getScenes()
      .then(setScenes)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const openCreate = async () => {
    setShowCreate(true);
    if (!allEntities) {
      try {
        const ents = await getEntities();
        setAllEntities(ents);
      } catch (err) {
        setError((err as Error).message);
      }
    }
  };

  const controllableDomains = ["light", "switch", "fan", "climate"];
  const flatEntities = allEntities
    ? Object.entries(allEntities.domains)
        .filter(([d]) => controllableDomains.includes(d))
        .flatMap(([, g]) => g.entities)
        .filter((e) =>
          !entitySearch ||
          e.friendly_name.toLowerCase().includes(entitySearch.toLowerCase()) ||
          e.entity_id.toLowerCase().includes(entitySearch.toLowerCase())
        )
    : [];

  const toggleEntitySelect = (eid: string) => {
    setSelectedEntities((prev) =>
      prev.includes(eid) ? prev.filter((e) => e !== eid) : [...prev, eid]
    );
  };

  const handleCreate = async () => {
    if (!sceneName || selectedEntities.length === 0) return;
    setSaving(true);
    try {
      await apiCreateScene({ name: sceneName, entity_ids: selectedEntities });
      setShowCreate(false);
      setSceneName("");
      setSelectedEntities([]);
      setEntitySearch("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleActivate = async (id: string) => {
    setActivatingId(id);
    try {
      await activateScene(id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActivatingId(null);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiDeleteScene(id);
      setConfirmDelete(null);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white font-mono">Scenes</h2>
          <p className="text-xs text-neutral-500">
            Snapshot and restore device states.
          </p>
        </div>
        {!showCreate && (
          <button
            onClick={openCreate}
            className="rounded-md bg-cyber-yellow/20 px-3 py-1.5 text-xs text-cyber-yellow hover:bg-cyber-yellow/30 transition-colors"
          >
            + Create Scene
          </button>
        )}
      </div>

      {error && (
        <div className="flex items-center justify-between rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-2">
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setError(null)} className="text-xs text-red-400/60 hover:text-red-400">dismiss</button>
        </div>
      )}

      {showCreate && (
        <div className="space-y-3 rounded-xl border border-white/10 bg-white/5 p-5">
          <h3 className="text-sm font-bold text-white font-mono">Create Scene</h3>
          <div>
            <label className="text-xs text-neutral-400">Scene Name</label>
            <input
              value={sceneName}
              onChange={(e) => setSceneName(e.target.value)}
              placeholder="Movie Night"
              className="mt-1 w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-neutral-600 outline-none focus:border-cyber-yellow/50"
            />
          </div>
          <div>
            <label className="text-xs text-neutral-400">
              Select entities to snapshot ({selectedEntities.length} selected)
            </label>
            <input
              value={entitySearch}
              onChange={(e) => setEntitySearch(e.target.value)}
              placeholder="Search entities..."
              className="mt-1 w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-neutral-600 outline-none focus:border-cyber-yellow/50"
            />
            <div className="mt-2 max-h-48 overflow-y-auto rounded-md border border-white/5 bg-white/[0.02]">
              {flatEntities.slice(0, 50).map((e) => (
                <button
                  key={e.entity_id}
                  onClick={() => toggleEntitySelect(e.entity_id)}
                  className={cn(
                    "flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition-colors hover:bg-white/5",
                    selectedEntities.includes(e.entity_id) ? "text-cyber-yellow bg-cyber-yellow/5" : "text-neutral-400"
                  )}
                >
                  <span className="truncate">{e.friendly_name}</span>
                  <span className="ml-2 shrink-0 font-mono text-neutral-600">{e.state}</span>
                </button>
              ))}
              {flatEntities.length === 0 && (
                <p className="p-3 text-xs text-neutral-600">Loading entities...</p>
              )}
            </div>
          </div>
          <p className="text-xs text-neutral-500">
            The current state of selected entities will be saved. Activating the scene restores them.
          </p>
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={() => { setShowCreate(false); setSelectedEntities([]); setEntitySearch(""); }}
              className="rounded-md px-3 py-1.5 text-xs text-neutral-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleCreate}
              disabled={saving || !sceneName || selectedEntities.length === 0}
              className="rounded-md bg-cyber-yellow/20 px-4 py-1.5 text-xs text-cyber-yellow hover:bg-cyber-yellow/30 disabled:opacity-40 transition-colors"
            >
              {saving ? "Saving..." : "Snapshot & Save"}
            </button>
          </div>
        </div>
      )}

      {loading && <p className="text-sm text-neutral-500 animate-pulse">Loading scenes...</p>}

      {!loading && scenes.length === 0 && !showCreate && (
        <div className="rounded-xl border border-dashed border-white/10 p-6 text-center">
          <p className="text-neutral-500 text-sm">No scenes saved yet.</p>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {scenes.map((scene) => (
          <MagicCard key={scene.id} className="p-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-sm font-semibold text-white font-mono">{scene.name}</h3>
                <p className="mt-1 text-xs text-neutral-500">{scene.entities.length} entities</p>
              </div>
              <button
                onClick={() => handleActivate(scene.id)}
                disabled={activatingId === scene.id}
                className="rounded-lg border border-cyber-yellow/20 bg-cyber-yellow/5 px-3 py-1.5 text-xs text-cyber-yellow hover:bg-cyber-yellow/15 transition-colors disabled:opacity-50"
              >
                {activatingId === scene.id ? "..." : "Activate"}
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {scene.entities.slice(0, 4).map((e) => (
                <span key={e.entity_id} className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-neutral-500 font-mono">
                  {e.entity_id.split(".")[1]}
                </span>
              ))}
              {scene.entities.length > 4 && (
                <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-neutral-500">
                  +{scene.entities.length - 4}
                </span>
              )}
            </div>
            <div className="mt-3 border-t border-white/5 pt-2">
              {confirmDelete === scene.id ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-red-400">Delete?</span>
                  <button onClick={() => handleDelete(scene.id)} className="text-xs text-red-400 hover:text-red-300 font-bold">Yes</button>
                  <button onClick={() => setConfirmDelete(null)} className="text-xs text-neutral-500 hover:text-neutral-300">No</button>
                </div>
              ) : (
                <button onClick={() => setConfirmDelete(scene.id)} className="text-xs text-neutral-500 hover:text-red-400 transition-colors">Delete</button>
              )}
            </div>
          </MagicCard>
        ))}
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
  const [runningSkill, setRunningSkill] = useState<string | null>(null);
  const [skillResult, setSkillResult] = useState<{ id: string; text: string; ms: number } | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);

  const refresh = useCallback(() => {
    setLoading(true);
    getSkills()
      .then(setSkills)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
    getModels()
      .then((data) => setAvailableModels(data.models))
      .catch(() => {});
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
      if ((data.model || null) !== (editingSkill.model || null)) updates.model = data.model || null;

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

  const handleRun = async (skill: SkillDetail) => {
    setRunningSkill(skill.id);
    setSkillResult(null);
    try {
      const res = await executeSkill(skill.id);
      setSkillResult({ id: skill.id, text: res.result, ms: res.duration_ms });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunningSkill(null);
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-5xl">
      <BlurFade delay={0}>
        <div>
          <h1 className="text-2xl font-bold text-white font-mono">Skills & Scenes</h1>
          <p className="text-sm text-neutral-400">
            Automations, routines, and device-state snapshots.
          </p>
        </div>
      </BlurFade>

      <BlurFade delay={0.05}>
        <ScenesSection />
      </BlurFade>

      <div className="border-t border-white/10 pt-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-white font-mono">Skills</h2>
          {!showForm && !editingSkill && (
            <button
              onClick={() => setShowForm(true)}
              className="rounded-md bg-cyber-yellow/20 px-3 py-1.5 text-xs text-cyber-yellow hover:bg-cyber-yellow/30 transition-colors"
            >
              + Create Skill
            </button>
          )}
        </div>
      </div>

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
            availableModels={availableModels}
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
              model: editingSkill.model,
            }}
            onSave={handleUpdate}
            onCancel={() => setEditingSkill(null)}
            saving={saving}
            availableModels={availableModels}
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
              <div className="mt-3 flex items-center gap-2 flex-wrap">
                <TriggerBadge type={skill.trigger?.type as string || "manual"} />
                <span className="text-xs text-neutral-500 font-mono">
                  {skill.mode}
                </span>
                {skill.model && (
                  <span className="inline-flex items-center rounded-full bg-cyan-500/10 px-2 py-0.5 text-[10px] font-mono text-cyan-400">
                    {skill.model}
                  </span>
                )}
              </div>
              {skill.ai_prompt && (
                <p className="mt-2 text-xs text-neutral-500 font-mono truncate">
                  {skill.ai_prompt}
                </p>
              )}
              {skillResult?.id === skill.id && (
                <div className="mt-3 rounded-lg border border-white/10 bg-white/5 p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-mono text-neutral-500">
                      Result ({(skillResult.ms / 1000).toFixed(1)}s)
                    </span>
                    <button
                      onClick={() => setSkillResult(null)}
                      className="text-xs text-neutral-500 hover:text-neutral-300"
                    >
                      dismiss
                    </button>
                  </div>
                  <p className="text-xs text-neutral-300 whitespace-pre-wrap max-h-48 overflow-y-auto">
                    {skillResult.text}
                  </p>
                </div>
              )}
              <div className="mt-3 flex items-center gap-2 border-t border-white/5 pt-3">
                <button
                  onClick={() => handleRun(skill)}
                  disabled={runningSkill === skill.id || !skill.active}
                  className="text-xs text-cyber-yellow hover:text-cyber-yellow/80 disabled:opacity-40 transition-colors"
                >
                  {runningSkill === skill.id ? "Running..." : "Run"}
                </button>
                <span className="text-white/10">|</span>
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
