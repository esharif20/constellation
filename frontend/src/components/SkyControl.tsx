import { memo, useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { TelescopeIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { DEFAULTS, LAYERS, STRENGTHS, getSky, onSky, setSky, type Strength } from "@/graph/skySettings";
import { cn } from "@/lib/utils";

// The Sky popover: which background layers show and how strongly. Sky state lives in graph/skySettings, outside React,
// so a change re-renders only this popover; the layers themselves only change CSS opacity.
export const SkyControl = memo(function SkyControl() {
  const [sky, set] = useState(getSky);
  useEffect(() => onSky(set), []);
  const id = useId();
  const off = sky.strength === 0;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" aria-label="Sky settings" title="Sky settings" className="pointer-events-auto size-11 rounded-lg p-0 text-text-2 sm:order-last sm:size-10">
          <TelescopeIcon aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} collisionPadding={16} className="glass w-[min(272px,calc(100vw-32px))] gap-3 p-3">
        <div className="flex items-center justify-between pr-8">
          <h2 className="text-[13px] font-medium text-foreground">Sky</h2>
          <Button variant="ghost" size="sm" className="-mr-1 h-8 px-2 text-xs text-text-2" onClick={() => setSky({ ...DEFAULTS })}>Reset</Button>
        </div>
        <StrengthControl value={sky.strength} onChange={(v) => setSky({ ...getSky(), strength: v })} labelId={`${id}-s`} />
        <ul className="flex flex-col">
          {LAYERS.map(([k, label]) => (
            <li key={k} className="flex min-h-10 items-center justify-between gap-3">
              <label htmlFor={`${id}-${k}`} className={off ? "text-[13px] text-text-3" : "text-[13px] text-text-2"}>{label}</label>
              <Switch id={`${id}-${k}`} checked={sky[k]} disabled={off} onCheckedChange={(v) => setSky({ ...getSky(), [k]: v })} />
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
});

// Off / Subtle / Rich as a segmented radio group (the scope filter's look): arrows move and select, Tab leaves.
function StrengthControl({ value, onChange, labelId }: { value: Strength; onChange: (v: Strength) => void; labelId: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: KeyboardEvent) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = ((value + step + 3) % 3) as Strength;
    onChange(next);
    refs.current[next]?.focus();
  };
  return (
    <div className="flex flex-col gap-2">
      <span id={labelId} className="text-xs text-text-2">Strength</span>
      <div role="radiogroup" aria-labelledby={labelId} onKeyDown={onKey} className="grid grid-cols-3 gap-0.5 rounded-lg border bg-surface-2 p-0.5 text-[13px]">
        {STRENGTHS.map((label, i) => (
          <button key={label} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={value === i} tabIndex={value === i ? 0 : -1} onClick={() => onChange(i as Strength)}
            className={cn("min-h-9 cursor-pointer rounded-md px-2 transition-colors duration-(--t-fast) focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none", value === i ? "bg-indigo-bright/20 text-foreground" : "text-text-2 hover:bg-surface-3 hover:text-foreground")}>
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
