"use client";

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
import { BlurFade } from "./magicui/blur-fade";
import { cn } from "@/lib/utils";

interface DashboardRendererProps {
  config: DashboardConfig;
  entitiesData: EntitiesResponse | null;
  onRefresh?: () => void;
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

function WidgetShell({
  widget,
  children,
  index,
}: {
  widget: DashboardWidget;
  children: React.ReactNode;
  index: number;
}) {
  return (
    <BlurFade delay={0.05 + index * 0.04}>
      <div
        className={cn(
          "rounded-xl border border-white/10 bg-white/[0.03] p-4 backdrop-blur-sm transition-colors hover:border-white/15 h-full",
          SIZE_CLASSES[widget.size] ?? SIZE_CLASSES.sm,
        )}
      >
        <h3 className="mb-3 text-sm font-medium text-neutral-300">
          {widget.title}
        </h3>
        {children}
      </div>
    </BlurFade>
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
    default:
      return (
        <p className="text-xs text-neutral-500">
          Unknown widget type: {widget.type}
        </p>
      );
  }
}

export default function DashboardRenderer({
  config,
  entitiesData,
  onRefresh,
}: DashboardRendererProps) {
  const entities = flattenEntities(entitiesData);

  if (!config.widgets || config.widgets.length === 0) {
    return (
      <div className="flex items-center justify-center py-20 text-neutral-500">
        No widgets configured. Use the AI assistant to set up your dashboard.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {config.widgets.map((widget, i) => (
        <WidgetShell key={widget.id} widget={widget} index={i}>
          {renderWidget(widget, entities, onRefresh)}
        </WidgetShell>
      ))}
    </div>
  );
}
