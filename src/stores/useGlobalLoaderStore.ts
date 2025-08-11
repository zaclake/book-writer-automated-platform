import { create } from 'zustand'

export type GlobalLoaderSize = 'sm' | 'md' | 'lg'

export interface GlobalLoaderState {
  isVisible: boolean
  title?: string
  stage?: string
  message?: string
  progress?: number
  showProgress?: boolean
  size: GlobalLoaderSize
  fullScreen: boolean
  customMessages?: string[]
  timeoutMs?: number
  onTimeout?: (() => void) | null
  // Control
  show: (config: Partial<Omit<GlobalLoaderState, 'isVisible' | 'show' | 'update' | 'hide'>>) => void
  update: (config: Partial<Omit<GlobalLoaderState, 'show' | 'update' | 'hide'>>) => void
  hide: () => void
}

export const useGlobalLoaderStore = create<GlobalLoaderState>((set) => ({
  isVisible: false,
  title: undefined,
  stage: undefined,
  message: undefined,
  progress: undefined,
  showProgress: true,
  size: 'md',
  fullScreen: true,
  customMessages: undefined,
  timeoutMs: 0,
  onTimeout: null,
  show: (config) =>
    set(() => ({
      isVisible: true,
      title: config.title,
      stage: config.stage,
      message: config.message,
      progress: config.progress,
      showProgress: config.showProgress ?? true,
      size: config.size ?? 'md',
      fullScreen: config.fullScreen ?? true,
      customMessages: config.customMessages,
      timeoutMs: config.timeoutMs,
      onTimeout: config.onTimeout ?? null,
    })),
  update: (config) =>
    set((state) => ({
      ...state,
      ...config,
      isVisible: config.isVisible ?? state.isVisible,
    })),
  hide: () =>
    set(() => ({
      isVisible: false,
      title: undefined,
      stage: undefined,
      message: undefined,
      progress: undefined,
      customMessages: undefined,
      timeoutMs: 0,
      onTimeout: null,
    })),
}))

// Convenience helpers for non-hook usage
export const GlobalLoader = {
  show: (config: Parameters<GlobalLoaderState['show']>[0]) =>
    useGlobalLoaderStore.getState().show(config),
  update: (config: Parameters<GlobalLoaderState['update']>[0]) =>
    useGlobalLoaderStore.getState().update(config),
  hide: () => useGlobalLoaderStore.getState().hide(),
}


