export default function Header({ activeTool, inChat, onBack }) {
  return (
    <header className="shrink-0 px-4 py-3 border-b border-gray-200 bg-white">
      <div className="flex items-center gap-2">
        {inChat && (
          <button onClick={onBack} className="text-gray-400 hover:text-gray-600 pr-2 shrink-0">
            ← 返回
          </button>
        )}
        <span className="text-xl">🧬</span>
        <div className="flex-1 min-w-0">
          <h1 className="text-base font-semibold text-gray-900 truncate">
            InfoX-Med 科研助手
          </h1>
        </div>
      </div>
      {activeTool && (
        <div className="mt-1.5 flex items-center gap-1.5 text-xs text-emerald-600">
          <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          正在调用: {activeTool}
        </div>
      )}
    </header>
  )
}
