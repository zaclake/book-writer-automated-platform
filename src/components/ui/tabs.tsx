import React, { createContext, useContext, useState } from 'react'
import { cn } from '@/lib/utils'

interface TabsContextValue {
  activeTab: string
  setActiveTab: (value: string) => void
  orientation?: 'horizontal' | 'vertical'
}

const TabsContext = createContext<TabsContextValue | undefined>(undefined)

interface TabsProps {
  defaultValue?: string
  value?: string
  onValueChange?: (value: string) => void
  orientation?: 'horizontal' | 'vertical'
  className?: string
  children: React.ReactNode
}

interface TabsListProps {
  className?: string
  children: React.ReactNode
}

interface TabsTriggerProps {
  value: string
  disabled?: boolean
  className?: string
  children: React.ReactNode
  badge?: string | number
  icon?: React.ReactNode
}

interface TabsContentProps {
  value: string
  className?: string
  children: React.ReactNode
}

// Main Tabs component
export const Tabs: React.FC<TabsProps> = ({
  defaultValue = '',
  value,
  onValueChange,
  orientation = 'horizontal',
  className,
  children
}) => {
  const [internalValue, setInternalValue] = useState(defaultValue)
  
  const activeTab = value !== undefined ? value : internalValue
  
  const setActiveTab = (newValue: string) => {
    if (value === undefined) {
      setInternalValue(newValue)
    }
    onValueChange?.(newValue)
  }

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab, orientation }}>
      <div className={cn('w-full', className)}>
        {children}
      </div>
    </TabsContext.Provider>
  )
}

// Tabs list component
export const TabsList: React.FC<TabsListProps> = ({ className, children }) => {
  const context = useContext(TabsContext)
  if (!context) throw new Error('TabsList must be used within Tabs')
  
  const { orientation } = context

  return (
    <div
      className={cn(
        'inline-flex items-center justify-center rounded-lg bg-gray-100 p-1 text-gray-500',
        orientation === 'vertical' ? 'flex-col h-fit' : 'h-10',
        className
      )}
    >
      {children}
    </div>
  )
}

// Tabs trigger component
export const TabsTrigger: React.FC<TabsTriggerProps> = ({
  value,
  disabled = false,
  className,
  children,
  badge,
  icon
}) => {
  const context = useContext(TabsContext)
  if (!context) throw new Error('TabsTrigger must be used within Tabs')
  
  const { activeTab, setActiveTab, orientation } = context
  const isActive = activeTab === value

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => !disabled && setActiveTab(value)}
      className={cn(
        'inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium ring-offset-white transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
        orientation === 'vertical' ? 'w-full' : '',
        isActive
          ? 'bg-white text-gray-950 shadow-sm'
          : 'hover:bg-gray-200 hover:text-gray-900',
        disabled && 'opacity-50 cursor-not-allowed',
        className
      )}
    >
      {icon && <span className="mr-2">{icon}</span>}
      <span>{children}</span>
      {badge && (
        <span className={cn(
          'ml-2 inline-flex items-center justify-center rounded-full text-xs font-medium',
          'h-5 min-w-[20px] px-1',
          isActive 
            ? 'bg-blue-100 text-blue-600' 
            : 'bg-gray-200 text-gray-600'
        )}>
          {badge}
        </span>
      )}
    </button>
  )
}

// Tabs content component
export const TabsContent: React.FC<TabsContentProps> = ({
  value,
  className,
  children
}) => {
  const context = useContext(TabsContext)
  if (!context) throw new Error('TabsContent must be used within Tabs')
  
  const { activeTab } = context
  
  if (activeTab !== value) return null

  return (
    <div
      className={cn(
        'mt-2 ring-offset-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2',
        'animate-in fade-in-50 duration-200',
        className
      )}
    >
      {children}
    </div>
  )
}

// Enhanced tabs with card styling
interface CardTabsProps extends Omit<TabsProps, 'className'> {
  variant?: 'default' | 'card' | 'pills'
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export const CardTabs: React.FC<CardTabsProps> = ({
  variant = 'card',
  size = 'md',
  className,
  children,
  ...props
}) => {
  return (
    <div className={cn(
      'w-full',
      variant === 'card' && 'bg-white rounded-lg border border-gray-200 overflow-hidden',
      className
    )}>
      <Tabs {...props}>
        {children}
      </Tabs>
    </div>
  )
}

// Tab panel with improved styling
interface TabPanelProps {
  value: string
  className?: string
  children: React.ReactNode
  padding?: boolean
}

export const TabPanel: React.FC<TabPanelProps> = ({
  value,
  className,
  children,
  padding = true
}) => {
  return (
    <TabsContent
      value={value}
      className={cn(
        'outline-none',
        padding && 'p-6',
        className
      )}
    >
      {children}
    </TabsContent>
  )
}

// Tabs with navigation styling (like browser tabs)
interface NavTabsProps extends TabsProps {
  variant?: 'line' | 'enclosed' | 'soft-rounded'
}

export const NavTabs: React.FC<NavTabsProps> = ({
  variant = 'line',
  className,
  children,
  ...props
}) => {
  return (
    <div className={cn(
      'w-full',
      variant === 'line' && 'border-b border-gray-200',
      className
    )}>
      <Tabs {...props}>
        {children}
      </Tabs>
    </div>
  )
}

interface NavTabsListProps extends TabsListProps {
  variant?: 'line' | 'enclosed' | 'soft-rounded'
}

export const NavTabsList: React.FC<NavTabsListProps> = ({
  variant = 'line',
  className,
  children
}) => {
  return (
    <div
      className={cn(
        'flex items-center',
        variant === 'line' && 'space-x-8 border-b border-gray-200',
        variant === 'enclosed' && 'bg-gray-50 p-1 rounded-lg',
        variant === 'soft-rounded' && 'space-x-2',
        className
      )}
    >
      {children}
    </div>
  )
}

interface NavTabsTriggerProps extends TabsTriggerProps {
  variant?: 'line' | 'enclosed' | 'soft-rounded'
}

export const NavTabsTrigger: React.FC<NavTabsTriggerProps> = ({
  variant = 'line',
  value,
  className,
  children,
  ...props
}) => {
  const context = useContext(TabsContext)
  if (!context) throw new Error('NavTabsTrigger must be used within Tabs')
  
  const { activeTab, setActiveTab } = context
  const isActive = activeTab === value

  const variantClasses = {
    line: cn(
      'border-b-2 pb-2 px-1 text-sm font-medium transition-colors',
      isActive
        ? 'border-blue-500 text-blue-600'
        : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
    ),
    enclosed: cn(
      'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
      isActive
        ? 'bg-white text-gray-900 shadow-sm'
        : 'text-gray-600 hover:text-gray-900'
    ),
    'soft-rounded': cn(
      'px-3 py-1.5 text-sm font-medium rounded-lg transition-colors',
      isActive
        ? 'bg-blue-100 text-blue-700'
        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
    )
  }

  return (
    <button
      type="button"
      onClick={() => setActiveTab(value)}
      className={cn(
        'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
        variantClasses[variant],
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
} 