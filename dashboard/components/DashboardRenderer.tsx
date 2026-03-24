"use client";

import { useCallback, useState, useMemo } from "react";
import {
  ResponsiveGridLayout,
  useContainerWidth,
  verticalCompactor,
  noCompactor,
} from "react-grid-layout";
import type { Layout, LayoutItem, ResponsiveLayouts } from "react-grid-layout";
import type {
  DashboardConfig,
  DashboardWidget,
  EntityInfo,
  EntitiesResponse,
  WidgetLayout,
  WidgetType,
} from "@/lib/types";
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
import { cn } from "@/lib/utils";

const BREAKPOINTS = { xl: 1280, lg: 1024, md: 768, sm: 640, xs: 0 };
const COLS = { xl: 4, lg: 3, md: 2, sm: 1, xs: 1 };
const ROW_HEIGHT = 40;
const MARGIN: [number, number] = [16, 16];

const SIZE_TO_W: Record<string, number> = { sm: 1, md: 2, lg: 3, full: 4 };

const DEFAULT_H: Partial<Record<WidgetType, number>> = {
  stat: 4,
  toggle_group: 5,
  sensor_grid: 5,
  camera: 10,
  quick_actions: 4,
  weather: 6,
  scene_buttons: 4,
  weather_card: 6,
  gauge: 5,
  light_control: 5,
  climate_control: 5,
  printer: 12,
  air_purifier: 7,
  room_environment: 5,
  health: 8,
  presence: 4,
  power_chart: 6,
  bandwidth_chart: 6,
  smart_plug: 6,
  generative: 6,
};

function generateDefaultLayouts(widgets: DashboardWidget[]): ResponsiveLayouts {
  const layout: LayoutItem[] = [];
  let x = 0;
  let y = 0;
  const maxCols = 4;

  for (const w of widgets) {
    const wCols = Math.min(SIZE_TO_W[w.size] ?? 1, maxCols);
    const h = DEFAULT_H[w.type] ?? 5;

    if (x + wCols > maxCols) {
      x = 0;
      y += 1;
    }

    layout.push({ i: w.id, x, y, w: wCols, h, minW: 1, minH: 2 });
    x += wCols;
    if (x >= maxCols) {
      x = 0;
      y += 1;
    }
  }

  return { xl: layout, lg: layout, md: layout, sm: layout, xs: layout };
}

function mergeLayouts(
  saved: Record<string, WidgetLayout[]> | undefined,
  widgets: DashboardWidget[],
): ResponsiveLayouts {
  if (!saved || Object.keys(saved).length === 0) {
    return generateDefaultLayouts(widgets);
  }

  const widgetIds = new Set(widgets.map((w) => w.id));
  const result: ResponsiveLayouts = {};

  for (const [bp, items] of Object.entries(saved)) {
    const filtered = items
      .filter((l) => widgetIds.has(l.i))
      .map((l) => ({ ...l, minW: l.minW ?? 1, minH: l.minH ?? 2 }));

    const existing = new Set(filtered.map((l) => l.i));
    const missing = widgets.filter((w) => !existing.has(w.id));
    let maxY = filtered.reduce((m, l) => Math.max(m, l.y + l.h), 0);

    for (const w of missing) {
      filtered.push({
        i: w.id,
        x: 0,
        y: maxY,
        w: Math.min(SIZE_TO_W[w.size] ?? 1, 4),
        h: DEFAULT_H[w.type] ?? 5,
        minW: 1,
        minH: 2,
      });
      maxY += DEFAULT_H[w.type] ?? 5;
    }

    result[bp] = filtered;
  }

  return result;
}

interface DashboardRendererProps {
  config: DashboardConfig;
  entitiesData: EntitiesResponse | null;
  onRefresh?: () => void;
  editMode?: boolean;
  onLayoutChange?: (layouts: Record<string, WidgetLayout[]>) => void;
  onDelete?: (widgetId: string) => void;
  onEditWidget?: (widgetId: string) => void;
}

function flattenEntities(data: EntitiesResponse | null): EntityInfo[] {
  if (!data) return [];
  return Object.values(data.domains).flatMap((d) => d.entities);
}

function WidgetCard({
  widget,
  children,
  editMode,
  onDelete,
  onEditWidget,
}: {
  widget: DashboardWidget;
  children: React.ReactNode;
  editMode?: boolean;
  onDelete?: (id: string) => void;
  onEditWidget?: (id: string) => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <div
      className={cn(
        "relative rounded-xl border bg-white/[0.03] p-4 backdrop-blur-sm transition-all h-full overflow-hidden",
        editMode
          ? "border-dashed border-white/20"
          : "border-white/10 hover:border-white/15",
      )}
    >
      {editMode && (
        <div className="absolute top-0 left-0 right-0 flex items-center justify-between rounded-t-xl bg-white/[0.06] px-3 py-1.5 border-b border-white/10 z-10">
          <div className="dashboard-drag-handle cursor-grab active:cursor-grabbing rounded p-0.5 text-neutral-500 hover:text-white transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
              <circle cx="9" cy="5" r="1.5" />
              <circle cx="15" cy="5" r="1.5" />
              <circle cx="9" cy="12" r="1.5" />
              <circle cx="15" cy="12" r="1.5" />
              <circle cx="9" cy="19" r="1.5" />
              <circle cx="15" cy="19" r="1.5" />
            </svg>
          </div>
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

      <div className={cn("h-full overflow-hidden", editMode && "pt-6")}>
        <h3 className="mb-3 text-sm font-medium text-neutral-300">
          {widget.title}
        </h3>
        {children}
      </div>
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
  onLayoutChange,
  onDelete,
  onEditWidget,
}: DashboardRendererProps) {
  const entities = flattenEntities(entitiesData);
  const { width, containerRef, mounted } = useContainerWidth();

  const layouts = useMemo(
    () => mergeLayouts(config.layouts, config.widgets),
    [config.layouts, config.widgets],
  );

  const handleLayoutChange = useCallback(
    (_current: Layout, allLayouts: ResponsiveLayouts) => {
      if (!editMode) return;
      const converted: Record<string, WidgetLayout[]> = {};
      for (const [bp, items] of Object.entries(allLayouts)) {
        if (!items) continue;
        converted[bp] = items.map((l) => ({
          i: l.i,
          x: l.x,
          y: l.y,
          w: l.w,
          h: l.h,
          minW: l.minW,
          minH: l.minH,
        }));
      }
      onLayoutChange?.(converted);
    },
    [editMode, onLayoutChange],
  );

  if (!config.widgets || config.widgets.length === 0) {
    return (
      <div className="flex items-center justify-center py-20 text-neutral-500">
        No widgets configured. Use the AI assistant to set up your dashboard.
      </div>
    );
  }

  return (
    <div ref={containerRef}>
      {mounted && (
        <ResponsiveGridLayout
          width={width}
          layouts={layouts}
          breakpoints={BREAKPOINTS}
          cols={COLS}
          rowHeight={ROW_HEIGHT}
          margin={MARGIN}
          containerPadding={[0, 0] as const}
          dragConfig={{
            enabled: !!editMode,
            handle: ".dashboard-drag-handle",
          }}
          resizeConfig={{
            enabled: !!editMode,
            handles: editMode ? ["se", "e", "s"] : [],
          }}
          compactor={verticalCompactor}
          onLayoutChange={handleLayoutChange}
        >
          {config.widgets.map((widget) => (
            <div key={widget.id}>
              <WidgetCard
                widget={widget}
                editMode={editMode}
                onDelete={onDelete}
                onEditWidget={onEditWidget}
              >
                {renderWidget(widget, entities, onRefresh)}
              </WidgetCard>
            </div>
          ))}
        </ResponsiveGridLayout>
      )}
    </div>
  );
}
