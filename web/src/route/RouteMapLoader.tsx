import { useEffect, useState } from "react";
import { api, isAbort } from "../api/client";
import type { Route, StoreMap } from "../api/types";
import { Skeleton } from "../components/ui";
import { RouteMap } from "./RouteMap";

type MapState = { status: "loading" } | { status: "ready"; map: StoreMap } | { status: "error" };

/** GET /stores/{id}/map, then the route drawn on it. If the map fails, the step list above is still the way. */
export function RouteMapLoader({ storeId, route }: { storeId: string; route: Route }) {
  const [state, setState] = useState<MapState>({ status: "loading" });
  useEffect(() => {
    const c = new AbortController();
    setState({ status: "loading" });
    api
      .map(storeId, c.signal)
      .then((map) => !c.signal.aborted && setState({ status: "ready", map }))
      .catch((e: unknown) => !isAbort(e) && !c.signal.aborted && setState({ status: "error" }));
    return () => c.abort();
  }, [storeId]);

  if (state.status === "loading") return <Skeleton height="10rem" />;
  if (state.status === "error") return <p className="sf-map__note">The map isn't available right now. The steps above show the way.</p>;
  return <RouteMap map={state.map} route={route} />;
}
