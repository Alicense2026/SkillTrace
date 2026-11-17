# aggregate CSV 中 proprietary 标签与原始条款

## 数据范围

本目录中的 `../aggregate_all_10200/result.csv` 实读 **17,289 行**。资产许可证列（`资产许可证`）严格等于 `proprietary` 的记录有 **5,626 行**，包括OpenAI、Claude、DeepSeek、Gemini、Mistral、Qwen、Cohere、Grok等产品。文件夹名里的10200与此文件当前记录数不一致。

`proprietary` 是数据集的汇总标签，不是5,626行共同适用的一份许可证。此类记录主要表示通过托管服务/API调用模型；适用文件可能是消费者服务条款、开发者/API服务条款、企业协议、订单表、区域附录和可接受使用政策的组合。还要先确认调用的是官方平台还是第三方云/代理服务，以及具体账户/订单接受的版本。

托管服务的条款通常约束服务访问与API使用，不能直接等同于对模型权重的著作权许可证。若数据记录指的是公开发布的权重/源码，应另外核对那个特定模型版本随附的模型许可证；不能因同一品牌同时提供托管API，就把API合同套给权重发布物。

## 官方原文与下载

下列链接为厂商官方页面。带“PDF”的链接可直接保存原文；网页也可用浏览器打印/另存为PDF。链接核对日期：2026-11-10。网页会更新；审计历史交易时还应保存生效时版本、地区、接受记录和客户订单。

| 平台/产品范围 | 官方原文 | 可下载版本与适用提示 |
|---|---|---|
| OpenAI API、ChatGPT Business/Enterprise等商业/开发者客户 | [OpenAI Services Agreement](https://openai.com/policies/services-agreement/) | [官方PDF](https://cdn.openai.com/osa/openai-services-agreement.pdf)。页面标示2026-01-01生效。实际具体交易仍可能由Order Form、服务专用条款及客户/经销商合同补充。 |
| OpenAI个人ChatGPT等 | [Terms of Use](https://openai.com/policies/terms-of-use/) | 页面标示2026-01-01生效；该页明确业务/API服务适用Business Terms，不应把个人条款代替API合同。 |
| Claude API、Claude for Work商业客户 | [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms) | [官方PDF](https://assets.claude.com/cbc0cee5a5580ef30c81ccf745ef439aa7c47921.pdf)，页面所列2025-06-17生效；适用Claude API及引用该条款的商业服务。 |
| Claude Free/Pro/Max个人用户 | [Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms) | [官方PDF](https://assets.claude.com/43c13f51a6d9755341433f79cf63c966ed9200ea.pdf)；不用于代替商业API terms。 |
| DeepSeek官方API/开发者平台 | [DeepSeek Open Platform Terms of Service](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html) | 原文网页可另存；页面列明2026-04-29生效。条款说明API可集成到下游应用，须与DeepSeek通用Terms of Use及补充政策合并阅读。 |
| DeepSeek消费者应用 | [DeepSeek Terms of Use](https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html) | 官方条款网页；消费者应用条款不能自动代替Open Platform/API专用条款。 |
| Gemini API / Google AI Studio | [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms) | 官方网页列明2026-03-23生效；同时要求Google APIs Terms。免费和付费服务的数据处理条件可能不同。 |
| Vertex AI / Google Cloud API | [Google Cloud Service Specific Terms](https://cloud.google.com/terms/service-terms) | 网页中AI/ML和生成式AI专节；同时核对Google Cloud主协议、产品/地区和订单。 |
| Mistral AI API/商业产品 | [Mistral Commercial Terms of Service](https://legal.mistral.ai/terms/commercial-terms-of-service/) | 官方网页；核对接受版本、Additional Terms、Usage Policy及具体部署形态。 |
| xAI/Grok | [xAI Legal Center](https://x.ai/legal) | 官方法律中心按Consumer、Enterprise等区分条款；进入与数据所记录服务相符的协议。 |

## 对ASC检测的处理建议

不要把原始数据中的 `proprietary` 当成 `LICENSE_ID=PROPRIETARY` 并臆造一组统一禁止/许可规则。应按每个上游资产解析**可识别的服务商、产品形态、调用方式、条款版本/地区**，建立来源可追溯的条款记录，再逐条抽取适用于特定行为和对象的ASC，例如远程调用、输出使用、转售API访问、竞争模型训练等。许可授予与使用限制需分别建模，合同适用对象范围也要保留。

若数据只说明“proprietary”且无法确定供应商/具体协议，License↔License对比应标为 `UNSPECIFIED`/`AMBIGUOUS` 或规则未覆盖，不能假定兼容或冲突。对已识别厂商的规则加入数据库前，仍需确认该产品、地区、用户类别、接受日期、第三方云中转和订单表。此次链接索引不构成法律意见，也没有把任何厂商条款自动灌入审计规则库。

## 按本CSV资产URL补充的平台原文

下面的数量是对当前CSV中资产许可证严格等于 `proprietary` 的行，按资产URL包含指定地址统计。它们不是各厂商全部使用量，也不代表资产URL就是请求实际到达的平台。抽样证据显示有些仓库使用provider适配层或第三方路由；应保留“实际服务商”人工核验。

| CSV资产URL | 匹配行数 / 不同资产名 | CSV中典型模型名 | 对应官方原文 |
|---|---:|---|---|
| `https://ai.google.dev/gemini-api/docs/models` | 930 / 139 | gemini-2.5-flash、Gemini 3等 | [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms)，同时适用Google APIs Terms；通过Vertex AI调用应核对Google Cloud服务条款。 |
| `https://open.bigmodel.cn/dev/api` | 163 / 59 | GLM-5、GLM-4.7等 | [智谱开放平台用户协议](https://docs.bigmodel.cn/cn/terms/user-agreement)，版本页标示2026-09-04生效；API、自然语言处理和开放平台服务适用。另查[智谱服务协议](https://docs.bigmodel.cn/cn/terms/service-agreement)及账户实际订单/计费协议。 |
| `https://help.aliyun.com/zh/model-studio/models` | 359 / 193 | Qwen、qwen-plus等 | [阿里云百炼服务协议](https://terms.alicdn.com/legal-agreement/terms/common_platform_service/20230728213935489/20230728213935489.html)，版本页标示2026-09-02生效；API集成通常也受其约束。还需核对[百炼服务特别说明](https://help.aliyun.com/zh/model-studio/bailian-service-notes)。使用百炼上的第三方模型时，协议明确要求另看第三方服务商自己的协议。 |
| `https://docs.mistral.ai/getting-started/models/` | 128 / 37 | mistral-large-latest、mistral-embed等 | [Mistral Commercial Terms](https://legal.mistral.ai/terms/commercial-terms-of-service/)，按企业/开发者和部署方式适用；页面另列消费者条款及partner-served deployment terms。 |
| `https://www.llama.com/models/` | 276 / 65 | Llama 3.x、llama-3.3-70b-versatile等 | 权重许可依模型版本而异，见下表。若只是远程API调用，再适用API实际运营方的协议。 |

### Meta Llama：按权重版本找许可证

Llama不是“一份 proprietary 服务许可证”。Meta提供的可下载模型权重适用对应版本的 Community License Agreement 和 Acceptable Use Policy；可直接阅读/下载官方Meta GitHub仓库内的完整 `LICENSE` 文件：

| 模型权重 | 官方许可证原文 |
|---|---|
| Llama 2 / Code Llama | [Meta Llama 2 LICENSE](https://github.com/meta-llama/llama/blob/main/LICENSE)（该官方文件标题为LLAMA 2 COMMUNITY LICENSE AGREEMENT） |
| Llama 3 | [Meta Llama 3 LICENSE](https://github.com/meta-llama/llama3/blob/main/LICENSE) |
| Llama 3.1 | [Meta Llama 3.1 LICENSE](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE) |
| Llama 3.2 | [Meta Llama 3.2 LICENSE](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE) |
| Llama 3.3 | [Meta Llama 3.3 LICENSE](https://github.com/meta-llama/llama-models/blob/main/models/llama3_3/LICENSE) |
| Llama 4 | [Meta Llama 4 Community License Agreement](https://www.llama.com/llama4/license/)；[官方下载入口](https://www.llama.com/llama-downloads/) |

对以上权重发布，还应同时读取对应版本的Meta Acceptable Use Policy（例如 [Llama 2 AUP](https://www.llama.com/llama2/use-policy/)、[Llama 3 AUP](https://www.llama.com/llama3/use-policy/)、[Llama 3.1 AUP](https://www.llama.com/llama3_1/use-policy/)），确认模型具体版本、地域限制、分发对象和适用的归属/名称要求。部分官方下载需登录或先接受协议；GitHub LICENSE一般便于直接阅读，但法律适用版本仍以下载模型时随附并接受的文本为准。

CSV内 `llama-3.3-70b-versatile` 的示例调用证据指向Groq适配器。因此该样本的运行时API合同应查Groq及其账户/服务条款；不能只凭资产名含Llama就把Meta权重协议认作API合同。反过来，如果实际分发或修改的是Llama权重，Meta版本许可证也必须单独核验。

本轮对智谱/阿里云等资产URL的核对表明：URL指向模型目录或开发文档，不是已保存的用户订单、合同版本或账户同意记录。特别是阿里云百炼协议说明，经平台调用第三方模型时，平台协议与第三方模型服务商协议可能同时适用。故这些链接可以作为原文检索入口，不能仅据此把全体对应CSV记录映射成确定ASC。
