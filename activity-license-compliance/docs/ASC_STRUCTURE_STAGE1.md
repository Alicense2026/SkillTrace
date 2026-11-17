# 许可证原文 ASC 结构化（阶段一）

## 交付内容

- `data/structured_asc_v1.json`：按原文条款抽取并展开的 ASC 记录。
- `data/structured_asc_v1_summary.json`：来源覆盖与记录数摘要。
- `scripts/build_asc_corpus.py`：可重复运行的首轮抽取/序列化脚本。

本阶段只处理许可证原文，没有读取供应链关系，也没有调用 LLM。原文按文件分别登记，不将同一厂商的 API 服务条款、模型社区协议和禁止用途政策合并。

## ASC 数据结构

每条记录的 `ASC` 字段严格包含三个键：

```json
{
  "A": "Distribute",
  "S": {"artifact": "$LICENSED_MATERIAL", "kind": "DerivativeWork"},
  "C": {"kind": "OBLIGATORY", "requires": "provide_agreement_and_required_notices"}
}
```

`A` 使用项目的规范活动名；`S.kind` 使用 `OriginalArtifact`、`ModifiedArtifact`、`DerivativeWork` 或 `CombinedProduct`。`C.kind` 使用 ASC 定义的七类模态。条件目前以符号化事实名保存，不能仅凭其字符串判定事实已经成立。例如，`prior_written_authorization_from_licensor` 需要由后续活动事实提供，不能默认满足。

条款来源元数据在 ASC 三元组之外，包含源文件名、SHA-256、原文行号范围、条款标签、原文摘录、行为主体角色、适用范围说明和抽取状态。原文证据可用 `license_source_id` 与 `clause_id` 定位。

## 本轮覆盖

本地共发现 40 份 `.txt` 原文。39 份生成了至少一条 ASC 记录；`LGPL-3.0.txt` 按要求保留来源指纹并标为 `EXCLUDED_BY_USER`，不生成活动条款。当前共输出 1,104 条展开后的 ASC 记录。该数量是“条款匹配 × 活动 × 对象”的展开记录数，不代表 1,104 个互不相同的原文条款。

抽取覆盖包含宽松软件许可证、GPL/AGPL、CC、MPL/EPL/EUPL、OpenRAIL、Llama 与 Baichuan 模型协议，以及 OpenAI、Anthropic、DeepSeek、Gemini、Mistral、阿里云、智谱等服务条款/使用政策。每份来源的记录数和内容指纹见 JSON 摘要与来源清单。

## 生成与复用

在项目根目录运行：

```sh
python3 scripts/build_asc_corpus.py
```

脚本按本地原文哈希建立稳定来源 ID，匹配规则只摘录实际命中的原文段落，并用 `license_checker.asc.validate_triple` 校验 ASC 形状及规范值。相同原文的不同文件名仍保留为独立许可证身份；AGPL 两份文件内容相同，但不合并掉原始文件记录。

## 当前边界

本结果是可复用的条款级初稿，不是穷尽全文的法律意见。脚本采用可读的条款匹配模板，条款只要命中相应模式便展开为对应活动和对象；模板未命中的内容不会自动变成 `UNSPECIFIED`，没有记录也不表示允许。商业/API 条款与软件版权许可证涉及的主体、对象和权利范围不同，后续做 license-license 对比前必须使用 `actor_role` 和 `scope_note` 过滤可比条款。

每条记录目前均标记 `FIRST_PASS_REVIEW_REQUIRED`。人工复核重点是：

1. 原文定位是否覆盖完整条款（尤其跨段落的条件、例外和定义）；
2. A 与对象类型是否从原文语境正确映射；
3. C 模态及 `requires`/`when` 条件是否忠实表达原文，而非将模板占位事实误作已满足事实；
4. 许可授予、使用限制、付款义务和署名/源码义务是否属于同一权利主体和同一活动场景。

完成这一步复核后，才适合据此生成完整的 `(A,S)` 未规定矩阵，并逐行分析供应链 license-license 冲突、license-activity 冲突及义务集合。

## 2026-11-12 增量更新

本页以上为最初阶段的历史说明。当前已加入 17 份新原文、1,367 条新增 ASC；总计 57 份来源、2,471 条 ASC。新增部分使用 LLM 提取及来源校验，详见 [增量结构化报告](ASC_EXTENSION_2026-11-12.md)。当前语料含增量数据，旧构建脚本会拒绝覆盖。
