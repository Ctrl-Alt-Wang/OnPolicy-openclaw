export default function ActionBar({ messages, onAction, disabled: globalDisabled }) {
  const lastAsst = [...messages].reverse().find(m => m.role === 'assistant')
  const len = lastAsst?.content?.length || 0
  const ok = lastAsst && !lastAsst.running && len >= 100

  const title = !lastAsst
    ? '暂无可处理内容'
    : lastAsst.running
      ? '正在处理中'
      : len < 100
        ? '内容过短'
        : ''

  const blocked = !ok || globalDisabled

  const buttons = [
    {
      emoji: '🌐',
      label: '英文翻译',
      action: () => {
        onAction({
          prompt: `请将下面的医学科研内容翻译成英文，保持医学术语准确、专业：\n\n${lastAsst.content}`,
          label: '🌐 英文翻译',
        })
      },
    },
    {
      emoji: '🌳',
      label: '思维导图',
      action: () => {
        onAction({
          prompt: `请把下面内容提炼成思维导图，要求：\n每个节点最多 8 个汉字或 4 个英文单词\n用 # ## ### - 表达层级，最多 4 层\n突出核心要素和关系，不要写完整句子\n不要重复原文，要做总结提炼\n\n内容：\n\n${lastAsst.content}`,
          label: '🌳 思维导图',
        })
      },
    },
    {
      emoji: '🔍',
      label: '查找原文',
      action: () => {
        onAction({
          prompt: `请根据下面内容，调用 medical-keyword-search skill 检索可能的引用原文文献。返回 markdown 列表格式，每篇文献需包含：标题、作者、期刊、年份、链接（如有）。按相关性排序，最多返回 5 篇。\n\n内容：\n\n${lastAsst.content}`,
          label: '🔍 查找原文',
        })
      },
    },
  ]

  return (
    <div className="px-4 pt-2 pb-0">
      <div className="flex gap-2">
        {buttons.map((btn) => (
          <button
            key={btn.label}
            onClick={btn.action}
            disabled={blocked}
            title={blocked ? title : ''}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium
              transition-colors
              ${
                blocked
                  ? 'border border-gray-200 bg-gray-50 text-gray-400 opacity-50 cursor-not-allowed'
                  : 'border border-gray-300 bg-gray-50 text-gray-600 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600'
              }`}
          >
            <span className="text-sm">{btn.emoji}</span>
            <span>{btn.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
