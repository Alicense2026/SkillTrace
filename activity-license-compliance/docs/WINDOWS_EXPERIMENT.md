> 公开版使用占位端点，在线执行前必须自行配置服务；历史产物并非全部收录。

# Windows · gpt-6-luna 中转站实验

## 1. 准备

安装Python3.11或更高版本并确保 `py -3 --version` 可用。将工具文件夹与输入数据复制到Windows；以下命令在 `activity_license_compliance` 目录的PowerShell中执行。运行无第三方依赖，不需要修改Codex配置或读取其auth.json。

```powershell
py -3 --version
py -3 -m license_checker cases
py -3 -m unittest discover -s tests -v
```

## 2. 配置与请求预览

编辑 `configs/experiment.toml`。按照用户提供的中转站示例采用Responses协议，当前默认：

```toml
[experiment]
base_url = "https://api.example.invalid"
responses_path = "/responses"
model = "gpt-6-luna"
api_key_env = "LICENSE_API_KEY"
reasoning_effort = "medium"
max_output_tokens = 8192
max_input_chars = 180000
max_retries = 2
timeout_seconds = 120
```

`base_url` 与 `responses_path` 直接拼接，不自动增加 `/v1`。示例文档给出站点根地址和Responses协议，但未验证实际HTTP路由；若服务商要求 `/v1/responses`，明确修改 `responses_path`。不自动更换模型。推理参数和模型权限以中转站实际支持为准。

```powershell
.\scripts\run_experiment.ps1 -Limit 3
```

默认输入为相邻目录 `aggregate_all_16927\result.csv`，默认输出 `runs\luna-preview`。可自定义 `-InputPath`、`-OutputDir`、`-ConfigPath`、`-Limit`、`-Offset`。脚本中的相对路径以工具根目录为基准。Offset从0开始。

若系统策略不允许运行PS1，直接运行相同Python入口：

```powershell
py -3 -m license_checker experiment --input "aggregate_all_16927\result.csv" --output-dir "runs\luna-preview" --limit 3
```

预览不联网。打开 `requests\*.json`，可以检查实际endpoint、完整12案例、当前样本、规则来源与输出合同。三个实测样本每个提示约6.8万字符，字符数不等于token数；所有样本都会重复发送完整案例。

## 3. 运行真实实验

可在当前PowerShell会话设置密钥（优先于 `api_key_file`）；输入不会显示：

```powershell
$env:LICENSE_API_KEY = [System.Net.NetworkCredential]::new("", (Read-Host "API Key" -AsSecureString)).Password
.\scripts\run_experiment.ps1 -Limit 1 -OutputDir "runs\luna-live-001" -Execute
```

或直接运行：

```powershell
py -3 -m license_checker experiment --input "aggregate_all_16927\result.csv" --output-dir "runs\luna-live-001" --limit 1 --execute
```

一次单样本成功后，再选定批次范围，例如 `-Offset 1 -Limit 20 -OutputDir runs\luna-batch-002 -Execute`。`--execute` 会向配置中转站发送请求并可能产生费用；请求包含当前记录和规则材料。

## 4. 产物和续跑

| 文件 | 用途 |
|---|---|
| `manifest.json` | 输入/案例/系统提示哈希，模型配置、环境、样本范围 |
| `requests/<case_id>.json` | endpoint、提示词全文、请求哈希；不含Authorization |
| `responses/<case_id>.json` | 原始成功HTTP响应；即使模型JSON校验失败也保留 |
| `results/<case_id>.json` | SUCCESS/ERROR、经校验分析、模型返回型号、token用量与耗时 |
| `three_outputs/{license_license,license_activity,obligations}/<case_id>.json` | 按供应链关系拆出的三类模型输出 |
| `progress.json` | 实际执行期间逐条更新的进度 |
| `summary.json` | DRY_RUN/LIVE模式、成功/复用/失败数和样本记录 |
| `final_report.md` | 本次选中范围的统计和最多3个冲突案例；只统计成功响应 |

使用**相同输入、配置、范围、输出目录**重跑，成功且请求哈希一致的样本会复用；失败样本重试。配置/输入/案例/系统提示变化时要求新目录。预览没有模型响应，不能作为准确率评估结果。结果格式通过只说明结构与引用合法，不证明法律结论正确。

## 5. 常见调试位置

- 401/403：核对密钥来源和账户授权；400/404：核对路由、模型和参数。这些错误中止当前批次，HTTP正文不写日志。
- 429/500/502/503/504或网络超时：有限次数重试。超时重试可能导致服务端重复处理，不承诺调用恰好一次。
- 输出不完整、拒绝、非JSON、对象/来源引用错误：样本记ERROR；检查responses与schema.py，不会自动把失败当合规。
- 提示超限：不删减12案例；调整字符上限前核实模型上下文容量，或减小单个样本提供的材料。
- 模型建议需人工审核后通过离线人工接口回填，实验程序不自动更新规则。

官方参考：[模型信息](https://developers.openai.com/api/docs/models/gpt-6-luna)、[Responses文本生成](https://developers.openai.com/api/docs/guides/text)。这些资料说明OpenAI协议，不保证第三方中转站兼容。本次仅在macOS完成离线验证，未在Windows或中转站实测。


## Prompt v2迁移

当前请求使用结构化ASC、Figure 10案例和32个合成对照场景；详见[Prompt设计](PROMPT_DESIGN.md)。逐行LLM实验不调用离线冲突判定引擎。八个顶层输出字段不变，非空义务新增trigger、applicability、unresolved_predicates。旧目录与新版本指纹不兼容。HTTP 429/5xx在有限重试后会停止批次，避免服务故障时继续发送余下请求。
