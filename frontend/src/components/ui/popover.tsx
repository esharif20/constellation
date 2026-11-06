import * as React from "react"
import { cn } from "@/lib/utils"
import { Popover as PopoverPrimitive } from "radix-ui"
import { XIcon } from "lucide-react"
import { RANK, type Why } from "@/lib/dismiss"
import { useLayer } from "@/lib/useLayer"

// Every popover joins the dismiss stack (lib/dismiss.ts): a click or tap outside closes it even over the canvas,
// opening one closes the other, and a close by pointer leaves focus where the user pointed.
// A popover given `open` without `onOpenChange` (the search results) is driven from outside and is not managed.
const Ctx = React.createContext<{ content: React.RefObject<HTMLDivElement | null>; trigger: React.RefObject<HTMLButtonElement | null>; why: React.RefObject<Why | null> } | null>(null)

function Popover({
  open: openProp,
  onOpenChange,
  defaultOpen,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Root>) {
  const [own, setOwn] = React.useState(!!defaultOpen)
  const content = React.useRef<HTMLDivElement>(null), trigger = React.useRef<HTMLButtonElement>(null), why = React.useRef<Why | null>(null)
  const open = openProp ?? own
  const set = (o: boolean) => { setOwn(o); onOpenChange?.(o) }
  useLayer(open && (openProp === undefined || !!onOpenChange), {
    rank: RANK.popover,
    close: (w) => { why.current = w; set(false) },
    inside: () => [content.current, trigger.current],
  })
  const ctx = React.useMemo(() => ({ content, trigger, why }), [])
  return (
    <Ctx.Provider value={ctx}>
      <PopoverPrimitive.Root data-slot="popover" open={open} onOpenChange={(o) => { why.current = null; set(o) }} {...props} />
    </Ctx.Provider>
  )
}

function PopoverTrigger({
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger data-slot="popover-trigger" ref={React.useContext(Ctx)?.trigger} {...props} />
}

function PopoverContent({
  className,
  align = "center",
  sideOffset = 4,
  closeButton = true,
  children,
  onCloseAutoFocus,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content> & { closeButton?: boolean }) {
  const ctx = React.useContext(Ctx)
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-slot="popover-content"
        ref={ctx?.content}
        onCloseAutoFocus={(e) => {
          onCloseAutoFocus?.(e)
          if (ctx?.why.current && ctx.why.current !== "escape") e.preventDefault() // closed by a click elsewhere: do not pull focus back to the button
        }}
        align={align}
        sideOffset={sideOffset}
        className={cn(
          "relative z-50 flex w-72 origin-(--radix-popover-content-transform-origin) flex-col gap-2.5 rounded-xl border border-line-1 bg-popover p-2.5 text-sm text-popover-foreground shadow-(--shadow-float) outline-hidden duration-(--m-pop-in) ease-(--ease-out) data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-[0.98] data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-[0.98] data-[state=closed]:duration-(--m-pop-out) data-[state=closed]:ease-(--ease-in)",
          className
        )}
        {...props}
      >
        {children}
        {closeButton && (
          <PopoverPrimitive.Close aria-label="Close" className="absolute top-1 right-1 grid size-10 cursor-pointer place-items-center rounded-md text-text-3 transition-colors hover:bg-foreground/5 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring sm:size-8">
            <XIcon className="size-4" aria-hidden />
          </PopoverPrimitive.Close>
        )}
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  )
}

function PopoverAnchor({
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Anchor>) {
  return <PopoverPrimitive.Anchor data-slot="popover-anchor" {...props} />
}

function PopoverHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="popover-header"
      className={cn("flex flex-col gap-0.5 pr-8 text-sm", className)}
      {...props}
    />
  )
}

function PopoverTitle({ className, ...props }: React.ComponentProps<"h2">) {
  return (
    <div
      data-slot="popover-title"
      className={cn("text-[15px] leading-[1.3] font-semibold tracking-[-0.01em]", className)}
      {...props}
    />
  )
}

function PopoverDescription({
  className,
  ...props
}: React.ComponentProps<"p">) {
  return (
    <p
      data-slot="popover-description"
      className={cn("text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Popover,
  PopoverAnchor,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
}
