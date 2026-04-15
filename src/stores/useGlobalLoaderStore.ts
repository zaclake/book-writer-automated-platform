import { create } from 'zustand'

export type GlobalLoaderSize = 'sm' | 'md' | 'lg'

export interface GlobalLoaderConfig {
  title?: string
  stage?: string
  message?: string
  progress?: number
  showProgress?: boolean
  size?: GlobalLoaderSize
  fullScreen?: boolean
  safeToLeave?: boolean
  canMinimize?: boolean
  customMessages?: string[]
  timeoutMs?: number
  onTimeout?: (() => void) | null
}

export interface GlobalLoaderState extends GlobalLoaderConfig {
  isVisible: boolean
  activeCount: number
  minimized: boolean
  startedAt: number | null
  size: GlobalLoaderSize
  fullScreen: boolean
  safeToLeave: boolean
  canMinimize: boolean
  show: (config: GlobalLoaderConfig) => void
  update: (config: Partial<GlobalLoaderConfig>) => void
  hide: () => void
  forceHide: () => void
  minimize: () => void
  restore: () => void
}

const INITIAL: Pick<GlobalLoaderState, 'title' | 'stage' | 'message' | 'progress' | 'showProgress' | 'size' | 'fullScreen' | 'safeToLeave' | 'canMinimize' | 'customMessages' | 'timeoutMs' | 'onTimeout' | 'startedAt' | 'minimized'> = {
  title: undefined,
  stage: undefined,
  message: undefined,
  progress: undefined,
  showProgress: true,
  size: 'md',
  fullScreen: true,
  safeToLeave: false,
  canMinimize: true,
  customMessages: undefined,
  timeoutMs: 0,
  onTimeout: null,
  startedAt: null,
  minimized: false,
}

export const useGlobalLoaderStore = create<GlobalLoaderState>((set) => ({
  isVisible: false,
  activeCount: 0,
  ...INITIAL,
  show: (config) =>
    set((state) => ({
      isVisible: true,
      minimized: false,
      activeCount: (state.activeCount || 0) + 1,
      startedAt: state.startedAt ?? Date.now(),
      title: config.title,
      stage: config.stage,
      message: config.message,
      progress: config.progress,
      showProgress: config.showProgress ?? true,
      size: config.size ?? 'md',
      fullScreen: config.fullScreen ?? true,
      safeToLeave: config.safeToLeave ?? false,
      canMinimize: config.canMinimize ?? true,
      customMessages: config.customMessages,
      timeoutMs: config.timeoutMs,
      onTimeout: config.onTimeout ?? null,
    })),
  update: (config) =>
    set((state) => ({
      ...state,
      ...config,
      isVisible: config.isVisible !== undefined ? config.isVisible : state.isVisible,
    })),
  hide: () =>
    set((state) => {
      const nextCount = Math.max(0, (state.activeCount || 0) - 1)
      if (nextCount === 0) {
        return { isVisible: false, activeCount: 0, minimized: false, ...INITIAL }
      }
      return { ...state, activeCount: nextCount, isVisible: true }
    }),
  forceHide: () =>
    set(() => ({ isVisible: false, activeCount: 0, minimized: false, ...INITIAL })),
  minimize: () =>
    set((state) => ({ ...state, minimized: true })),
  restore: () =>
    set((state) => ({ ...state, minimized: false })),
}))

export const GlobalLoader = {
  show: (config: GlobalLoaderConfig) =>
    useGlobalLoaderStore.getState().show(config),
  update: (config: Partial<GlobalLoaderConfig>) =>
    useGlobalLoaderStore.getState().update(config),
  hide: () => useGlobalLoaderStore.getState().hide(),
  forceHide: () => useGlobalLoaderStore.getState().forceHide(),
  minimize: () => useGlobalLoaderStore.getState().minimize(),
  restore: () => useGlobalLoaderStore.getState().restore(),
}
