import React from 'react'
import { cn } from '@/lib/utils'

interface StepperStep {
  id: string
  title: string
  description?: string
  status: 'pending' | 'current' | 'completed' | 'error'
  optional?: boolean
}

interface StepperProps {
  steps: StepperStep[]
  orientation?: 'horizontal' | 'vertical'
  className?: string
  onStepClick?: (step: StepperStep, index: number) => void
  allowClickableSteps?: boolean
}

const Stepper: React.FC<StepperProps> = ({
  steps,
  orientation = 'horizontal',
  className,
  onStepClick,
  allowClickableSteps = false
}) => {
  const isHorizontal = orientation === 'horizontal'

  const getStepIcon = (step: StepperStep, index: number) => {
    switch (step.status) {
      case 'completed':
        return (
          <div className="w-8 h-8 bg-green-600 rounded-full flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
          </div>
        )
      case 'current':
        return (
          <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center">
            <span className="text-white text-sm font-semibold">{index + 1}</span>
          </div>
        )
      case 'error':
        return (
          <div className="w-8 h-8 bg-red-600 rounded-full flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </div>
        )
      default:
        return (
          <div className="w-8 h-8 bg-gray-300 rounded-full flex items-center justify-center">
            <span className="text-gray-600 text-sm font-semibold">{index + 1}</span>
          </div>
        )
    }
  }

  const getStepConnector = (index: number, step: StepperStep) => {
    if (index === steps.length - 1) return null

    const connectorClass = cn(
      'transition-colors',
      isHorizontal ? 'flex-1 h-0.5 mx-4' : 'w-0.5 h-8 mx-4',
      step.status === 'completed' ? 'bg-green-600' : 'bg-gray-300'
    )

    return <div className={connectorClass} />
  }

  const handleStepClick = (step: StepperStep, index: number) => {
    if (allowClickableSteps && onStepClick) {
      onStepClick(step, index)
    }
  }

  return (
    <div className={cn(
      'flex',
      isHorizontal ? 'items-center' : 'flex-col',
      className
    )}>
      {steps.map((step, index) => (
        <React.Fragment key={step.id}>
          <div
            className={cn(
              'flex items-center transition-all',
              isHorizontal ? 'flex-row' : 'flex-col text-center',
              allowClickableSteps && step.status !== 'pending' ? 'cursor-pointer hover:opacity-75' : '',
              !isHorizontal ? 'mb-4' : ''
            )}
            onClick={() => handleStepClick(step, index)}
          >
            {/* Step Icon */}
            <div className="flex-shrink-0">
              {getStepIcon(step, index)}
            </div>

            {/* Step Content */}
            <div className={cn(
              'ml-4',
              isHorizontal ? 'text-left' : 'text-center ml-0 mt-2'
            )}>
              <div className={cn(
                'text-sm font-medium',
                step.status === 'current' ? 'text-blue-600' :
                step.status === 'completed' ? 'text-green-600' :
                step.status === 'error' ? 'text-red-600' :
                'text-gray-500'
              )}>
                {step.title}
                {step.optional && (
                  <span className="ml-1 text-xs text-gray-400">(Optional)</span>
                )}
              </div>
              
              {step.description && (
                <div className={cn(
                  'text-xs mt-1',
                  step.status === 'current' ? 'text-blue-500' :
                  step.status === 'completed' ? 'text-green-500' :
                  step.status === 'error' ? 'text-red-500' :
                  'text-gray-400'
                )}>
                  {step.description}
                </div>
              )}
            </div>
          </div>

          {/* Connector */}
          {getStepConnector(index, step)}
        </React.Fragment>
      ))}
    </div>
  )
}

export default Stepper

// Hook for managing stepper state
export function useStepper(initialSteps: StepperStep[]) {
  const [steps, setSteps] = React.useState<StepperStep[]>(initialSteps)
  const [currentStepIndex, setCurrentStepIndex] = React.useState(0)

  const updateStepStatus = (stepId: string, status: StepperStep['status']) => {
    setSteps(prevSteps =>
      prevSteps.map(step =>
        step.id === stepId ? { ...step, status } : step
      )
    )
  }

  const goToStep = (index: number) => {
    if (index >= 0 && index < steps.length) {
      // Update current step
      setSteps(prevSteps =>
        prevSteps.map((step, i) => ({
          ...step,
          status: i === index ? 'current' : 
                  i < index ? 'completed' : 'pending'
        }))
      )
      setCurrentStepIndex(index)
    }
  }

  const nextStep = () => {
    if (currentStepIndex < steps.length - 1) {
      goToStep(currentStepIndex + 1)
    }
  }

  const previousStep = () => {
    if (currentStepIndex > 0) {
      goToStep(currentStepIndex - 1)
    }
  }

  const completeStep = (stepId?: string) => {
    const targetStepId = stepId || steps[currentStepIndex]?.id
    if (targetStepId) {
      updateStepStatus(targetStepId, 'completed')
    }
  }

  const markStepError = (stepId?: string) => {
    const targetStepId = stepId || steps[currentStepIndex]?.id
    if (targetStepId) {
      updateStepStatus(targetStepId, 'error')
    }
  }

  const reset = () => {
    setSteps(initialSteps)
    setCurrentStepIndex(0)
  }

  const isFirstStep = currentStepIndex === 0
  const isLastStep = currentStepIndex === steps.length - 1
  const currentStep = steps[currentStepIndex]

  return {
    steps,
    currentStepIndex,
    currentStep,
    isFirstStep,
    isLastStep,
    goToStep,
    nextStep,
    previousStep,
    completeStep,
    markStepError,
    updateStepStatus,
    reset
  }
} 