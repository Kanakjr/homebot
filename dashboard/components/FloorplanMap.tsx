"use client";

import { useMemo } from "react";
import type { FloorplanConfig, EntityInfo } from "@/lib/types";

interface FloorplanMapProps {
  config: FloorplanConfig;
  entities: Record<string, EntityInfo>;
  onDeviceClick: (svgId: string) => void;
  selectedDevice: string | null;
}

function getDeviceState(
  svgId: string,
  config: FloorplanConfig,
  entities: Record<string, EntityInfo>,
): { entity: EntityInfo | null; isOn: boolean; stateText: string } {
  const mapping = config.devices.find((d) => d.svg_id === svgId);
  if (!mapping) return { entity: null, isOn: false, stateText: "" };
  const entity = entities[mapping.entity_id] || null;
  if (!entity) return { entity: null, isOn: false, stateText: "N/A" };

  const state = entity.state;
  const isOn = state === "on" || state === "home" || state === "playing";

  let stateText = state;
  if (mapping.type === "sensor") {
    const val = parseFloat(state);
    if (!isNaN(val)) {
      stateText = val % 1 === 0 ? String(val) : val.toFixed(1);
    }
  }

  return { entity, isOn, stateText };
}

type DeviceColors = {
  glow: string;
  fill: string;
  stroke: string;
  glowOn: string;
};

const DEVICE_COLORS: Record<string, DeviceColors> = {
  light: { glow: "none", fill: "#555", stroke: "#666", glowOn: "0 0 14px 4px rgba(255,215,0,0.5)" },
  switch: { glow: "none", fill: "#555", stroke: "#666", glowOn: "0 0 10px 3px rgba(74,222,128,0.4)" },
  fan: { glow: "none", fill: "#555", stroke: "#666", glowOn: "0 0 10px 3px rgba(96,165,250,0.4)" },
  camera: { glow: "none", fill: "#555", stroke: "#666", glowOn: "0 0 10px 3px rgba(96,165,250,0.4)" },
  sensor: { glow: "none", fill: "#555", stroke: "#666", glowOn: "none" },
  device_tracker: { glow: "none", fill: "#555", stroke: "#666", glowOn: "0 0 10px 3px rgba(74,222,128,0.4)" },
};

function DeviceOverlay({
  svgId,
  config,
  entities,
  onClick,
  selected,
}: {
  svgId: string;
  config: FloorplanConfig;
  entities: Record<string, EntityInfo>;
  onClick: () => void;
  selected: boolean;
}) {
  const mapping = config.devices.find((d) => d.svg_id === svgId);
  if (!mapping) return null;

  const { entity, isOn, stateText } = getDeviceState(svgId, config, entities);
  const colors = DEVICE_COLORS[mapping.type] || DEVICE_COLORS.sensor;

  const positions: Record<string, { x: number; y: number }> = {
    light_bed: { x: 630, y: 140 },
    light_foyer: { x: 630, y: 355 },
    light_lamp: { x: 927, y: 110 },
    plug_desk: { x: 860, y: 82 },
    plug_printer: { x: 835, y: 370 },
    router_hallway: { x: 400, y: 180 },
    router_bedroom: { x: 755, y: 82 },
    camera_living: { x: 850, y: 305 },
    device_air_purifier: { x: 927, y: 290 },
    device_3d_printer: { x: 905, y: 400 },
    sensor_foyer: { x: 660, y: 395 },
  };

  const pos = positions[svgId];
  if (!pos) return null;

  const boxShadow = isOn ? colors.glowOn : "none";
  const statusColor = isOn ? "#4ade80" : "#666";
  const ringColor = selected ? "rgba(255,215,0,0.6)" : "transparent";

  return (
    <g
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      style={{ cursor: "pointer" }}
    >
      <circle
        cx={pos.x}
        cy={pos.y}
        r={24}
        fill="transparent"
        stroke={ringColor}
        strokeWidth={selected ? 2 : 0}
      />
      {isOn && (
        <circle
          cx={pos.x}
          cy={pos.y}
          r={22}
          fill="none"
          stroke={mapping.type === "light" ? "rgba(255,215,0,0.3)" : mapping.type === "switch" ? "rgba(74,222,128,0.2)" : "rgba(96,165,250,0.2)"}
          strokeWidth={4}
          style={{ filter: `drop-shadow(${boxShadow})` }}
        >
          {mapping.type === "light" && isOn && (
            <animate attributeName="opacity" values="0.6;1;0.6" dur="2s" repeatCount="indefinite" />
          )}
        </circle>
      )}
      <circle
        cx={pos.x + 16}
        cy={pos.y - 16}
        r={4}
        fill={statusColor}
      />
      {mapping.type === "sensor" && entity && (
        <text
          x={pos.x}
          y={pos.y + 32}
          textAnchor="middle"
          fill="#a3a3a3"
          fontSize="10"
          fontFamily="monospace"
        >
          {stateText}
        </text>
      )}
      <title>{`${mapping.label}: ${stateText}`}</title>
    </g>
  );
}

export default function FloorplanMap({ config, entities, onDeviceClick, selectedDevice }: FloorplanMapProps) {
  const deviceSvgIds = useMemo(() => config.devices.map((d) => d.svg_id), [config]);

  return (
    <svg viewBox="0 0 1000 500" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" className="max-w-4xl mx-auto">
      <defs>
        <style>{`
          .wall { stroke: #666; stroke-width: 8; stroke-linecap: square; fill: none; }
          .wall-dash { stroke: #666; stroke-width: 8; stroke-dasharray: 15,10; fill: none; }
          .door-arc { stroke: #555; stroke-width: 1.5; fill: none; }
          .door-line { stroke: #666; stroke-width: 3; stroke-linecap: round; }
          .door-frame { fill: #333; stroke: #555; stroke-width: 1; }
          .furniture { stroke: #444; stroke-width: 2; }
          .ha-device { cursor: pointer; transition: all 0.3s ease; }
          .ha-device:hover { filter: drop-shadow(0px 0px 8px rgba(255, 215, 0, 0.4)); }
          .device-bg { fill: rgba(40, 40, 40, 0.9); stroke: #555; stroke-width: 1; rx: 6; }
          .device-icon { fill: none; stroke: #999; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
          .rgb-glow { fill: url(#rgbGrad); opacity: 0.8; }
        `}</style>

        <linearGradient id="rgbGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#ff00ff" />
          <stop offset="33%" stopColor="#00ffff" />
          <stop offset="66%" stopColor="#ffff00" />
          <stop offset="100%" stopColor="#00ff00" />
        </linearGradient>

        <g id="device-base">
          <rect x="-20" y="-20" width="40" height="40" className="device-bg" />
        </g>
      </defs>

      <rect width="1000" height="500" fill="transparent" />

      {/* --- Walls --- */}
      {/* Bathroom */}
      <path className="wall" d="M 210,200 L 210,50 L 280,50 M 330,50 L 370,50 L 370,200 L 350,200 M 240,200 L 210,200" />
      <path className="wall-dash" d="M 280,50 L 330,50" />

      {/* Kitchen */}
      <path className="wall" d="M 30,240 L 380,240 L 380,310 M 380,380 L 380,460 L 30,460 L 30,380 M 30,290 L 30,240" />
      <path className="wall-dash" d="M 30,380 L 30,290" />

      {/* Bedroom */}
      <path className="wall" d="M 600,220 L 600,50 L 650,50 M 890,50 L 960,50 L 960,460 L 550,460 L 550,450" />
      <path className="wall-dash" d="M 650,50 L 890,50" />

      {/* Inner walls */}
      <path className="wall" d="M 600,330 L 600,460" />
      <path className="wall" d="M 700,330 L 700,460" />
      <path className="wall" d="M 660,330 L 700,330" />

      {/* --- Doors --- */}
      <rect className="door-frame" x="235" y="195" width="10" height="10" />
      <rect className="door-frame" x="345" y="195" width="10" height="10" />
      <path className="door-arc" d="M 240,90 A 110,110 0 0,1 350,200" />
      <path className="door-line" d="M 240,200 L 240,90" />

      <rect className="door-frame" x="595" y="215" width="10" height="10" />
      <rect className="door-frame" x="595" y="325" width="10" height="10" />
      <path className="door-arc" d="M 710,330 A 110,110 0 0,0 600,220" />
      <path className="door-line" d="M 600,330 L 710,330" />

      <rect className="door-frame" x="655" y="325" width="10" height="10" />
      <path className="door-arc" d="M 600,390 A 60,60 0 0,0 660,330" />
      <path className="door-line" d="M 600,330 L 600,390" />

      <path className="door-arc" d="M 500,340 A 120,120 0 0,0 380,460" />
      <path className="door-line" d="M 500,460 L 500,340" />

      {/* --- Furniture --- */}
      {/* Washer */}
      <rect x="40" y="244" width="60" height="65" fill="#1a1a1a" className="furniture" rx="4" />
      <circle cx="70" cy="282" r="18" fill="none" className="furniture" />
      <circle cx="55" cy="255" r="3" fill="#444" />
      <circle cx="65" cy="255" r="3" fill="#444" />
      <circle cx="75" cy="255" r="3" fill="#444" />

      {/* Countertop */}
      <rect x="110" y="244" width="160" height="45" fill="#1a1a1a" rx="2" />

      {/* Fridge */}
      <rect x="280" y="244" width="70" height="65" fill="#1a1a1a" className="furniture" rx="4" />
      <rect x="305" y="255" width="20" height="35" fill="none" className="furniture" rx="2" />
      <circle cx="315" cy="272" r="10" fill="none" className="furniture" />

      {/* Dining */}
      <rect x="40" y="405" width="310" height="51" fill="#1a1a1a" />
      <line x1="120" y1="405" x2="120" y2="456" stroke="#333" strokeWidth="2" />
      <line x1="200" y1="405" x2="200" y2="456" stroke="#333" strokeWidth="2" />
      <line x1="280" y1="405" x2="280" y2="456" stroke="#333" strokeWidth="2" />
      <rect x="50" y="410" width="70" height="40" fill="#222" rx="4" />
      <ellipse cx="85" cy="430" rx="22" ry="14" fill="none" className="furniture" />

      {/* Bed */}
      <rect x="605" y="55" width="120" height="140" fill="#1a1a1a" className="furniture" rx="4" />
      <rect x="610" y="60" width="50" height="30" fill="#222" className="furniture" rx="4" />
      <rect x="665" y="60" width="50" height="30" fill="#222" className="furniture" rx="4" />
      <path d="M 605,100 L 725,100" className="furniture" />

      {/* Desk area */}
      <rect x="725" y="55" width="170" height="55" fill="#222" className="furniture" rx="2" />

      {/* Wardrobe */}
      <rect x="900" y="55" width="55" height="150" fill="#1a1a2a" className="furniture" />
      <rect x="900" y="205" width="55" height="45" fill="#1a2a3a" className="furniture" />

      {/* Air purifier */}
      <rect x="900" y="260" width="55" height="75" fill="#1a1a1a" className="furniture" rx="4" />
      <circle cx="927" cy="275" r="8" fill="none" className="furniture" />
      <path d="M 905,315 L 950,315 M 905,320 L 950,320 M 905,325 L 950,325 M 905,330 L 950,330" stroke="#444" strokeWidth="2" strokeDasharray="2,3" />

      {/* 3D printer */}
      <rect x="860" y="350" width="90" height="100" fill="#1a1a1a" className="furniture" rx="4" />
      <rect x="870" y="390" width="70" height="10" fill="#333" />
      <path d="M 880,360 L 880,440 M 930,360 L 930,440 M 880,360 L 930,360 L 930,370 L 880,370 Z" fill="#444" className="furniture" />
      <path d="M 905,370 L 905,390" className="furniture" />
      <rect x="800" y="445" width="150" height="6" className="rgb-glow" rx="3" />

      {/* --- Smart devices (original icons) --- */}
      {/* Router - hallway */}
      <g className="ha-device" transform="translate(400, 180)" onClick={() => onDeviceClick("router_hallway")}>
        <use href="#device-base" />
        <rect x="-12" y="-5" width="24" height="10" fill="transparent" className="device-icon" rx="2" />
        <path d="M -8,-5 L -10,-12 M 8,-5 L 10,-12" className="device-icon" />
        <path d="M -6,5 A 8,8 0 0,1 6,5 M -10,9 A 12,12 0 0,1 10,9" className="device-icon" strokeWidth="1.5" />
      </g>

      {/* Router - bedroom */}
      <g className="ha-device" transform="translate(755, 82)" onClick={() => onDeviceClick("router_bedroom")}>
        <use href="#device-base" />
        <rect x="-12" y="-5" width="24" height="10" fill="transparent" className="device-icon" rx="2" />
        <path d="M -8,-5 L -10,-12 M 8,-5 L 10,-12" className="device-icon" />
        <path d="M -6,5 A 8,8 0 0,1 6,5 M -10,9 A 12,12 0 0,1 10,9" className="device-icon" strokeWidth="1.5" />
      </g>

      {/* Plug - desk */}
      <g className="ha-device" transform="translate(860, 82)" onClick={() => onDeviceClick("plug_desk")}>
        <use href="#device-base" />
        <rect x="-10" y="-12" width="20" height="24" fill="transparent" className="device-icon" rx="4" />
        <circle cx="-3" cy="0" r="2" fill="#999" />
        <circle cx="3" cy="0" r="2" fill="#999" />
        <path d="M 12,-6 A 8,8 0 0,1 12,6 M 15,-9 A 12,12 0 0,1 15,9" className="device-icon" strokeWidth="1.5" />
      </g>

      {/* Plug - printer */}
      <g className="ha-device" transform="translate(835, 370)" onClick={() => onDeviceClick("plug_printer")}>
        <use href="#device-base" />
        <rect x="-10" y="-12" width="20" height="24" fill="transparent" className="device-icon" rx="4" />
        <circle cx="-3" cy="0" r="2" fill="#999" />
        <circle cx="3" cy="0" r="2" fill="#999" />
        <path d="M -12,-6 A 8,8 0 0,0 -12,6 M -15,-9 A 12,12 0 0,0 -15,9" className="device-icon" strokeWidth="1.5" />
      </g>

      {/* Light - bedroom */}
      <g className="ha-device" transform="translate(630, 140)" onClick={() => onDeviceClick("light_bed")}>
        <use href="#device-base" />
        <path d="M -6,-6 C -6,-12 6,-12 6,-6 C 6,-2 4,1 4,4 L -4,4 C -4,1 -6,-2 -6,-6 Z" fill="transparent" className="device-icon" />
        <line x1="-3" y1="7" x2="3" y2="7" className="device-icon" />
        <path d="M 8,-6 A 8,8 0 0,1 8,4 M 11,-9 A 12,12 0 0,1 11,7" className="device-icon" strokeWidth="1.5" />
      </g>

      {/* Light - foyer */}
      <g className="ha-device" transform="translate(630, 355)" onClick={() => onDeviceClick("light_foyer")}>
        <use href="#device-base" />
        <path d="M -6,-6 C -6,-12 6,-12 6,-6 C 6,-2 4,1 4,4 L -4,4 C -4,1 -6,-2 -6,-6 Z" fill="transparent" className="device-icon" />
        <line x1="-3" y1="7" x2="3" y2="7" className="device-icon" />
        <path d="M 8,-6 A 8,8 0 0,1 8,4 M 11,-9 A 12,12 0 0,1 11,7" className="device-icon" strokeWidth="1.5" />
      </g>

      {/* Lamp - desk */}
      <g className="ha-device" transform="translate(927, 110)" onClick={() => onDeviceClick("light_lamp")}>
        <use href="#device-base" />
        <path d="M -8,5 L 8,5 L 10,12 L -10,12 Z" fill="#3d2a1a" stroke="#3d2a1a" strokeWidth="1.5" />
        <path d="M -6,5 C -6,-4 -3,-12 0,-14 C 3,-12 6,-4 6,5 Z" fill="rgba(50,50,50,0.7)" stroke="#555" strokeWidth="1" />
        <circle cx="0" cy="0" r="3" fill="#665500" />
      </g>

      {/* Camera */}
      <g className="ha-device" transform="translate(850, 305)" onClick={() => onDeviceClick("camera_living")}>
        <use href="#device-base" />
        <path d="M -12,0 A 12,12 0 0,1 12,0 L 8,6 L -8,6 Z" fill="transparent" className="device-icon" />
        <circle cx="0" cy="0" r="5" fill="#999" />
        <circle cx="0" cy="0" r="2" fill="#333" />
        <path d="M -6,-10 A 15,15 0 0,0 -16,-4 M -9,-14 A 20,20 0 0,0 -20,-6" className="device-icon" strokeWidth="1.5" />
      </g>

      {/* Sensor - foyer */}
      <g className="ha-device" transform="translate(660, 395)" onClick={() => onDeviceClick("sensor_foyer")}>
        <use href="#device-base" />
        <rect x="-10" y="-8" width="20" height="16" fill="transparent" className="device-icon" rx="2" />
        <circle cx="4" cy="0" r="3" fill="#999" />
        <line x1="-6" y1="-2" x2="-2" y2="-2" className="device-icon" strokeWidth="1.5" />
        <line x1="-6" y1="2" x2="-2" y2="2" className="device-icon" strokeWidth="1.5" />
        <path d="M -4,12 A 8,8 0 0,1 4,12 M -7,16 A 12,12 0 0,1 7,16" className="device-icon" strokeWidth="1.5" />
      </g>

      {/* --- Room labels --- */}
      <text x="290" y="130" textAnchor="middle" fill="#555" fontSize="14" fontFamily="monospace" fontWeight="bold">Bathroom</text>
      <text x="200" y="360" textAnchor="middle" fill="#555" fontSize="14" fontFamily="monospace" fontWeight="bold">Kitchen</text>
      <text x="480" y="280" textAnchor="middle" fill="#555" fontSize="14" fontFamily="monospace" fontWeight="bold">Hallway</text>
      <text x="650" y="440" textAnchor="middle" fill="#555" fontSize="14" fontFamily="monospace" fontWeight="bold">Foyer</text>
      <text x="780" y="180" textAnchor="middle" fill="#555" fontSize="14" fontFamily="monospace" fontWeight="bold">Bedroom</text>

      {/* --- Live state overlays --- */}
      {deviceSvgIds.map((svgId) => (
        <DeviceOverlay
          key={svgId}
          svgId={svgId}
          config={config}
          entities={entities}
          onClick={() => onDeviceClick(svgId)}
          selected={selectedDevice === svgId}
        />
      ))}
    </svg>
  );
}
