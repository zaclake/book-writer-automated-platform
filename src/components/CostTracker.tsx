'use client'

interface CostTrackerProps {
  metrics: {
    total_cost?: number
    average_cost_per_chapter?: number
    monthly_cost?: number
    budget_remaining?: number
    cost_trend?: Array<{ date: string; cost: number }>
  } | null
}

export function CostTracker({ metrics }: CostTrackerProps) {
  if (!metrics) {
    return (
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Cost Tracking</h2>
        <div className="text-center py-8">
          <div className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mx-auto mb-2"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2 mx-auto"></div>
          </div>
        </div>
      </div>
    )
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 4,
      maximumFractionDigits: 4
    }).format(amount)
  }

  const getBudgetColor = (remaining: number) => {
    if (remaining > 50) return 'text-green-600'
    if (remaining > 20) return 'text-yellow-600'
    return 'text-red-600'
  }

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Cost Tracking</h2>
      
      <div className="space-y-4">
        {/* Total Cost */}
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-600">Total Cost</span>
          <span className="text-lg font-semibold text-gray-900">
            {formatCurrency(metrics.total_cost || 0)}
          </span>
        </div>

        {/* Average per Chapter */}
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-600">Avg per Chapter</span>
          <span className="text-sm font-medium text-gray-700">
            {formatCurrency(metrics.average_cost_per_chapter || 0)}
          </span>
        </div>

        {/* Monthly Cost */}
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-600">This Month</span>
          <span className="text-sm font-medium text-gray-700">
            {formatCurrency(metrics.monthly_cost || 0)}
          </span>
        </div>

        {/* Budget Status */}
        {metrics.budget_remaining !== undefined && (
          <div className="pt-4 border-t">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-gray-600">Budget Remaining</span>
              <span className={`text-sm font-medium ${getBudgetColor(metrics.budget_remaining)}`}>
                {metrics.budget_remaining.toFixed(1)}%
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div 
                className={`h-2 rounded-full transition-all duration-300 ${
                  metrics.budget_remaining > 50 
                    ? 'bg-green-500' 
                    : metrics.budget_remaining > 20 
                    ? 'bg-yellow-500' 
                    : 'bg-red-500'
                }`}
                style={{ width: `${Math.max(0, Math.min(100, metrics.budget_remaining))}%` }}
              ></div>
            </div>
          </div>
        )}

        {/* Cost Projections */}
        <div className="pt-4 border-t">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Projections</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">10 chapters:</span>
              <span className="text-gray-900">
                {formatCurrency((metrics.average_cost_per_chapter || 0) * 10)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">50 chapters:</span>
              <span className="text-gray-900">
                {formatCurrency((metrics.average_cost_per_chapter || 0) * 50)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Full novel (100):</span>
              <span className="text-gray-900">
                {formatCurrency((metrics.average_cost_per_chapter || 0) * 100)}
              </span>
            </div>
          </div>
        </div>

        {/* Cost Efficiency */}
        <div className="pt-4 border-t">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Efficiency</h3>
          <div className="text-xs text-gray-500">
            {metrics.average_cost_per_chapter && metrics.average_cost_per_chapter > 0 && (
              <p>
                ~{((metrics.average_cost_per_chapter || 0) * 1000).toFixed(2)} 
                <span className="ml-1">cents per 1000 words</span>
              </p>
            )}
            <p className="mt-1">
              Estimated 50x more cost-efficient than manual writing
            </p>
          </div>
        </div>
      </div>
    </div>
  )
} 