"""render_ui tool -- lets the agent generate interactive UI for the dashboard chat."""

import json

from langchain_core.tools import tool


@tool
def render_ui(spec: dict) -> str:
    """Generate an interactive UI for the user by providing a json-render spec.

    The spec MUST have two keys:
    - "root": a string ID referencing the root element
    - "elements": a dict mapping element IDs to component definitions

    Each element has:
    - "type": one of the available component types below
    - "props": an object matching that component's prop schema
    - "children": an array of child element IDs (empty [] for leaf components)

    AVAILABLE COMPONENTS:

    Layout:
    - Card: { title?: string, padding?: "sm"|"md"|"lg" } -- Container with optional title. Has children.
    - Stack: { direction?: "vertical"|"horizontal", gap?: "sm"|"md"|"lg" } -- Stacks children. Has children.
    - Grid: { columns?: number, gap?: "sm"|"md"|"lg" } -- Grid layout. Has children.

    Device controls:
    - DeviceToggle: { entity_id: string, label?: string } -- On/off toggle for any HA entity. No children.
    - LightControl: { entity_id: string, label?: string } -- Brightness slider + toggle for light.* entities. No children.
    - ClimateControl: { entity_id: string, label?: string } -- Preset modes + toggle for climate/fan entities. No children.

    Display:
    - StatCard: { label: string, value: string, unit?: string } -- Key metric display. No children.
    - SensorReading: { entity_id: string, label?: string } -- Live sensor value. No children.
    - DataTable: { columns: string[], rows: string[][] } -- Tabular data. No children.

    Actions:
    - ActionButton: { label: string, variant?: "primary"|"secondary"|"ghost", action_type: string, action_params?: Record<string,string> } -- Button triggering an action. No children.
      action_type values: "toggle_entity", "set_light", "set_climate", "activate_scene"

    Forms:
    - TextInput: { label?: string, placeholder?: string, field_type?: "text"|"number"|"email" } -- Input field. No children.
    - SelectInput: { label?: string, options: {value: string, label: string}[] } -- Dropdown. No children.

    EXAMPLE SPEC:
    {
      "root": "main-card",
      "elements": {
        "main-card": {
          "type": "Card",
          "props": { "title": "Bedroom Controls" },
          "children": ["controls-stack"]
        },
        "controls-stack": {
          "type": "Stack",
          "props": { "direction": "vertical", "gap": "md" },
          "children": ["light-1", "toggle-1"]
        },
        "light-1": {
          "type": "LightControl",
          "props": { "entity_id": "light.bedside", "label": "Bedside Lamp" },
          "children": []
        },
        "toggle-1": {
          "type": "DeviceToggle",
          "props": { "entity_id": "switch.monitor_plug", "label": "Monitor" },
          "children": []
        }
      }
    }

    Always provide a text response alongside render_ui so the user gets context.
    """
    return json.dumps(spec)


def get_render_ui_tools() -> list:
    return [render_ui]
