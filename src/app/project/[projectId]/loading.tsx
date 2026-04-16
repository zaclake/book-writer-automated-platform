export default function ProjectLoading() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="w-full px-4 sm:px-6 md:px-8 lg:px-12">
          <div className="flex items-center gap-3 py-4 border-b border-gray-100">
            <div className="h-5 w-24 bg-gray-200 rounded animate-pulse" />
            <div className="h-5 w-3 bg-gray-100 rounded animate-pulse" />
            <div className="h-5 w-40 bg-gray-200 rounded animate-pulse" />
          </div>
          <div className="flex gap-2 py-3 overflow-x-auto">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-9 w-24 bg-gray-100 rounded-lg animate-pulse shrink-0" />
            ))}
          </div>
        </div>
      </div>
      <div className="flex items-center justify-center py-24">
        <div className="text-center">
          <div className="w-10 h-10 mx-auto border-4 border-gray-200 border-t-indigo-500 rounded-full animate-spin" />
          <p className="mt-4 text-sm text-gray-500">Loading...</p>
        </div>
      </div>
    </div>
  )
}
