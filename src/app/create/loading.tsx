export default function CreateLoading() {
  return (
    <div className="min-h-screen bg-brand-off-white">
      <div className="relative min-h-[28vh] bg-gradient-to-br from-gray-900 via-indigo-950 to-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="w-10 h-10 mx-auto border-4 border-white/20 border-t-white rounded-full animate-spin" />
          <p className="mt-4 text-sm text-white/60">Loading...</p>
        </div>
      </div>
      <div className="w-full px-4 sm:px-6 md:px-8 lg:px-12 py-10">
        <div className="max-w-4xl md:max-w-5xl mx-auto bg-white border border-gray-200 rounded-xl p-6 sm:p-8 animate-pulse">
          <div className="space-y-6">
            <div className="grid md:grid-cols-2 gap-4">
              <div className="h-10 bg-gray-200 rounded" />
              <div className="h-10 bg-gray-200 rounded" />
            </div>
            <div className="h-10 bg-gray-200 rounded" />
            <div className="h-48 bg-gray-200 rounded" />
            <div className="h-10 bg-gray-200 rounded w-1/3 ml-auto" />
          </div>
        </div>
      </div>
    </div>
  )
}
