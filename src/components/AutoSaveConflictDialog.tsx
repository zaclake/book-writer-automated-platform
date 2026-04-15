'use client'

import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'

export function AutoSaveConflictDialog(props: {
  open: boolean
  onOpenChange: (open: boolean) => void
  localPreview: string
  onUseLocal: () => void
  onDiscard: () => void
}) {
  const { open, onOpenChange, localPreview, onUseLocal, onDiscard } = props

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Conflict detected</DialogTitle>
        </DialogHeader>

        <div className="text-sm text-muted-foreground">
          Your chapter changed on the server while you were editing. Choose how to resolve it.
        </div>

        <div className="mt-3">
          <div className="text-sm font-medium mb-1">Your local changes</div>
          <ScrollArea className="h-[40vh] rounded-md border">
            <pre className="whitespace-pre-wrap p-3 text-xs">{localPreview}</pre>
          </ScrollArea>
        </div>

        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={() => {
              onDiscard()
              onOpenChange(false)
            }}
            aria-label="Discard local changes"
          >
            Discard local changes
          </Button>
          <Button
            onClick={() => {
              onUseLocal()
              onOpenChange(false)
            }}
            aria-label="Use local changes and overwrite server"
          >
            Use local changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

