# macOS / Linux 运行公开版本

在 `activity-license-compliance` 目录执行，要求 Python 3.11+。

```bash
python3 -m license_checker cases
python3 -m license_checker experiment --input aggregate_all_16927/result.csv --output-dir runs/public-preview --limit 1
```

预览不联网。在线运行前配置 `configs/experiment.toml` 的服务地址、Responses 路径和模型，通过 `LICENSE_API_KEY` 环境变量提供密钥，再增加 `--execute`。默认配置不再读取本地 API 文件。请使用新的输出目录；公开归档不包含历史请求和原始响应。
