import { Button } from "@/components/ui/button";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";

const Code = ({ children }: { children: string }) => <code className="rounded-sm border border-line-1 bg-surface-3 px-1.5 py-px font-mono whitespace-nowrap text-xs text-foreground">{children}</code>;

export function Loading() {
  return (
    <div role="status" className="fixed inset-0 grid place-content-center justify-items-center gap-3 text-[13px] text-text-2">
      <span className="pulse-star" aria-hidden />
      Charting your setup
    </div>
  );
}

export function Nothing() {
  return (
    <Empty className="fixed inset-0">
      <EmptyHeader>
        <span className="pulse-star [animation:none]" aria-hidden />
        <EmptyTitle className="font-serif text-[26px] leading-[1.15] font-normal tracking-[-0.005em]">Nothing to chart yet</EmptyTitle>
        <EmptyDescription>
          This scan found no Items. Run <Code>constellation scan</Code> on a Claude Code setup, then reload this page.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

export function Failed({ detail, onRetry }: { detail: string; onRetry: () => void }) {
  return (
    <Empty className="fixed inset-0" role="alert">
      <EmptyHeader>
        <span className="size-2.5 rounded-full border border-dashed border-text-3" aria-hidden />
        <EmptyTitle className="font-serif text-[26px] leading-[1.15] font-normal tracking-[-0.005em]">Could not load the constellation</EmptyTitle>
        <EmptyDescription>
          {detail}. Check that <Code>constellation open</Code> is still running, then try again.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button variant="outline" className="h-10 rounded-lg px-6" onClick={onRetry} autoFocus>
          Try again
        </Button>
      </EmptyContent>
    </Empty>
  );
}
