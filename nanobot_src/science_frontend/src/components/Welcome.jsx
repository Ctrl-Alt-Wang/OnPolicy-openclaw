export default function Welcome() {
  return (
    <div className="text-center pt-4">
      <p className="text-lg text-gray-900 font-medium">你好，我是你的科研助手</p>
      <p className="text-sm text-gray-500 mt-1">
        我可以帮你检索文献、分析论文、撰写综述等
      </p>
      <div className="flex flex-wrap justify-center gap-2 mt-4">
        {['文献检索', '论文精读', '综述撰写', '数据分析'].map(tag => (
          <span key={tag} className="px-3 py-1 rounded-full bg-gray-100 text-gray-600 text-xs border border-gray-200">
            {tag}
          </span>
        ))}
      </div>
    </div>
  )
}
