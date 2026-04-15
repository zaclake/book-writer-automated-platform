import { toast as sonnerToast } from 'sonner'

export type AppToast = {
  title?: string
  description?: string
  variant?: 'default' | 'destructive'
}

/**
 * Unified toast API for the app.
 *
 * We standardize on `sonner` (rendered in `src/components/layout/AppLayout.tsx`).
 * This wrapper exists because some parts of the codebase previously used a
 * custom `use-toast` store that was not rendered.
 */
export function toast({ title, description, variant = 'default' }: AppToast) {
  const resolvedTitle = title?.trim() || (variant === 'destructive' ? 'Something went wrong' : 'Notice')

  if (variant === 'destructive') {
    return sonnerToast.error(resolvedTitle, { description })
  }

  return sonnerToast(resolvedTitle, { description })
}

export function useAppToast() {
  return {
    toast,
    success: (title: string, description?: string) => sonnerToast.success(title, { description }),
    error: (title: string, description?: string) => sonnerToast.error(title, { description }),
    info: (title: string, description?: string) => sonnerToast(title, { description }),
  }
}

