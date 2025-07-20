import React, { useState, useCallback } from 'react'

export interface Toast {
  id?: string
  title?: string
  description?: string
  variant?: 'default' | 'destructive'
}

const toasts: Toast[] = []
let listeners: Array<(toasts: Toast[]) => void> = []

let memoryState: { toasts: Toast[] } = { toasts }

function dispatch(action: { type: string; toast?: Toast; toastId?: string }) {
  switch (action.type) {
    case 'ADD_TOAST':
      memoryState.toasts = [action.toast!, ...memoryState.toasts]
      break
    case 'REMOVE_TOAST':
      memoryState.toasts = memoryState.toasts.filter(
        (t) => t.id !== action.toastId
      )
      break
  }
  
  listeners.forEach((listener) => {
    listener(memoryState.toasts)
  })
}

let count = 0

function genId() {
  count = (count + 1) % Number.MAX_VALUE
  return count.toString()
}

const toast = ({ ...props }: Toast) => {
  const id = genId()

  const update = (props: Toast) =>
    dispatch({
      type: 'UPDATE_TOAST',
      toast: { ...props, id },
    })

  const dismiss = () => dispatch({ type: 'REMOVE_TOAST', toastId: id })

  dispatch({
    type: 'ADD_TOAST',
    toast: {
      ...props,
      id,
    },
  })

  // Auto dismiss after 5 seconds
  setTimeout(() => {
    dismiss()
  }, 5000)

  return {
    id: id,
    dismiss,
    update,
  }
}

function useToast() {
  const [state, setState] = useState<{ toasts: Toast[] }>(memoryState)

  const subscribe = useCallback((listener: (toasts: Toast[]) => void) => {
    listeners.push(listener)
    return () => {
      const index = listeners.indexOf(listener)
      if (index > -1) {
        listeners.splice(index, 1)
      }
    }
  }, [])

  React.useEffect(() => {
    listeners.push(setState)
    return () => {
      const index = listeners.indexOf(setState)
      if (index > -1) {
        listeners.splice(index, 1)
      }
    }
  }, [])

  return {
    ...state,
    toast,
    dismiss: (toastId?: string) => dispatch({ type: 'REMOVE_TOAST', toastId }),
  }
}

export { useToast, toast } 