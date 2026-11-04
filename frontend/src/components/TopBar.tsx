import { Command as CommandPrimitive } from "cmdk";
import { SearchIcon, TriangleAlertIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandItem, CommandList } from "@/components/ui/command";
import { Kbd } from "@/components/ui/kbd";
import { Popover, PopoverAnchor, PopoverContent, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { kindName, type GNode, type Model } from "@/graph/model";

type Props = {
  model: Model;
  query: string;
  found: GNode[];
  onQuery: (q: string) => void;
  onChoose: (n: GNode) => void;
  onPreview: (n: GNode | null) => void;
};

export function TopBar({ model, query, found, onQuery, onChoose, onPreview }: Props) {
  return (
    <header className="pointer-events-none fixed inset-x-4 top-3 flex flex-wrap items-center gap-x-4 gap-y-2 sm:inset-x-6 sm:top-4 sm:flex-nowrap">
      <h1 className="font-serif text-[22px] leading-none tracking-[0.01em] italic [text-shadow:0_0_18px_rgb(150_170_255/0.35)] sm:text-[26px]">Constellation</h1>
      <p className="text-xs text-muted-foreground tabular-nums sm:text-[13px]">
        {model.nodes.length} items, {model.links.length} relations, {model.clusters.length} clusters
      </p>
      <Warnings warnings={model.warnings} />
      <Search query={query} found={found} onQuery={onQuery} onChoose={onChoose} onPreview={onPreview} />
    </header>
  );
}

function Search({ query, found, onQuery, onChoose, onPreview }: Omit<Props, "model">) {
  const input = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);
  const [active, setActive] = useState("");
  const open = focused && query.trim() !== "";
  const shown = found.slice(0, 8);

  // "/" focuses search from anywhere, as in most developer tools
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement;
      if (e.key === "/" && !typing) { e.preventDefault(); input.current?.focus(); }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);

  // the highlighted result lights up on the map before it is chosen
  useEffect(() => {
    onPreview(open ? (found.find((n) => n.id === active) ?? null) : null);
  }, [open, active, found, onPreview]);

  return (
    <Command shouldFilter={false} value={active} onValueChange={setActive} className="pointer-events-auto order-last w-full overflow-visible! bg-transparent p-0 sm:order-none sm:ml-auto sm:w-80">
      <Popover open={open}>
        <PopoverAnchor asChild>
          <div className="relative">
            <SearchIcon className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-text-3" aria-hidden />
            <CommandPrimitive.Input
              ref={input}
              value={query}
              onValueChange={onQuery}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={(e) => {
                if (e.key === "Escape") { e.preventDefault(); if (query) onQuery(""); else input.current?.blur(); }
              }}
              placeholder="Find an Item"
              aria-label="Find an Item by name"
              className="glass h-10 w-full rounded-full border border-border pr-10 pl-10 text-sm transition-[border-color,box-shadow] duration-(--t-fast) outline-none placeholder:text-text-3 hover:border-input focus:border-ring focus:ring-3 focus:ring-ring/15"
            />
            {!focused && !query && <Kbd className="pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 sm:inline-flex">/</Kbd>}
          </div>
        </PopoverAnchor>
        <PopoverContent
          align="start"
          sideOffset={8}
          onOpenAutoFocus={(e) => e.preventDefault()}
          onInteractOutside={(e) => e.preventDefault()}
          className="glass w-(--radix-popover-trigger-width) p-1"
        >
          <CommandList>
            <CommandEmpty className="py-4 text-muted-foreground">No Item matches that name.</CommandEmpty>
            <CommandGroup className="p-0">
              {shown.map((n) => (
                <CommandItem key={n.id} value={n.id} onSelect={() => onChoose(n)} onMouseDown={(e) => e.preventDefault()} className="min-h-11 gap-3 rounded-md px-3">
                  <span className="glyph" data-kind={n.kind} />
                  <span className="min-w-0">
                    <span className="block">{n.name}</span>
                    <span className="block truncate text-xs text-muted-foreground">{n.label || kindName(n.kind)}</span>
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </PopoverContent>
      </Popover>
    </Command>
  );
}

function Warnings({ warnings }: { warnings: string[] }) {
  if (!warnings.length) return null;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" className="glass pointer-events-auto ml-auto h-8 rounded-full border-warn/30 px-3 text-warn hover:bg-warn/10 hover:text-warn aria-expanded:bg-warn/10 sm:order-last sm:ml-0 sm:h-10 sm:px-4">
          <TriangleAlertIcon data-icon="inline-start" aria-hidden />
          {warnings.length} warning{warnings.length > 1 ? "s" : ""}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="glass w-[min(420px,calc(100vw-2rem))]">
        <PopoverHeader>
          <PopoverTitle>Scan warnings</PopoverTitle>
        </PopoverHeader>
        <ul className="mt-2 flex max-h-[50vh] list-disc flex-col gap-2 overflow-y-auto pl-4 text-[13px] leading-relaxed text-muted-foreground">
          {warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
