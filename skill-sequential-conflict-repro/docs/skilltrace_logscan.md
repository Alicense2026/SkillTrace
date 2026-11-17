# SkillTrace 日志扫描

`scripts/skilltrace_logscan.py` 从 Agent 执行日志中提取 Skill 和许可证证据。它是之前
SkillTrace/TAR Engine 自动化能力的离线精简版，专门用于本实验包中的 8 个 Skill。

## 可识别内容

- Skill 名称、ID、仓库和 `SKILL.md` 路径。
- Skill 第一次出现在日志中的顺序。
- `inputs/skills.json` 中记录的许可证。
- `inputs/tasks.json` 中定义的 C1-C3、O1-O3 调用链。
- 命令参数、文件路径、工具响应和普通文本中的检测证据。

## 支持的日志格式

- Codex JSONL，包括 `thread.started`、`item.completed` 和 `turn.completed`。
- 带 `tool_name`、`tool_input`、`tool_response` 的 Claude Code 风格 JSON/JSONL。
- JSON 数组或 `{"events": [...]}` 包装格式。
- 使用 `--source generic` 或自动识别失败时的普通文本日志。

日志内容会被当作不可信数据解析，不会执行其中出现的命令。

## 使用方式

扫描 Codex 轨迹：

```bash
python scripts/skilltrace_logscan.py examples/skilltrace/sample_codex_c1.jsonl
```

示例输出：

```text
1. paper-search-pro | Apache-2.0 | ...
2. easy-vibe | CC-BY-NC-SA-4.0 | ...
Matched chains:
- C1 (commercial_use): paper-search-pro -> easy-vibe
```

输出 JSON：

```bash
python scripts/skilltrace_logscan.py examples/skilltrace/sample_codex_c1.jsonl \
  --json --pretty
```

扫描 Claude Code 风格轨迹：

```bash
python scripts/skilltrace_logscan.py examples/skilltrace/sample_claude_o1.json
```

一次扫描多个日志并指定格式：

```bash
python scripts/skilltrace_logscan.py logs/*.jsonl --source codex --json
```

写入结果文件：

```bash
python scripts/skilltrace_logscan.py logs/agent.jsonl --json --pretty \
  --output outputs/skilltrace-scan.json
```

## 匹配流程

1. 将日志解析为 JSON、JSONL 或普通文本事件。
2. 将不同 Agent 的工具事件归一化为统一结构。
3. 在原始事件和归一化事件中查找 Skill ID、名称、仓库或足够具体的 Skill 路径。
4. 按第一次匹配事件确定调用顺序。
5. 从固定版本的 `inputs/skills.json` 解析许可证。
6. 对照 `inputs/tasks.json` 判断是否匹配六条已设计调用链。

扫描器不会只凭 `SKILL.md` 文件名匹配，因为所有 Skill 都使用该文件名，会产生大量误报。

## 输出字段

- `files`：扫描文件及事件数量。
- `events`：事件总数。
- `detected_skills`：Skill ID、名称、许可证、首次事件、证据文件和匹配文本。
- `license_sequence`：检测出的 Skill 和许可证顺序。
- `matched_chains`：日志中按顺序出现的已知实验调用链。
- `errors`：JSON/JSONL 文件中无法解析的日志行。

## 限制

- 检测依赖本实验固定的仓库名、Skill ID 和路径，不是通用 Skill 注册表。
- 如果日志只有通用命令，可能无法判断实际加载了哪个 Skill。
- 许可证来自固定实验清单，不会读取任意当前仓库未固定版本。
- 扫描器报告调用证据和已知调用链，不判断商业目的或输出内容是否构成法律冲突。

## 上游归属

统一事件结构和 Codex/Claude 归一化逻辑改编自 `qingxuantang/tar-engine`，对应 commit
`ab5f50bfcc4728ccd9a02c96057ba8d12ea4139c`，原项目采用 Apache-2.0。
许可证全文保存在 `licenses/TAR-ENGINE-APACHE-2.0.txt`。
