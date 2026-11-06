import { useEffect, useId, useState } from "react";
import { TelescopeIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { DEFAULTS, LAYERS, STRENGTHS, getSky, onSky, setSky, type Strength } from "@/graph/skySettings";

// The Sky popover: which background layers show and how strongly. A quiet icon in the top bar; it never competes with Ask or search.
export function SkyControl() {
  const [sky, set] = useState(getSky);
  useEffect(() => onSky(set), []);
  const id = useId();
  const off = sky.strength === 0;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" aria-label="Sky settings" className="pointer-events-auto size-11 rounded-lg p-0 text-text-2 sm:order-last sm:size-10">
          <TelescopeIcon aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} collisionPadding={16} className="glass w-[min(272px,calc(100vw-32px))] gap-3 p-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[13px] font-medium text-foreground">Sky</h2>
          <Button variant="ghost" size="sm" className="-mr-1 h-8 px-2 text-xs text-text-2" onClick={() => setSky({ ...DEFAULTS })}>Reset</Button>
        </div>
        <div className="flex flex-col gap-2">
          <span id={`${id}-s`} className="text-xs text-text-2">Strength</span>
          <Slider min={0} max={2} step={1} value={[sky.strength]} onValueChange={([v]) => setSky({ ...sky, strength: v as Strength })} thumbProps={{ "aria-labelledby": `${id}-s`, "aria-valuetext": STRENGTHS[sky.strength] }} className="py-2" />
          <div aria-hidden className="flex justify-between text-[11px] text-text-3">{STRENGTHS.map((s, i) => <span key={s} className={i === sky.strength ? "text-text-2" : undefined}>{s}</span>)}</div>
        </div>
        <ul className="flex flex-col">
          {LAYERS.map(([k, label]) => (
            <li key={k} className="flex min-h-10 items-center justify-between gap-3">
              <label htmlFor={`${id}-${k}`} className={off ? "text-[13px] text-text-3" : "text-[13px] text-text-2"}>{label}</label>
              <Switch id={`${id}-${k}`} checked={sky[k]} disabled={off} onCheckedChange={(v) => setSky({ ...sky, [k]: v })} />
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
