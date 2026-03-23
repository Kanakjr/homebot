"use client";

import { useMemo, useRef } from "react";
import type { Spec } from "@json-render/core";
import {
  Renderer,
  StateProvider,
  VisibilityProvider,
  ActionProvider,
} from "@json-render/react";
import {
  registry,
  handlers,
  setEntityLookup,
  setOnRefresh,
  type EntityLookup,
} from "./registry";

export interface UISpec {
  root: string;
  elements: Record<string, unknown>;
}

interface GenUIRendererProps {
  spec: UISpec;
  loading?: boolean;
  entityLookup?: EntityLookup;
  onRefresh?: () => void;
}

function filterValidSpec(raw: UISpec): Spec | null {
  if (!raw.root || !raw.elements) return null;
  const rootEl = raw.elements[raw.root] as
    | { type?: string; props?: unknown }
    | undefined;
  if (!rootEl?.type || rootEl.props == null) return null;

  const safeElements: Record<string, unknown> = {};
  for (const [key, el] of Object.entries(raw.elements)) {
    const elem = el as { type?: string; props?: unknown } | undefined;
    if (elem?.type && elem.props != null) {
      safeElements[key] = elem;
    }
  }
  return { root: raw.root, elements: safeElements } as Spec;
}

export default function GenUIRenderer({
  spec,
  loading = false,
  entityLookup,
  onRefresh,
}: GenUIRendererProps) {
  if (entityLookup) setEntityLookup(entityLookup);
  setOnRefresh(onRefresh);

  const filtered = filterValidSpec(spec);
  if (!filtered) return null;

  const stateRef = useRef<Record<string, unknown>>({});
  const setStateRef = useRef<
    React.Dispatch<React.SetStateAction<Record<string, unknown>>>
  >(() => {});

  const actionHandlers = useMemo(
    () =>
      handlers(
        () => setStateRef.current,
        () => stateRef.current,
      ),
    [],
  );

  return (
    <StateProvider initialState={{}}>
      <VisibilityProvider>
        <ActionProvider handlers={actionHandlers}>
          <Renderer
            spec={filtered}
            registry={registry}
            loading={loading}
          />
        </ActionProvider>
      </VisibilityProvider>
    </StateProvider>
  );
}
