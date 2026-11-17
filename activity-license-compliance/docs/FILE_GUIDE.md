# 文件职责与调试导读

## 调用关系

```text
python -m license_checker
  └─ __main__.py → cli.py
      ├─ audit → audit_cli.py → input_files.py → pipeline.py
      │                         ├─ ingestion.py → identity.py / audit_rules.py
      │                         ├─ analysis.py → audit_engines.py → asc.py
      │                         └─ reporting.py → resources/report.html
      ├─ experiment → llm/experiment.py
      │    ├─ input_files.py → ingestion.py → analysis.py（确定性基线）
      │    ├─ llm/config.py
      │    ├─ llm/prompting.py → figure10_cases.json + llm_system.txt
      │    ├─ llm/client.py → 中转站 Responses API（仅execute）
      │    └─ llm/schema.py → 请求/响应/结果/汇总落盘
      └─ cases → llm/prompting.py（核验全部案例）
```

## 核心代码

| 文件 | 职责；适合修改/断点的位置 |
|---|---|
| `license_checker/__init__.py` | 包版本0.6.0 |
| `license_checker/__main__.py` | `python -m`入口 |
| `license_checker/cli.py` | audit/experiment/cases子命令和错误退出；CLI参数在此 |
| `license_checker/audit_cli.py` | 离线参数、加载人工文件、记录输入哈希、写报告 |
| `license_checker/input_files.py` | JSON和中文CSV适配；扩展列名在CSV_COLUMNS |
| `license_checker/identity.py` | 原始记录+原始索引生成稳定case_id；切片不重新编号 |
| `license_checker/ingestion.py` | prepare构造对象图、可信行为事实、许可规则；apply_human应用人工事实/条款 |
| `license_checker/pipeline.py` | 批量run、证据目录、策略说明、跨案例汇总 |
| `license_checker/analysis.py` | analyze_case单案例总控：两类审计、义务、覆盖与最终状态 |
| `license_checker/license_pair_cache.py` | SQLite License↔License 符号比较缓存；按规范化规则对、条款版本、作用范围复用，不存行为事实 |
| `license_checker/audit_engines.py` | License↔License、License↔Behavior、义务合并和联合条件分析 |
| `license_checker/audit_rules.py` | 带条款来源、范围和覆盖元数据的规则库；添加经审核许可证规则的主要入口 |
| `license_checker/asc_rules.py` | 基础许可证识别和ASC规则辅助；被审计规则模块复用 |
| `license_checker/asc.py` | 七模态校验、三值条件求值、D⇒U、可满足性和反例；不决定批量结论策略 |
| `license_checker/taxonomy.py` | 规范活动和别名；TrainModel是Figure案例/LLM扩展，未自动扩大既有审计矩阵 |
| `license_checker/reporting.py` | JSON拆分产物与HTML转义、模板替换；不参与判定 |
| `license_checker/audit_chain.py` | 旧调用方兼容入口，转发run/write_outputs/main，无另一套算法 |
| `license_checker/chain.py` | 旧模块命令兼容入口，转到当前离线审计 |

ASC的S必须携带 `artifact` 身份与 `kind`（OriginalArtifact/ModifiedArtifact/DerivativeWork/CombinedProduct）。条件支持bool、原子名称、all/any/not；未知值为null。比较前必须先确定同一许可作用范围，不能仅凭两端许可证名称比较全部对象。

## LLM实验代码与资源

| 文件 | 职责 |
|---|---|
| `license_checker/llm/__init__.py` | 实验子包说明 |
| `license_checker/llm/config.py` | TOML配置和HTTPS端点校验、环境变量密钥读取 |
| `license_checker/llm/casebook.py` | Figure10模板和对照场景的无损去重；完整原始资源保留 |
| `license_checker/llm/prompting.py` | 唯一请求构造入口；加载/校验12案例及ASC、拼接基线/允许引用/输出合同、生成哈希、检查字符上限 |
| `license_checker/llm/client.py` | 标准库HTTP、Bearer认证、超时、有限重试、禁止自动重定向、Responses文本提取 |
| `license_checker/llm/schema.py` | 纯JSON输出合同；校验case_id、ASC、对象、来源、状态和重复键 |
| `license_checker/llm/experiment.py` | 先选样本后分析、预览/发送、原子写文件、成功缓存续跑、失败和用量记录 |
| `license_checker/resources/llm_system.txt` | 实际发送的系统提示；修改分析工作流程在此 |
| `license_checker/resources/conflict_patterns.json` | 12种合成对照模式、32场景；其中9种来自Figure10主题、3种为扩展 |
| `license_checker/resources/figure10_cases.json` | 原始12案例和40条ASC；实际发送采用可逆模板引用，保留映射依据和边界 |
| `license_checker/resources/report.html` | 离线报告模板 |
| `configs/experiment.toml` | 中转站地址、Responses路径、gpt-6-luna及运行参数；没有密钥 |
| `scripts/run_experiment.ps1` | Windows参数化入口，默认预览，Execute才发送 |
| `prompts/auditable_asc_pipeline.txt` | 保留的离线审计方法说明；不是实际HTTP系统提示，实际提示以上述resource为准 |

每个请求包含全部图案例和一个当前任务。图案例没有供应链角色推断权限，也不替代当前许可证原文；合成反条件仅展示逻辑。图的某些摘要有语义/版本疑点，保留标记，不自动注入确定性规则库。若想做消融实验，请新建明确版本与输出目录，不绕过当前完整案例要求。

## 测试、示例与工程文件

| 文件 | 职责 |
|---|---|
| `tests/test_asc.py` | ASC模态、条件、作用范围、包含关系和反例 |
| `tests/test_audit.py` | 双引擎、对象图、人工接口、证据、义务与216条回归 |
| `tests/test_llm.py` | 12案例/40ASC、每次注入、预算、协议、错误与重试、输出合同、预览/续跑、CSV和索引稳定性 |
| `tests/fixtures/chain_216.json` | 从既有normalized_cases快照恢复的216条输入，含来源及哈希；不可当新采集数据 |
| `examples/audit_distribution_case.json` | 小型分发行为调试输入 |
| `examples/audit_distribution_human.json` | 配套人工声明、履行/行为与规则输入示例 |
| `pyproject.toml` | Python版本、包构建、命令行入口、资源打包；运行无第三方依赖 |
| `.gitignore` | 排除缓存、虚拟环境、实验产物和本地凭据资料；不删除本地文件 |

## 文档与来源

| 文件 | 职责 |
|---|---|
| `README.md` | 入口、最短运行流程和当前结果边界 |
| `docs/PROPRIETARY_TERMS.md` | CSV proprietary标签解释与供应商官方协议链接及范围备注 |
| `docs/PROPRIETARY_ASSET_URLS.md` | 可独立转发的五个平台资产URL统计表和许可证原文直达链接 |
| `docs/FILE_GUIDE.md` | 本文：文件和调用关系 |
| `docs/FIGURE10_ASC.md` | 面向人工阅读的12案例/40条ASC、映射与争议说明 |
| `docs/WINDOWS_EXPERIMENT.md` | Windows配置、执行、续跑与排错 |
| `docs/PROMPT_DESIGN.md` | Prompt v2设计、案例展示、义务结构、验证和预览入口 |
| `docs/HISTORY.md` | 各版本变化、历史结论及局限 |
| `docs/cleanup_manifest.json` | 删除的历史文件路径、大小和SHA，便于追查清理范围 |
| `docs/VALIDATION.md` | 本版实际验证记录及未执行范围 |
| `Figure 10.pdf` | 案例原始来源，只读保留 |
| `中转站使用示例.docx` | 用户提供的中转站配置来源，只读保留，可能含密钥，不复制到请求或代码 |

## 生成文件

`output/`是可重建的离线结果，以下均来自当前216条回归复跑：

| 文件 | 内容 |
|---|---|
| `analysis.json` | 完整审计，含摘要、案例、证据与每例结果 |
| `summary.json` | 汇总计数 |
| `normalized_cases.json` | 规范化输入、事实、对象图与规则 |
| `decisions.json` | 简洁判定列表 |
| `license_license.json` | 许可证间比较 |
| `license_behavior.json` | 行为检查 |
| `obligations_by_activity.json` | 活动义务 |
| `joint_obligations.json` | 联合义务可满足性 |
| `review_queue.json` | 逐案人工/规则维护项 |
| `review_tasks.json` | 按类型汇总的待办 |
| `evidence_inventory.json` | 条款和输入来源索引 |
| `rules.json` | 实例化ASC规则 |
| `object_graphs.json` | 逐案对象关系 |
| `components.json` | 已有与待补组件 |
| `human_input.json` | 人工回填文件；重跑时不覆盖已有内容，使用需显式传--human-input |
| `report.html` | 可读审计报告 |

默认 `cache/license_license.sqlite3` 是可再生的跨运行比较库，按键失效规则见 `license_pair_cache.py`。`runs/<实验名>/`的manifest、requests、responses、results、progress、summary职责见Windows文档。`__pycache__/`是Python自动生成缓存；编辑器临时锁文件不属于工程源码。

## 建议调试顺序

1. 用 `cases` 核验案例资源；在 `build_request` 检查某个实际请求的全部上下文。
2. 用一个示例在 `prepare` 检查对象/行为，再在 `analyze_case` 检查规则覆盖与独立引擎结果。
3. 修改规则后跑ASC及审计测试；修改API/prompt后跑LLM测试和dry-run。
4. 单样本真实调用，检查原始响应、结构校验结果与usage；再按固定范围运行批次。准确率评估仍需独立人工标签，Figure频次不是本数据集标签。
