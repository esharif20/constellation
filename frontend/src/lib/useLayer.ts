import { useEffect, useLayoutEffect, useId, useRef } from "react";
import { register, type Layer, type Why } from "@/lib/dismiss";

type Opts = Pick<Layer, "rank" | "inside" | "press" | "background"> & { close: (why: Why) => void };

/** Registers an overlay on the dismiss stack while `open`: outside press, background click, Escape order, one transient at a time. */
export function useLayer(open: boolean, opts: Opts) {
  const id = useId(), o = useRef(opts);
  useLayoutEffect(() => { o.current = opts; }); // latest callbacks without re-registering
  useEffect(() => {
    if (!open) return;
    return register({ id, rank: o.current.rank, press: o.current.press, background: o.current.background, close: (why) => o.current.close(why), inside: () => o.current.inside?.() ?? [] });
  }, [open, id]);
}
