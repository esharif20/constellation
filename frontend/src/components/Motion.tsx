import { createContext, forwardRef, isValidElement, useContext, useEffect, useState, type ComponentProps, type ReactElement, type ReactNode } from "react";
import { exitMs } from "@/lib/motion";

// Presence without a library: while its child is falsy Presence keeps the last child mounted, marked as leaving, until the exit has
// played (index.css `[data-pane][data-leaving]`). Same idea as AnimatePresence, ~1 KB instead of ~30 KB gzip (docs/design/motion.md).
const Leave = createContext(false);

export function Presence({ children }: { children: ReactNode }) {
  const live = isValidElement(children) ? (children as ReactElement) : null;
  const [held, setHeld] = useState<ReactElement | null>(live);
  if (live && held !== live) setHeld(live);
  const leaving = !live;
  // Presence owns the exit timer, not the child: a child with no Pane (the Suspense fallback skeleton) would otherwise never unmount.
  useEffect(() => {
    if (!leaving) return;
    const id = setTimeout(() => setHeld(null), exitMs("panel"));
    return () => clearTimeout(id);
  }, [leaving]);
  const shown = live ?? held;
  return shown ? <Leave value={leaving}>{shown}</Leave> : null;
}

type Tag = "section" | "aside" | "div";
type PaneProps = Omit<ComponentProps<"div">, "ref"> & {
  as?: Tag;
  /** Where it comes from on a wide screen; side panels rise from the bottom on a phone. */
  from: "left" | "right" | "top" | "bottom";
  /** Wait before entering (ms), e.g. for the camera to start flying. */
  delay?: number;
};

// Fades and slides in; under Presence it plays its exit before Presence unmounts it. While leaving it is inert (no clicks, no focus, hidden from
// assistive technology). Only transform and opacity animate, so nothing reflows.
export const Pane = forwardRef<HTMLElement, PaneProps>(function Pane({ as: Tag = "div", from, delay = 0, style, ...rest }, ref) {
  const leaving = useContext(Leave);
  return <Tag ref={ref as never} data-pane={from} data-leaving={leaving || undefined} inert={leaving || undefined} style={delay ? { "--pane-delay": `${delay}ms`, ...style } as never : style} {...rest} />;
});
