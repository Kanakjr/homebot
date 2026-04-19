// Mood / scene presets for the Lights page.
//
// Each mood defines a target state for each of the room's lights:
//   - `bedside` / `table_lamp` are native HA `light.*` entities and use
//     either `rgb_color` + `brightness` or `color_temp_kelvin` + `brightness`.
//   - `rgb_strip` is an Alexa-driven script bundle; we can only set one of
//     Alexa's named colors plus a brightness level.
//
// The `gradient` field is a plain CSS linear-gradient used for the mood
// card's background so the UI matches what the room will actually look
// like when the mood is applied.

export type LightTarget =
  | {
      kind: "light";
      on: true;
      brightness_pct: number;
      rgb_color?: [number, number, number];
      color_temp_kelvin?: number;
    }
  | { kind: "light"; on: false };

export type StripTarget =
  | {
      kind: "strip";
      on: true;
      color: StripColor;
      brightness_pct: number;
    }
  | { kind: "strip"; on: false };

export const STRIP_COLORS = [
  "red",
  "green",
  "blue",
  "yellow",
  "orange",
  "purple",
  "pink",
  "warm white",
  "cool white",
  "daylight",
] as const;
export type StripColor = (typeof STRIP_COLORS)[number];

export const STRIP_COLOR_HEX: Record<StripColor, string> = {
  red: "#ef4444",
  green: "#22c55e",
  blue: "#3b82f6",
  yellow: "#facc15",
  orange: "#f97316",
  purple: "#a855f7",
  pink: "#ec4899",
  "warm white": "#ffd7a1",
  "cool white": "#e0e8ff",
  daylight: "#f5f6ff",
};

export interface Mood {
  id: string;
  name: string;
  description: string;
  gradient: string;
  /**
   * Optional scene photo used as the circular thumbnail on mood cards.
   * Defaults resolve to an Unsplash CDN URL; override by either:
   *   1. Replacing the URL here with your own, or
   *   2. Dropping an image at `public/moods/{id}.jpg` and changing this to
   *      `/moods/{id}.jpg`.
   * If the image fails to load, the `gradient` is shown as a fallback.
   */
  image?: string;
  bedside: LightTarget;
  table_lamp: LightTarget;
  rgb_strip: StripTarget;
}

// Small helper so the Unsplash URL + params stay consistent across moods.
const u = (slug: string) =>
  `https://images.unsplash.com/photo-${slug}?auto=format&fit=crop&w=400&q=75`;

export const MOODS: Mood[] = [
  {
    id: "relax",
    name: "Relax",
    description: "Warm amber glow for unwinding",
    gradient: "linear-gradient(135deg, #7a2e00 0%, #ff7a18 60%, #ffb347 100%)",
    image: u("1703783010857-9bd7a7b97c50"),
    bedside: { kind: "light", on: true, brightness_pct: 45, rgb_color: [255, 147, 41] },
    table_lamp: { kind: "light", on: true, brightness_pct: 35, rgb_color: [255, 147, 41] },
    rgb_strip: { kind: "strip", on: true, color: "warm white", brightness_pct: 30 },
  },
  {
    id: "read",
    name: "Read",
    description: "Neutral warm light for the eyes",
    gradient: "linear-gradient(135deg, #2b1d0e 0%, #caa472 70%, #ffe4ba 100%)",
    image: u("1657040899601-fbcc8f6486f6"),
    bedside: { kind: "light", on: true, brightness_pct: 85, color_temp_kelvin: 3200 },
    table_lamp: { kind: "light", on: true, brightness_pct: 85, color_temp_kelvin: 3200 },
    rgb_strip: { kind: "strip", on: true, color: "warm white", brightness_pct: 60 },
  },
  {
    id: "concentrate",
    name: "Concentrate",
    description: "Cool, focused white light",
    gradient: "linear-gradient(135deg, #0b1324 0%, #5a7fb2 60%, #dce9ff 100%)",
    image: u("1497215842964-222b430dc094"),
    bedside: { kind: "light", on: true, brightness_pct: 100, color_temp_kelvin: 5000 },
    table_lamp: { kind: "light", on: true, brightness_pct: 100, color_temp_kelvin: 5000 },
    rgb_strip: { kind: "strip", on: true, color: "cool white", brightness_pct: 100 },
  },
  {
    id: "energize",
    name: "Energize",
    description: "Bright daylight to wake you up",
    gradient: "linear-gradient(135deg, #1d3e5b 0%, #88c1f0 55%, #ffffff 100%)",
    image: u("1494548162494-384bba4ab999"),
    bedside: { kind: "light", on: true, brightness_pct: 100, color_temp_kelvin: 6500 },
    table_lamp: { kind: "light", on: true, brightness_pct: 100, color_temp_kelvin: 6500 },
    rgb_strip: { kind: "strip", on: true, color: "daylight", brightness_pct: 100 },
  },
  {
    id: "nightlight",
    name: "Nightlight",
    description: "Dim warm glow for late hours",
    gradient: "linear-gradient(135deg, #170b00 0%, #4a1a00 65%, #a34500 100%)",
    image: u("1601922046210-41e129a3e64a"),
    bedside: { kind: "light", on: true, brightness_pct: 8, rgb_color: [255, 90, 30] },
    table_lamp: { kind: "light", on: false },
    rgb_strip: { kind: "strip", on: true, color: "warm white", brightness_pct: 5 },
  },
  {
    id: "bloodmoon",
    name: "Bloodmoon",
    description: "Deep red ambience",
    gradient: "linear-gradient(135deg, #1a0303 0%, #7a0b0b 55%, #ff3a3a 100%)",
    image: u("1532771098148-525cefe10c23"),
    bedside: { kind: "light", on: true, brightness_pct: 70, rgb_color: [190, 20, 20] },
    table_lamp: { kind: "light", on: true, brightness_pct: 55, rgb_color: [150, 10, 10] },
    rgb_strip: { kind: "strip", on: true, color: "red", brightness_pct: 85 },
  },
  {
    id: "tropical_twilight",
    name: "Tropical Twilight",
    description: "Sunset pinks and oranges",
    gradient: "linear-gradient(135deg, #3a0f5a 0%, #d94a7a 55%, #ff8a4c 100%)",
    image: u("1561571994-3c61c554181a"),
    bedside: { kind: "light", on: true, brightness_pct: 65, rgb_color: [255, 100, 60] },
    table_lamp: { kind: "light", on: true, brightness_pct: 55, rgb_color: [255, 60, 120] },
    rgb_strip: { kind: "strip", on: true, color: "pink", brightness_pct: 80 },
  },
  {
    id: "ocean_dawn",
    name: "Ocean Dawn",
    description: "Fresh blue-to-lavender morning",
    gradient: "linear-gradient(135deg, #041a3b 0%, #2a63b5 55%, #9bb7f2 100%)",
    image: u("1549636162-4c964a155253"),
    bedside: { kind: "light", on: true, brightness_pct: 55, rgb_color: [60, 120, 220] },
    table_lamp: { kind: "light", on: true, brightness_pct: 55, rgb_color: [110, 160, 255] },
    rgb_strip: { kind: "strip", on: true, color: "blue", brightness_pct: 80 },
  },
  {
    id: "spring_blossom",
    name: "Spring Blossom",
    description: "Soft pinks in bloom",
    gradient: "linear-gradient(135deg, #4a0c2c 0%, #d46aa0 55%, #ffc7d6 100%)",
    image: u("1522383225653-ed111181a951"),
    bedside: { kind: "light", on: true, brightness_pct: 70, rgb_color: [255, 170, 200] },
    table_lamp: { kind: "light", on: true, brightness_pct: 60, rgb_color: [255, 120, 170] },
    rgb_strip: { kind: "strip", on: true, color: "pink", brightness_pct: 80 },
  },
  {
    id: "arctic_aurora",
    name: "Arctic Aurora",
    description: "Cool greens and teal",
    gradient: "linear-gradient(135deg, #012027 0%, #0ea5a5 55%, #7ef3b8 100%)",
    image: u("1443926818681-717d074a57af"),
    bedside: { kind: "light", on: true, brightness_pct: 60, rgb_color: [50, 200, 180] },
    table_lamp: { kind: "light", on: true, brightness_pct: 60, rgb_color: [100, 255, 170] },
    rgb_strip: { kind: "strip", on: true, color: "green", brightness_pct: 80 },
  },
  {
    id: "galaxy",
    name: "Galaxy",
    description: "Deep purples and violets",
    gradient: "linear-gradient(135deg, #0a0624 0%, #5b2bb8 55%, #9c6bff 100%)",
    image: u("1614926037592-5d7aec4d5f8c"),
    bedside: { kind: "light", on: true, brightness_pct: 55, rgb_color: [120, 50, 200] },
    table_lamp: { kind: "light", on: true, brightness_pct: 55, rgb_color: [80, 100, 255] },
    rgb_strip: { kind: "strip", on: true, color: "purple", brightness_pct: 80 },
  },
  {
    id: "savanna_sunset",
    name: "Savanna Sunset",
    description: "Warm amber dusk",
    gradient: "linear-gradient(135deg, #3b0a00 0%, #ef6c1a 55%, #ffd27a 100%)",
    image: u("1668468834614-b9fd661a0433"),
    bedside: { kind: "light", on: true, brightness_pct: 75, rgb_color: [255, 120, 30] },
    table_lamp: { kind: "light", on: true, brightness_pct: 60, rgb_color: [255, 80, 40] },
    rgb_strip: { kind: "strip", on: true, color: "orange", brightness_pct: 80 },
  },
];

export function findMood(id: string): Mood | undefined {
  return MOODS.find((m) => m.id === id);
}
