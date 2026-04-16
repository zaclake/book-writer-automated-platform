import * as React from "react"
import { cn } from "@/lib/utils"
import { lockScroll, unlockScroll } from "@/lib/scroll-lock"

const Dialog = ({ open, onOpenChange, children }: {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children: React.ReactNode
}) => {
  const [internalOpen, setInternalOpen] = React.useState(false)
  const isOpen = open !== undefined ? open : internalOpen
  const setOpen = onOpenChange || setInternalOpen

  return (
    <DialogContext.Provider value={{ open: isOpen, onOpenChange: setOpen }}>
      {children}
    </DialogContext.Provider>
  )
}

const DialogContext = React.createContext<{
  open: boolean
  onOpenChange: (open: boolean) => void
}>({
  open: false,
  onOpenChange: () => {}
})

const DialogTrigger = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean
  }
>(({ className, children, asChild = false, ...props }, ref) => {
  const { onOpenChange } = React.useContext(DialogContext)

  if (asChild) {
    return React.cloneElement(children as React.ReactElement, {
      onClick: (e: React.MouseEvent) => {
        onOpenChange(true)
        const originalOnClick = (children as React.ReactElement).props.onClick
        if (originalOnClick) originalOnClick(e)
      }
    })
  }

  return (
    <button
      ref={ref}
      className={className}
      onClick={() => onOpenChange(true)}
      {...props}
    >
      {children}
    </button>
  )
})
DialogTrigger.displayName = "DialogTrigger"

const DialogContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, children, ...props }, ref) => {
  const { open, onOpenChange } = React.useContext(DialogContext)

  React.useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onOpenChange(false)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onOpenChange])

  React.useEffect(() => {
    if (!open) return
    lockScroll()
    return () => { unlockScroll() }
  }, [open])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start sm:items-center justify-center p-4 sm:p-6"
      style={{
        paddingTop: 'calc(env(safe-area-inset-top) + 1rem)',
        paddingBottom: 'calc(env(safe-area-inset-bottom) + 1rem)',
      }}
    >
      {/* Overlay */}
      <div 
        className="fixed inset-0 bg-black/50" 
        onClick={() => onOpenChange(false)}
      />
      
      {/* Content */}
      <div
        ref={ref}
        className={cn(
          "relative bg-white rounded-lg shadow-lg p-6 w-full max-w-md max-h-[85vh] sm:max-h-[90vh] overflow-y-auto",
          className
        )}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        {...props}
      >
        {children}
      </div>
    </div>
  )
})
DialogContent.displayName = "DialogContent"

const DialogHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col space-y-1.5 text-center sm:text-left mb-4", className)}
    {...props}
  />
))
DialogHeader.displayName = "DialogHeader"

const DialogTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h2
    ref={ref}
    className={cn("text-lg font-semibold leading-none tracking-tight", className)}
    {...props}
  />
))
DialogTitle.displayName = "DialogTitle"

const DialogDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-gray-500", className)}
    {...props}
  />
))
DialogDescription.displayName = "DialogDescription"

export {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} 

// Optional footer container for actions
export const DialogFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center justify-end gap-2 mt-4", className)}
    {...props}
  />
))
DialogFooter.displayName = "DialogFooter"