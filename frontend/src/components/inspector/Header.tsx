import { Badge } from "@/components/ui/badge";
import { kindName, type GNode, type Model } from "@/graph/model";
import { cn } from "@/lib/utils";

export function Header({ item, model }: { item: GNode; model: Model }) {
  return (
    <>
      <p className="flex min-h-7 flex-wrap items-center gap-x-2 gap-y-1 pr-10 text-xs font-medium tracking-[0.02em] text-text-3">
        <span className="glyph" data-kind={item.kind} />
        {kindName(item.kind)}
        {item.origin && <span className="font-normal">from {item.origin}</span>}
        {item.scope && <Badge>{item.scope === "project" ? (item.project && model.projects[item.project] ? `Project · ${model.projects[item.project]}` : "Project") : "Global"}</Badge>}
        {item.disabled && <Badge variant="warn">Switched off</Badge>}
      </p>
      <h2 id="i-name" tabIndex={-1} className={cn("mt-2 mb-1 font-serif text-[26px] leading-[1.1] tracking-[-0.01em] [overflow-wrap:anywhere] outline-none sm:text-[30px]", item.disabled && "text-text-2")}>
        {item.name}
      </h2>
      {item.label && <p className="text-[15px] leading-[1.45] tracking-[-0.005em] text-text-2">{item.label}</p>}
    </>
  );
}
