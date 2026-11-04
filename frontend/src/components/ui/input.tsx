import * as React from "react"
import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full min-w-0 rounded-lg border border-input bg-surface-2/94 px-2.5 py-1 text-base transition-[border-color,box-shadow] duration-(--t-fast) outline-none hover:border-line-3 file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-text-3 focus-visible:border-indigo-bright focus-visible:shadow-[0_0_0_3px_rgb(130_143_255/0.25)] disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-surface-1 disabled:text-text-4 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
        className
      )}
      {...props}
    />
  )
}

export { Input }
