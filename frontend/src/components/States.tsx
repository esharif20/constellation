import { Button } from "@/components/ui/button";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";

const Code = ({ children }: { children: string }) => <code className="rounded bg-muted px-1.5 py-px text-[13px] text-foreground">{children}</code>;

export function Loading() {
  return (
    <div role="status" className="fixed inset-0 grid place-content-center justify-items-center gap-3 text-sm text-muted-foreground">
      <span className="pulse-star" aria-hidden />
      Charting your setup
    </div>
  );
}

export function Nothing() {
  return (
    <Empty className="fixed inset-0">
      <EmptyHeader>
        <EmptyTitle className="font-serif text-[28px] font-normal italic">Nothing to chart yet</EmptyTitle>
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
        <EmptyTitle className="font-serif text-[28px] font-normal italic">Could not load the constellation</EmptyTitle>
        <EmptyDescription>
          {detail}. Check that <Code>constellation open</Code> is still running, then try again.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button variant="outline" className="h-10 rounded-full px-6" onClick={onRetry} autoFocus>
          Try again
        </Button>
      </EmptyContent>
    </Empty>
  );
}
