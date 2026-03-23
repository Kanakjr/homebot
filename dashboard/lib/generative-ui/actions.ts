import {
  toggleEntity,
  setLightState,
  setClimateState,
  activateScene,
} from "@/lib/api";

export const actionHandlers = {
  toggle_entity: async (params: {
    entity_id: string;
    action: "toggle" | "turn_on" | "turn_off";
  }) => {
    await toggleEntity(params.entity_id, params.action);
  },

  set_light: async (params: {
    entity_id: string;
    brightness: number | null;
  }) => {
    if (params.brightness != null) {
      await setLightState(params.entity_id, {
        brightness: params.brightness,
      });
    }
  },

  set_climate: async (params: {
    entity_id: string;
    preset_mode: string | null;
    temperature: number | null;
  }) => {
    const updates: Record<string, unknown> = {};
    if (params.preset_mode) updates.preset_mode = params.preset_mode;
    if (params.temperature != null) updates.temperature = params.temperature;
    await setClimateState(
      params.entity_id,
      updates as {
        preset_mode?: string;
        temperature?: number;
      },
    );
  },

  activate_scene: async (params: { scene_id: string }) => {
    await activateScene(params.scene_id);
  },
};
