"use client";

import { useCallback, useState } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  rectSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { DashboardConfig, DashboardWidget, EntityInfo, EntitiesResponse } from "@/lib/types";
import {
  StatWidget,
  ToggleGroupWidget,
  SensorGridWidget,
  CameraWidget,
  QuickActionsWidget,
  WeatherWidget,
  SceneButtonsWidget,
  GaugeWidget,
  WeatherCardWidget,
  LightControlWidget,
  ClimateControlWidget,
  PrinterWidget,
  AirPurifierWidget,
  RoomEnvironmentWidget,
  HealthWidget,
  PresenceWidget,
  PowerChartWidget,
  BandwidthChartWidget,
  SmartPlugWidget,
} from "./widgets";
import { GenUIRenderer } from "@/lib/generative-ui";
import type { EntityLookup } from "@/lib/generative-ui";
import { BlurFade } from "./magicui/blur-fade";
import { cn } from "@/lib/utils";

interface DashboardRendererProps {
  config: DashboardConfig;
  entitiesData: EntitiesResponse | null;
  onRefresh?: () => void;
  editMode?: boolean;
  onReorder?: (widgetIds: string[]) => void;
  onDelete?: (widgetId: string) => void;
  onEditWidget?: (widgetId: string) => void;
}

function flattenEntities(data: EntitiesResponse | null): EntityInfo[] {
  if (!data) return [];
  return Object.values(data.domains).flatMap((d) => d.entities);
}

const SIZE_CLASSES: Record<string, string> = {
  sm: "col-span-1",
  md: "col-span-1 sm:col-span-2",
  lg: "col-span-1 sm:col-span-2 lg:col-span-3",
  full: "col-span-1 sm:col-span-2 lg:col-span-3 xl:col-span-4",
};

function SortableWidgetShell({
  widget,
  children,
  index,
  editMode,
  onDelete,
  onEditWidget,
}: {
  widget: DashboardWidget;
  children: React.ReactNode;
  index: number;
  editMode?: boolean;
  onDelete?: (id: string) => void;
  onEditWidget?: (id: string) => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: widget.id, disabled: !editMode });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 50 : undefined,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(SIZE_CLASSES[widget.size] ?? SIZE_CLASSES.sm)}
    >
      <BlurFade delay={editMode ? 0 : 0.05 + index * 0.04}>
        <div
          className={cn(
            "relative rounded-xl border bg-white/[0.03] p-4 backdrop-blur-sm transition-all h-full",
            editMode
              ? "border-dashed border-white/20"
              : "border-white/10 hover:border-white/15",
            isDragging && "opacity-80 shadow-xl shadow-cyber-yellow/10 scale-[1.02]",
          )}
        >
          {editMode && (
            <div className="absolute -top-px left-0 right-0 flex items-center justify-between rounded-t-xl bg-white/[0.06] px-3 py-1.5 border-b border-white/10 z-10">
              <button
                {...attributes}
                {...listeners}
                className="cursor-grab active:cursor-grabbing rounded p-0.5 text-neutral-500 hover:text-white transition-colors"
                title="Drag to reorder"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
                  <circle cx="9" cy="5" r="1.5" />
                  <circle cx="15" cy="5" r="1.5" />
                  <circle cx="9" cy="12" r="1.5" />
                  <circle cx="15" cy="12" r="1.5" />
                  <circle cx="9" cy="19" r="1.5" />
                  <circle cx="15" cy="19" r="1.5" />
                </svg>
              </button>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => onEditWidget?.(widget.id)}
                  className="rounded p-1 text-neutral-500 hover:text-cyber-yellow transition-colors"
                  title="Edit widget"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>
                {confirmDelete ? (
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => { onDelete?.(widget.id); setConfirmDelete(false); }}
                      className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
                    >
                      Delete
                    </button>
                    <button
                      onClick={() => setConfirmDelete(false)}
                      className="rounded px-1.5 py-0.5 text-[10px] text-neutral-400 hover:text-white transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDelete(true)}
                    className="rounded p-1 text-neutral-500 hover:text-red-400 transition-colors"
                    title="Delete widget"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                    </svg>
                  </button>
                )}
              </div>
            </div>
          )}

          <div className={cn(editMode && "pt-6 pointer-events-none select-none")}>
            <h3 className="mb-3 text-sm font-medium text-neutral-300">
              {widget.title}
            </h3>
            {children}
          </div>
        </div>
      </BlurFade>
    </div>
  );
}

function renderWidget(
  widget: DashboardWidget,
  entities: EntityInfo[],
  onRefresh?: () => void,
) {
  const cfg = widget.config as any;

  switch (widget.type) {
    case "stat":
      return <StatWidget config={cfg} entities={entities} />;
    case "toggle_group":
      return <ToggleGroupWidget config={cfg} entities={entities} onRefresh={onRefresh} />;
    case "sensor_grid":
      return <SensorGridWidget config={cfg} entities={entities} />;
    case "camera":
      return <CameraWidget config={cfg} />;
    case "quick_actions":
      return <QuickActionsWidget config={cfg} onRefresh={onRefresh} />;
    case "weather":
      return <WeatherWidget config={cfg} entities={entities} />;
    case "scene_buttons":
      return <SceneButtonsWidget config={cfg} />;
    case "gauge":
      return <GaugeWidget config={cfg} entities={entities} />;
    case "weather_card":
      return <WeatherCardWidget config={cfg} entities={entities} />;
    case "light_control":
      return <LightControlWidget config={cfg} entities={entities} onRefresh={onRefresh} />;
    case "climate_control":
      return <ClimateControlWidget config={cfg} entities={entities} onRefresh={onRefresh} />;
    case "printer":
      return <PrinterWidget config={cfg} entities={entities} />;
    case "air_purifier":
      return <AirPurifierWidget config={cfg} entities={entities} onRefresh={onRefresh} />;
    case "room_environment":
      return <RoomEnvironmentWidget config={cfg} entities={entities} />;
    case "health":
      return <HealthWidget config={cfg} entities={entities} />;
    case "presence":
      return <PresenceWidget config={cfg} entities={entities} />;
    case "power_chart":
      return <PowerChartWidget config={cfg} />;
    case "bandwidth_chart":
      return <BandwidthChartWidget config={cfg} />;
    case "smart_plug":
      return <SmartPlugWidget config={cfg} entities={entities} onRefresh={onRefresh} />;
    case "generative":
      return <GenerativeWidget config={cfg} entities={entities} onRefresh={onRefresh} />;
    default:
      return (
        <p className="text-xs text-neutral-500">
          Unknown widget type: {widget.type}
        </p>
      );
  }
}

function GenerativeWidget({
  config,
  entities,
  onRefresh,
}: {
  config: { spec?: { root: string; elements: Record<string, unknown> } };
  entities: EntityInfo[];
  onRefresh?: () => void;
}) {
  const entityLookup: EntityLookup = useCallback(
    (id: string) => entities.find((e) => e.entity_id === id),
    [entities],
  );

  if (!config.spec) {
    return <p className="text-xs text-neutral-500">No spec configured.</p>;
  }

  return (
    <GenUIRenderer
      spec={config.spec}
      entityLookup={entityLookup}
      onRefresh={onRefresh}
    />
  );
}

export default function DashboardRenderer({
  config,
  entitiesData,
  onRefresh,
  editMode,
  onReorder,
  onDelete,
  onEditWidget,
}: DashboardRendererProps) {
  const entities = flattenEntities(entitiesData);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id || !config.widgets) return;

      const ids = config.widgets.map((w) => w.id);
      const oldIndex = ids.indexOf(active.id as string);
      const newIndex = ids.indexOf(over.id as string);
      if (oldIndex === -1 || newIndex === -1) return;

      const reordered = [...ids];
      reordered.splice(oldIndex, 1);
      reordered.splice(newIndex, 0, active.id as string);
      onReorder?.(reordered);
    },
    [config.widgets, onReorder],
  );

  if (!config.widgets || config.widgets.length === 0) {
    return (
      <div className="flex items-center justify-center py-20 text-neutral-500">
        No widgets configured. Use the AI assistant to set up your dashboard.
      </div>
    );
  }

  const widgetIds = config.widgets.map((w) => w.id);

  const grid = (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {config.widgets.map((widget, i) => (
        <SortableWidgetShell
          key={widget.id}
          widget={widget}
          index={i}
          editMode={editMode}
          onDelete={onDelete}
          onEditWidget={onEditWidget}
        >
          {renderWidget(widget, entities, onRefresh)}
        </SortableWidgetShell>
      ))}
    </div>
  );

  if (editMode) {
    return (
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext items={widgetIds} strategy={rectSortingStrategy}>
          {grid}
        </SortableContext>
      </DndContext>
    );
  }

  return grid;
}
