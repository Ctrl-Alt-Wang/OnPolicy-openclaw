const PROMPTS = [
  { title: '检索最新文献', desc: '帮我检索近三年关于 CAR-T 治疗实体瘤的临床研究', icon: '🔬' },
  { title: 'PICO 循证检索', desc: 'PICO检索：晚期非小细胞肺癌患者使用免疫检查点抑制剂 vs 化疗的总生存期', icon: '📊' },
  { title: '撰写综述大纲', desc: '帮我写一篇关于mRNA疫苗在肿瘤免疫治疗中应用的综述大纲', icon: '📝' },
  { title: '润色论文摘要', desc: '帮我润色这段英文摘要，让它更符合 SCI 期刊风格', icon: '✨' },
]

export default function PromptCards({ onSend }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-400 font-medium">试试这些</p>
      {PROMPTS.map((p, i) => (
        <button
          key={i}
          onClick={() => onSend(p.desc)}
          className="w-full text-left px-4 py-3 rounded-xl bg-gray-50 border border-gray-200
                     hover:border-emerald-400 hover:bg-emerald-50 active:scale-[0.98] transition-all"
        >
          <span className="text-sm mr-2">{p.icon}</span>
          <span className="text-sm text-gray-900 font-medium">{p.title}</span>
          <p className="text-xs text-gray-500 mt-0.5 ml-6">{p.desc}</p>
        </button>
      ))}
    </div>
  )
}
