export default function ConversationHistory({ conversations, onOpen, onDelete }) {
  if (conversations.length === 0) return null

  return (
    <div>
      <p className="text-xs text-gray-400 font-medium mb-3">历史对话</p>
      <div className="space-y-1">
        {conversations.map(c => (
          <div
            key={c.id}
            onClick={() => onOpen(c)}
            className="flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer border
                       bg-gray-50 border-gray-200 hover:border-gray-300
                       transition-colors active:scale-[0.98]"
          >
            <span className="text-base shrink-0">💬</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-900 truncate">{c.title || '新对话'}</p>
              <p className="text-[10px] text-gray-400">
                {c.messages.length} 条消息
                {c.createdAt && ` · ${new Date(c.createdAt).toLocaleDateString('zh-CN')}`}
              </p>
            </div>
            <button
              onClick={e => { e.stopPropagation(); onDelete(c.id) }}
              className="text-gray-300 hover:text-red-400 text-sm px-1"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
