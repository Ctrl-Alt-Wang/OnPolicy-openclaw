# Search Tools - 搜索工具说明

本技能使用 `scripts/search.py` 进行医学文献检索，底层调用 Infox-Med API。

## 搜索脚本位置

```
<skill_path>/scripts/search.py
```

> `<skill_path>` 是本技能的安装目录，无需手动配置。

## 工具接口

### search(keywords: List[str]) -> List[Dict]

搜索医学文献并返回去重后的结构化结果。

**参数**：
- `keywords`: 搜索关键词列表（支持中文），也支持空格分隔的字符串

**返回字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 文献唯一 ID |
| `title` | str | 文献标题 |
| `pmid` | str | PubMed ID |
| `abstract` | str | 摘要（英文或中文） |
| `url` | str | Infox-Med 详情页链接 |
| `publish_time` | str | 发布时间（YYYY-MM 格式） |
| `docIf` | str | 期刊影响因子 |
| `_matched_keywords` | list | 命中的关键词列表（用于判断文献与多维度的关联性） |

## 调用方式

### 方式 1：命令行调用（推荐用于 run_command）

```bash
python3 <skill_path>/scripts/search.py --keywords "肺癌" "免疫治疗" --output "/tmp/search_results.json" --summary-limit 8
```

### 方式 2：Python 导入

```python
import sys
sys.path.insert(0, r"<skill_path>/scripts")
from search import search

results = search(["肺癌", "免疫治疗"])
for paper in results:
    print(f"[{paper['publish_time']}] {paper['title']} (IF: {paper['docIf']})")
```

## API 参数说明

search.py 内部的默认参数配置：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `category` | 3 | 文献类别 |
| `pageNum` | 1 | 页码（固定第一页） |
| `pageSize` | 10 | 每个关键词最多返回的文献数。如需更广泛的证据收集（如空白点挖掘报告场景），可考虑调整为 20 |
| `nearMonth` | 120 | 搜索近 120 个月（10 年）的文献。覆盖近十年研究趋势，但结果排序仍优先近 5 年文献 |

> ℹ️ 关于时间范围：报告模板要求覆盖近 10 年演变趋势，因此 `nearMonth` 默认值已从 60 调整为 120。检索结果应优先使用近 5 年文献，但允许追溯更早的里程碑研究。

## 注意事项

- 每个关键词独立请求，结果自动按 `id` 去重
- 多关键词命中同一文献时，`_matched_keywords` 会记录所有命中关键词
- API 调用失败时会自动重试 1 次（间隔 0.1 秒），仍失败则跳过该关键词并继续
- 请求超时设置为 30 秒
