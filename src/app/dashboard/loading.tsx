export default function DashboardLoading() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-indigo-950 to-gray-900">
      <div className="flex items-center justify-center min-h-[40vh] px-6">
        <div className="text-center">
          <div className="w-10 h-10 mx-auto border-4 border-white/20 border-t-white rounded-full animate-spin" />
          <p className="mt-4 text-sm text-white/60">Loading your studio...</p>
        </div>
      </div>
      <div className="bg-gray-50 min-h-[60vh] rounded-t-3xl px-4 sm:px-6 md:px-8 lg:px-12 py-10">
        <div className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="p-6 border border-gray-200 rounded-xl bg-white animate-pulse">
              <div className="space-y-4">
                <div className="h-6 bg-gray-200 rounded w-1/2" />
                <div className="space-y-2">
                  <div className="h-4 bg-gray-200 rounded w-full" />
                  <div className="h-4 bg-gray-200 rounded w-3/4" />
                </div>
                <div className="h-10 bg-gray-200 rounded w-1/3" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
