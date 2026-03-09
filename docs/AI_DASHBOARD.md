# AI-Customizable Dashboard

The homepage (`/`) is a widget-based dashboard driven by a JSON config stored in SQLite. A floating AI assistant lets you customize the layout via natural language.

## Widget Types

| Type | Description | Config |
|------|-------------|--------|
| `stat` | Single entity value displayed large | `entity_id`, `unit?` |
| `toggle_group` | Grid of toggleable entities with switches | `entities[]` |
| `sensor_grid` | Grid of sensor readings | `entities[]` |
| `camera` | Camera snapshot with refresh button | `entity_id` |
| `quick_actions` | Buttons that call HA services | `actions[{label, entity_id, domain, service}]` |
| `weather` | Weather summary card | `entity_id` |
| `scene_buttons` | Scene activation buttons | `scenes[{entity_id, label}]` |

## Widget Sizes

| Size | Grid Span |
|------|-----------|
| `sm` | 1 column |
| `md` | 2 columns |
| `lg` | 3 columns |
| `full` | Full width |

## Dashboard Editor

Click the yellow floating button (bottom-right) to open the Dashboard Editor panel.

Example requests:
- "add a stat widget for desk power consumption"
- "remove the weather card"
- "make the lights toggle group full width"
- "what entities can I add?"
- "add a camera for the bedroom"
- "move scenes to the top"

The editor uses a dedicated Gemini call focused only on layout editing -- it never controls devices.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard` | Returns current widget config JSON |
| PUT | `/api/dashboard` | Saves a new config directly |
| POST | `/api/dashboard/edit` | AI-powered layout editing via natural language |

## Config Schema

```json
{
  "widgets": [
    {
      "id": "w1",
      "type": "stat",
      "title": "Temperature",
      "config": { "entity_id": "sensor.temperature", "unit": "C" },
      "size": "sm"
    }
  ]
}
```

## Architecture

```
User -> Dashboard Editor panel -> POST /api/dashboard/edit
  -> Gemini Flash (layout-only prompt + current config + available entities)
  -> Updated config JSON -> SQLite persistence
  -> Frontend re-renders widgets instantly
```

The config is stored in a `dashboard_config` table (single row, `id=1`). A default layout is provided when no saved config exists, including stat cards, toggle groups, sensor grid, camera, scenes, and quick actions.

## Files

- `backend/dashboard_config.py` -- SQLite persistence for config JSON
- `backend/api.py` -- GET/PUT/POST dashboard endpoints
- `dashboard/components/DashboardRenderer.tsx` -- Widget grid renderer
- `dashboard/components/DashboardAssistant.tsx` -- Floating AI panel
- `dashboard/components/widgets/` -- Individual widget components
- `dashboard/app/page.tsx` -- Homepage wiring
