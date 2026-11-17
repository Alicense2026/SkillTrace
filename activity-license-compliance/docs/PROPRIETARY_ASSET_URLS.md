# proprietary 资产统计与许可证原文链接

统计对象：`aggregate_all_10200/result.csv` 中 `资产许可证` 严格等于 `proprietary` 的记录。该 CSV 当前共 17,289 行，其中 5,626 行为 `proprietary`。

以下按资产 URL 包含相应地址统计；不同厂商之间的统计不做推断或合并。匹配数量反映数据快照，不是服务调用量。

| 平台/品牌 | CSV 中的资产 URL | 匹配行数 | 不同资产名 | 对应官方原文 |
|---|---|---:|---:|---|
| Gemini / Google AI | [Gemini API 模型文档](https://ai.google.dev/gemini-api/docs/models) | 930 | 139 | [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms)；同时查看[Google APIs Terms](https://developers.google.com/terms)。如通过 Vertex AI 调用，另查[Google Cloud Service Specific Terms](https://cloud.google.com/terms/service-terms)。 |
| 智谱 BigModel / GLM | [open.bigmodel.cn 开放平台 API 文档](https://open.bigmodel.cn/dev/api) | 163 | 59 | [智谱开放平台用户协议](https://docs.bigmodel.cn/cn/terms/user-agreement)；[智谱服务协议](https://docs.bigmodel.cn/cn/terms/service-agreement)。 |
| 阿里云百炼 / Qwen | [百炼模型目录](https://help.aliyun.com/zh/model-studio/models) | 359 | 193 | [阿里云百炼服务协议](https://terms.alicdn.com/legal-agreement/terms/common_platform_service/20230728213935489/20230728213935489.html)；[百炼服务特别说明](https://help.aliyun.com/zh/model-studio/bailian-service-notes)。 |
| Mistral AI | [Mistral 模型文档](https://docs.mistral.ai/getting-started/models/) | 128 | 37 | [Mistral Commercial Terms of Service](https://legal.mistral.ai/terms/commercial-terms-of-service/)；官方页面还列有消费者、额外产品及合作伙伴部署条款。 |
| Meta Llama | [Llama 模型目录](https://www.llama.com/models/) | 276 | 65 | 权重许可证取决于具体版本，见下方 Llama 版本表；远程API调用则需查实际API服务商协议。 |

## Llama 权重许可证原文

这些是 Meta 官方仓库或许可页面提供的原文入口：

| 权重版本 | 官方许可证 |
|---|---|
| Llama 2 / Code Llama | [Meta Llama 2 Community License](https://github.com/meta-llama/llama/blob/main/LICENSE) |
| Llama 3 | [Meta Llama 3 Community License](https://github.com/meta-llama/llama3/blob/main/LICENSE) |
| Llama 3.1 | [Meta Llama 3.1 LICENSE](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE) |
| Llama 3.2 | [Meta Llama 3.2 LICENSE](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE) |
| Llama 3.3 | [Meta Llama 3.3 LICENSE](https://github.com/meta-llama/llama-models/blob/main/models/llama3_3/LICENSE) |
| Llama 4 | [Meta Llama 4 Community License Agreement](https://www.llama.com/llama4/license/) |

同时核对相应版本的 [Llama 2 AUP](https://www.llama.com/llama2/use-policy/)、[Llama 3 AUP](https://www.llama.com/llama3/use-policy/) 或 [Llama 3.1 AUP](https://www.llama.com/llama3_1/use-policy/)。Llama 官方下载可能需要登录或先接受协议；实际使用时应以获取模型时随附并接受的版本为准。

## 使用这些链接时的范围说明

- CSV 的资产 URL 通常是模型目录或开发者文档，不一定是实际服务协议，也不能单独证明请求由该平台处理。
- 同一模型家族可能有托管API、第三方云转售、可下载权重等不同使用方式；协议需按实际调用提供者、用户类型、地区、接受日期和订单确定。
- Llama 的 Community License 约束相应模型材料/权重；若只远程调用服务，另需确认真实API运营方的条款。CSV中部分Llama调用证据指向第三方provider适配器，不能仅按模型名推定服务商。
- `proprietary` 是数据集中的统一标签，不是一份适用于所有品牌的许可证。此表用于定位原文，不会自动把任何条款转换为工具内的确定性 ASC 规则。

统计依据为当前工作区 CSV，文档整理日期：2026-11-10。协议页面会更新；追溯某条历史供应链时，应留存其当时生效的协议、订单和接受记录。
