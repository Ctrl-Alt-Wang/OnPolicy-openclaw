const CAPABILITIES = [
  { name: '文献检索', icon: '🔍', desc: '关键词语义检索' },
  { name: '论文精读', icon: '📖', desc: '全文API读取' },
  { name: 'PICO 检索', icon: '🎯', desc: '循证医学检索' },
  { name: '综述撰写', icon: '✍️', desc: '自动生成综述' },
  { name: '论文润色', icon: '✨', desc: 'SCI 风格润色' },
  { name: '参会 PPT', icon: '📊', desc: '一键生成PPT' },
  { name: '浏览器', icon: '🌐', desc: '联网搜索' },
  { name: '科研助手', icon: '🤖', desc: '全流程辅助' },
]

export default function CapabilityGrid() {
  return (
    <div>
      <p className="text-xs text-gray-400 font-medium mb-3">深度探索 8 大能力</p>
      <div className="grid grid-cols-2 gap-2">
        {CAPABILITIES.map((c) => (
          <div
            key={c.name}
            className="flex flex-col items-center gap-1 px-3 py-4 rounded-xl
                       bg-gray-50 border border-gray-200"
          >
            <span className="text-base">{c.icon}</span>
            <span className="text-xs text-gray-900 font-medium">{c.name}</span>
            <span className="text-[10px] text-gray-400">{c.desc}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
