import { createContext, forwardRef, isValidElement, useCallback, useContext, useEffect, useMemo, useState, type ComponentProps, type ReactElement, type ReactNode } from "react";
import { exitMs } from "@/lib/motion";

// Presence without a library: while its child is falsy Presence keeps the last child mounted, marked as leaving, until the exit has
// played (index.css `[data-pane][data-leaving]`). Same idea as AnimatePresence, ~1 KB instead of ~30 KB gzip (docs/design/motion.md).
const Leave = createContext<{ leaving: boolean; done: () => void }>({ leaving: false, done: () => {} });

export function Presence({ children }: { children: ReactNode }) {
  const live = isValidElement(children) ? (children as ReactElement) : null;
  const [held, setHeld] = useState<ReactElement | null>(live);
  if (live && held !== live) setHeld(live);
  const done = useCallback(() => setHeld(null), []);
  const leaving = !live;
  const value = useMemo(() => ({ leaving, done }), [leaving, done]);
  const shown = live ?? held;
  return shown ? <Leave value={value}>{shown}</Leave> : null;
}

type Tag = "section" | "aside" | "div";
type PaneProps = Omit<ComponentProps<"div">, "ref"> & {
  as?: Tag;
  /** Where it comes from on a wide screen; side panels rise from the bottom on a phone. */
  from: "left" | "right" | "top" | "bottom";
  /** Wait before entering (ms), e.g. for the camera to start flying. */
  delay?: number;
};

// Fades and slides in; under Presence it plays its exit before unmounting. While leaving it is inert (no clicks, no focus, hidden from
// assistive technology). Only transform and opacity animate, so nothing reflows.
export const Pane = forwardRef<HTMLElement, PaneProps>(function Pane({ as: Tag = "div", from, delay = 0, style, ...rest }, ref) {
  const { leaving, done } = useContext(Leave);
  useEffect(() => {
    if (!leaving) return;
    const id = setTimeout(done, exitMs("panel"));
    return () => clearTimeout(id);
  }, [leaving, done]);
  return <Tag ref={ref as never} data-pane={from} data-leaving={leaving || undefined} inert={leaving || undefined} style={delay ? { "--pane-delay": `${delay}ms`, ...style } as never : style} {...rest} />;
});
