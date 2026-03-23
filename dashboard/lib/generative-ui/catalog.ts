import { defineCatalog } from "@json-render/core";
import { schema } from "@json-render/react/schema";
import { z } from "zod";

export const catalog = defineCatalog(schema, {
  components: {
    Card: {
      props: z.object({
        title: z.string().nullable(),
        padding: z.enum(["sm", "md", "lg"]).nullable(),
      }),
      slots: ["default"],
      description:
        "Container card with optional title and padding. Use as a wrapper for groups of related components.",
    },
    Stack: {
      props: z.object({
        direction: z.enum(["vertical", "horizontal"]).nullable(),
        gap: z.enum(["sm", "md", "lg"]).nullable(),
      }),
      slots: ["default"],
      description:
        "Layout container that stacks children vertically or horizontally with configurable gap.",
    },
    Grid: {
      props: z.object({
        columns: z.number().nullable(),
        gap: z.enum(["sm", "md", "lg"]).nullable(),
      }),
      slots: ["default"],
      description:
        "Responsive grid layout. Columns default to 2. Use for sensor readings, stat cards, etc.",
    },
    DeviceToggle: {
      props: z.object({
        entity_id: z.string(),
        label: z.string().nullable(),
      }),
      description:
        "On/off toggle switch for a Home Assistant entity. Shows friendly name and current state. Works with lights, switches, fans, etc.",
    },
    LightControl: {
      props: z.object({
        entity_id: z.string(),
        label: z.string().nullable(),
      }),
      description:
        "Light control with brightness slider and on/off toggle. Shows current brightness percentage. Use for light.* entities.",
    },
    ClimateControl: {
      props: z.object({
        entity_id: z.string(),
        label: z.string().nullable(),
      }),
      description:
        "Climate/fan control with preset mode buttons, on/off toggle, and current temperature display. Use for climate.* or fan.* entities.",
    },
    StatCard: {
      props: z.object({
        label: z.string(),
        value: z.string(),
        unit: z.string().nullable(),
      }),
      description:
        "Displays a single key metric with large value text, label, and optional unit. Use for showing a specific reading or count.",
    },
    SensorReading: {
      props: z.object({
        entity_id: z.string(),
        label: z.string().nullable(),
      }),
      description:
        "Shows a sensor entity's current state with its friendly name. Use for sensor.*, binary_sensor.*, etc.",
    },
    ActionButton: {
      props: z.object({
        label: z.string(),
        variant: z.enum(["primary", "secondary", "ghost"]).nullable(),
        action_type: z.string(),
        action_params: z.record(z.string(), z.string()).nullable(),
      }),
      description:
        "Button that triggers an action. action_type is the catalog action name (toggle_entity, activate_scene, set_light). action_params carries the parameters.",
    },
    DataTable: {
      props: z.object({
        columns: z.array(z.string()),
        rows: z.array(z.array(z.string())),
      }),
      description:
        "Table for tabular data. columns is the header row, rows is an array of value arrays.",
    },
    TextInput: {
      props: z.object({
        label: z.string().nullable(),
        placeholder: z.string().nullable(),
        field_type: z.enum(["text", "number", "email"]).nullable(),
      }),
      description: "Text input field with optional label and placeholder.",
    },
    SelectInput: {
      props: z.object({
        label: z.string().nullable(),
        options: z.array(
          z.object({ value: z.string(), label: z.string() }),
        ),
      }),
      description: "Dropdown select with predefined options.",
    },
  },
  actions: {
    toggle_entity: {
      params: z.object({
        entity_id: z.string(),
        action: z.enum(["toggle", "turn_on", "turn_off"]),
      }),
      description: "Toggle a Home Assistant entity on/off.",
    },
    set_light: {
      params: z.object({
        entity_id: z.string(),
        brightness: z.number().nullable(),
      }),
      description: "Set light brightness (0-255).",
    },
    set_climate: {
      params: z.object({
        entity_id: z.string(),
        preset_mode: z.string().nullable(),
        temperature: z.number().nullable(),
      }),
      description: "Set climate/fan preset mode or target temperature.",
    },
    activate_scene: {
      params: z.object({
        scene_id: z.string(),
      }),
      description: "Activate a Home Assistant scene by ID.",
    },
  },
});
