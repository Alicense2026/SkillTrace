# 自定义许可证 ASC 结构化结果

输入：`许可证原文/_licenseref_full/licenseref_full.json`。共122个仓库映射；原文导出时校验了提供的哈希。

|项目|数量|
|---|---:|
|仓库映射|122|
|非空、去重原文|119|
|新提取原文|118|
|复用已有原文|1|
|提取得到有效 ASC 的原文|89|
|未匹配到有效条款的原文|30|
|空原文记录|1|
|新增 ASC|3392|
|自定义相关 ASC 总数（含复用）|3489|

132个分块均成功返回并通过结构与源行号校验。调用 GPT-6-luna；保留 requests、responses、validated。51条规则按此前通用 ASC 规范化流程处理条件禁止、义务内容谓词或布尔字面值，详见 normalization_audit.json；原始提取保存在 custom_before_normalization.json，原始模型响应未改动。

所有条款摘录与原文行号逐字匹配；旧语料中的2471条规则及57个来源未被改写。此校验不等同于人工法律审查。

## 无有效条款或空原文的记录

下列来源已经读取；零条款不等于无限制许可。部分文件实际是包元数据、营销文本、未定许可声明或外部链接。完整提取说明见 custom_asc_index.csv 的覆盖说明列。

|仓库|状态|证据文件|
|---|---|---|
|0xchrisskr/go2-agent-lab|INCLUDED_NO_RULE_MATCHED|LICENSE|
|anthropics/claude-ai-mcp|INCLUDED_NO_RULE_MATCHED|LICENSE|
|anthropics/claude-code|INCLUDED_NO_RULE_MATCHED|LICENSE.md|
|aradotso/hermes-skills|INCLUDED_NO_RULE_MATCHED|LICENSE|
|buffaloshine/langgraph-langchain-agent-setup|INCLUDED_NO_RULE_MATCHED|license.txt|
|chelo6185/ai-photo-restoration-remini-codeformer|INCLUDED_NO_RULE_MATCHED|license.txt|
|cognis-digital/agentforge|INCLUDED_NO_RULE_MATCHED|pyproject.toml|
|cognis-digital/convoyplan|INCLUDED_NO_RULE_MATCHED|pyproject.toml|
|cognis-digital/crmsync|INCLUDED_NO_RULE_MATCHED|pyproject.toml|
|cognis-digital/enrichr|INCLUDED_NO_RULE_MATCHED|pyproject.toml|
|cognis-digital/portfan|INCLUDED_NO_RULE_MATCHED|pyproject.toml|
|cognis-digital/ssltriage|INCLUDED_NO_RULE_MATCHED|pyproject.toml|
|cognis-digital/taskloom|INCLUDED_NO_RULE_MATCHED|pyproject.toml|
|creatorrrr/common-skills|INCLUDED_NO_RULE_MATCHED|LICENSE|
|devexpress-examples/blazor-ai-chat-function-calling|INCLUDED_NO_RULE_MATCHED|LICENSE|
|failproofai/skills|INCLUDED_NO_RULE_MATCHED|LICENSE|
|fim-ai/fim-one|INCLUDED_NO_RULE_MATCHED|pyproject.toml|
|floydtang/jiuliang-scenes|INCLUDED_NO_RULE_MATCHED|NOTICE.md|
|generalelectionexoergicreaction447/ai-vfx-wonder-studio|INCLUDED_NO_RULE_MATCHED|license.txt|
|gibbok/typescript-book|INCLUDED_NO_RULE_MATCHED|LICENSE.MD|
|highcharts/highcharts|INCLUDED_NO_RULE_MATCHED|license.txt|
|islablxkp6370558/soul.md-ai-latest-version|INCLUDED_NO_RULE_MATCHED|license.md|
|phamdo627/ai-detection-bypass-gptzero-turnitin|EMPTY_ORIGINAL|license.txt|
|pimenov/anti-roadmap-skill|INCLUDED_NO_RULE_MATCHED|NOTICE.md|
|rna4219/manual-bb-test-harness|INCLUDED_NO_RULE_MATCHED|pyproject.toml|
|scarletshoburn/openai-assistants-api-setup|INCLUDED_NO_RULE_MATCHED|license.txt|
|theailanguage/mcp_client|INCLUDED_NO_RULE_MATCHED|LICENSE|
|vila-lab/dive-into-claude-code|INCLUDED_NO_RULE_MATCHED|LICENSE|
|voicevox/voicevox|INCLUDED_NO_RULE_MATCHED|LICENSE|
|vxz789913/ai-interior-design-roomgpt-remodel-ai|INCLUDED_NO_RULE_MATCHED|license.txt|
|xrmghost/xrmghost-skills|INCLUDED_NO_RULE_MATCHED|LICENSE|

## 产物

- `data/structured_asc_custom_v1.json`：独立的自定义 ASC 和映射。
- `custom_asc_index.csv`：122个仓库的原文、状态、条目数和覆盖说明。
- `by_license/<sha256>.json`：按原文查看条款及关联仓库。
- `verification.json`：原文哈希、摘录、旧语料保留及约束表示校验。
- `normalization_audit.json`：51条规范化改动。
