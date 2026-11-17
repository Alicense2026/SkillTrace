# Figure 10 到 ASC 的转换

来源：工具根目录 `Figure 10.pdf`，1 页、12 行。PDF SHA-256：`011d74597c1b462fcbb1600882b16c87bfb38b08c4228690cec74601f6c637fe`。

保留图的分类、箭头、操作与频次；不把图的左右方向擅自认定为上下游。O/R 是图中分类编号。`counterexample` 为构造测试，不是另一许可证的真实条款。

|案例|图中组合|操作 → A|频次|转换条数|
|---|---|---|---:|---:|
|figure10-01|Apache 2.0 → LLaMA3|Fine-tune → Modify|14873|5|
|figure10-02|Apache 2.0 → Gemma|Fine-tune → Modify|5082|2|
|figure10-03|CC-BY-NC-4.0 → LLaMA3.1|Fine-tune → Modify|261|6|
|figure10-04|CreativeML-OpenRAIL-M → CC-BY-NC-4.0|Fine-tune → Modify|1569|1|
|figure10-05|LLaMA3.1 → (LLaMA3, CC-BY-NC-4.0)|Merge → Combine|525|5|
|figure10-06|OpenRAIL → GPL 3.0|Fine-tune → Modify|111|3|
|figure10-07|CreativeML-OpenRAIL-M → LLaMA3|Fine-tune → Modify|84|5|
|figure10-08|CreativeML-OpenRAIL-M → Gemma|Fine-tune → Modify|37|2|
|figure10-09|Gemma → LLaMA3.1|Fine-tune → Modify|34|5|
|figure10-10|Apache 2.0 → CC-BY-NC-4.0|Main-Data → Use|2417|1|
|figure10-11|Apache 2.0 → CC-BY-NC-SA-4.0|Quantize → Modify|465|2|
|figure10-12|Apache 2.0 → GPL 3.0|Fine-tune → Modify|249|3|

## 逐项 ASC

实际机器可读数据位于 `license_checker/resources/figure10_cases.json`，每次请求全量注入 12 个案例。

### figure10-01 Apache 2.0 → LLaMA3

**O2 / LLaMA3**：提供 LLaMA3 协议副本。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-01:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "include_license:LLaMA3"
  }
}
```

**O6 / LLaMA3**：在相关数字资产上显著展示 Built with Meta Llama 3。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-01:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "display_notice:Built with Meta Llama 3"
  }
}
```
分发是本例采用的触发假设；图中文字的 all related digital assets 范围需原文判定。

**R1 / LLaMA3**：遵守所包含的可接受使用政策。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-01:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "comply_with_aup:LLaMA3"
  }
}
```

**R2 / LLaMA3**：超过七亿月活跃用户时必须申请许可。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-01:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": "monthly_active_users_gt_700m",
    "requires": "special_license_requested:LLaMA3"
  }
}
```
申请不等于获准；阈值统计对象与时点图中未说明。

**R4 / LLaMA3**：图称禁止用模型输出训练竞争性 AI 模型。
```json
{
  "A": "TrainModel",
  "S": {
    "artifact": "figure10-01:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PROHIBITED",
    "when": true,
    "requires": {
      "all": [
        "uses_outputs:LLaMA3",
        "trains_competing_model"
      ]
    }
  }
}
```
SOURCE_CLAIM_NOT_VERIFIED；特别是 LLaMA3.1 不将该图概括自动升级为已核实条款。

### figure10-02 Apache 2.0 → Gemma

**O7 / Gemma**：将基于使用的限制传递到许可中。
```json
{
  "A": "Sublicense",
  "S": {
    "artifact": "figure10-02:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "pass_through_use_restrictions:Gemma"
  }
}
```

**O2 / Gemma**：提供 Gemma 许可副本。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-02:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "include_license:Gemma"
  }
}
```

### figure10-03 CC-BY-NC-4.0 → LLaMA3.1

**O2 / LLaMA3.1**：提供 LLaMA3.1 协议副本。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-03:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "include_license:LLaMA3.1"
  }
}
```

**O6 / LLaMA3.1**：在相关数字资产上显著展示 Built with Meta Llama。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-03:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "display_notice:Built with Meta Llama"
  }
}
```
分发是本例采用的触发假设；图中文字的 all related digital assets 范围需原文判定。

**R1 / LLaMA3.1**：遵守所包含的可接受使用政策。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-03:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "comply_with_aup:LLaMA3.1"
  }
}
```

**R2 / LLaMA3.1**：超过七亿月活跃用户时必须申请许可。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-03:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": "monthly_active_users_gt_700m",
    "requires": "special_license_requested:LLaMA3.1"
  }
}
```
申请不等于获准；阈值统计对象与时点图中未说明。

**R4 / LLaMA3.1**：图称禁止用模型输出训练竞争性 AI 模型。
```json
{
  "A": "TrainModel",
  "S": {
    "artifact": "figure10-03:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PROHIBITED",
    "when": true,
    "requires": {
      "all": [
        "uses_outputs:LLaMA3.1",
        "trains_competing_model"
      ]
    }
  }
}
```
SOURCE_CLAIM_NOT_VERIFIED；特别是 LLaMA3.1 不将该图概括自动升级为已核实条款。

**R2 / CC-BY-NC-4.0**：仅用于非商业目的。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-03:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": "exercising_licensed_rights",
    "requires": {
      "not": "commercial_purpose"
    }
  }
}
```
仅约束适用许可权利的行使，不泛化为用户所有经营或收费行为。

### figure10-04 CreativeML-OpenRAIL-M → CC-BY-NC-4.0

**R2 / CC-BY-NC-4.0**：仅用于非商业目的。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-04:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": "exercising_licensed_rights",
    "requires": {
      "not": "commercial_purpose"
    }
  }
}
```
仅约束适用许可权利的行使，不泛化为用户所有经营或收费行为。

### figure10-05 LLaMA3.1 → (LLaMA3, CC-BY-NC-4.0)

**R2 / CC-BY-NC-4.0**：仅用于非商业目的。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-05:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": "exercising_licensed_rights",
    "requires": {
      "not": "commercial_purpose"
    }
  }
}
```
仅约束适用许可权利的行使，不泛化为用户所有经营或收费行为。

**R2 / LLaMA3.1**：超过七亿月活跃用户时必须申请许可。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-05:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": "monthly_active_users_gt_700m",
    "requires": "special_license_requested:LLaMA3.1"
  }
}
```
申请不等于获准；阈值统计对象与时点图中未说明。

**O2 / LLaMA3**：提供 LLaMA3 协议副本。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-05:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "include_license:LLaMA3"
  }
}
```

**O6 / LLaMA3**：在相关数字资产上显著展示 Built with Meta Llama 3。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-05:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "display_notice:Built with Meta Llama 3"
  }
}
```
分发是本例采用的触发假设；图中文字的 all related digital assets 范围需原文判定。

**O6 / LLaMA3.1**：在相关数字资产上显著展示 Built with Meta Llama。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-05:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "display_notice:Built with Meta Llama"
  }
}
```
分发是本例采用的触发假设；图中文字的 all related digital assets 范围需原文判定。

### figure10-06 OpenRAIL → GPL 3.0

**O2 / GPL-3.0**：提供 GPL 3.0 许可文本。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-06:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "include_license:GPL-3.0"
  }
}
```

**O5 / GPL-3.0**：修改版本分发时沿用 GPL 3.0。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-06:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "outbound_license:GPL-3.0"
  }
}
```

**O3 / GPL-3.0**：图中文字为提供 Licensed Material 的链接。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-06:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "licensed_material_link"
  }
}
```
图的栏目名为 Source/Weights Disclosure，但正文只提链接；不将链接自动等同对应源码或权重披露。

### figure10-07 CreativeML-OpenRAIL-M → LLaMA3

**O2 / LLaMA3**：提供 LLaMA3 协议副本。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-07:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "include_license:LLaMA3"
  }
}
```

**O6 / LLaMA3**：在相关数字资产上显著展示 Built with Meta Llama 3。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-07:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "display_notice:Built with Meta Llama 3"
  }
}
```
分发是本例采用的触发假设；图中文字的 all related digital assets 范围需原文判定。

**R1 / LLaMA3**：遵守所包含的可接受使用政策。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-07:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "comply_with_aup:LLaMA3"
  }
}
```

**R2 / LLaMA3**：超过七亿月活跃用户时必须申请许可。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-07:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": "monthly_active_users_gt_700m",
    "requires": "special_license_requested:LLaMA3"
  }
}
```
申请不等于获准；阈值统计对象与时点图中未说明。

**R4 / LLaMA3**：图称禁止用模型输出训练竞争性 AI 模型。
```json
{
  "A": "TrainModel",
  "S": {
    "artifact": "figure10-07:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PROHIBITED",
    "when": true,
    "requires": {
      "all": [
        "uses_outputs:LLaMA3",
        "trains_competing_model"
      ]
    }
  }
}
```
SOURCE_CLAIM_NOT_VERIFIED；特别是 LLaMA3.1 不将该图概括自动升级为已核实条款。

### figure10-08 CreativeML-OpenRAIL-M → Gemma

**O7 / Gemma**：将基于使用的限制传递到许可中。
```json
{
  "A": "Sublicense",
  "S": {
    "artifact": "figure10-08:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "pass_through_use_restrictions:Gemma"
  }
}
```

**O2 / Gemma**：提供 Gemma 许可副本。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-08:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "include_license:Gemma"
  }
}
```

### figure10-09 Gemma → LLaMA3.1

**O2 / LLaMA3.1**：提供 LLaMA3.1 协议副本。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-09:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "include_license:LLaMA3.1"
  }
}
```

**O6 / LLaMA3.1**：在相关数字资产上显著展示 Built with Meta Llama。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-09:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "display_notice:Built with Meta Llama"
  }
}
```
分发是本例采用的触发假设；图中文字的 all related digital assets 范围需原文判定。

**R1 / LLaMA3.1**：遵守所包含的可接受使用政策。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-09:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "comply_with_aup:LLaMA3.1"
  }
}
```

**R2 / LLaMA3.1**：超过七亿月活跃用户时必须申请许可。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-09:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": "monthly_active_users_gt_700m",
    "requires": "special_license_requested:LLaMA3.1"
  }
}
```
申请不等于获准；阈值统计对象与时点图中未说明。

**R4 / LLaMA3.1**：图称禁止用模型输出训练竞争性 AI 模型。
```json
{
  "A": "TrainModel",
  "S": {
    "artifact": "figure10-09:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PROHIBITED",
    "when": true,
    "requires": {
      "all": [
        "uses_outputs:LLaMA3.1",
        "trains_competing_model"
      ]
    }
  }
}
```
SOURCE_CLAIM_NOT_VERIFIED；特别是 LLaMA3.1 不将该图概括自动升级为已核实条款。

### figure10-10 Apache 2.0 → CC-BY-NC-4.0

**R2 / CC-BY-NC-4.0**：仅用于非商业目的。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-10:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": "exercising_licensed_rights",
    "requires": {
      "not": "commercial_purpose"
    }
  }
}
```
仅约束适用许可权利的行使，不泛化为用户所有经营或收费行为。

### figure10-11 Apache 2.0 → CC-BY-NC-SA-4.0

**R2 / CC-BY-NC-SA-4.0**：仅用于非商业目的。
```json
{
  "A": "Use",
  "S": {
    "artifact": "figure10-11:covered-artifact",
    "kind": "OriginalArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": "exercising_licensed_rights",
    "requires": {
      "not": "commercial_purpose"
    }
  }
}
```
仅约束适用许可权利的行使，不泛化为用户所有经营或收费行为。

**O5 / CC-BY-NC-SA-4.0**：修改版本分发时沿用 CC-BY-NC-SA-4.0。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-11:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "outbound_license:CC-BY-NC-SA-4.0"
  }
}
```

### figure10-12 Apache 2.0 → GPL 3.0

**O2 / GPL-3.0**：提供 GPL 3.0 许可文本。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-12:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "include_license:GPL-3.0"
  }
}
```

**O5 / GPL-3.0**：修改版本分发时沿用 GPL 3.0。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-12:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "outbound_license:GPL-3.0"
  }
}
```

**O3 / GPL-3.0**：图中文字为提供 Licensed Material 的链接。
```json
{
  "A": "Distribute",
  "S": {
    "artifact": "figure10-12:covered-artifact",
    "kind": "ModifiedArtifact"
  },
  "C": {
    "kind": "CONDITIONALLY_PERMITTED",
    "when": true,
    "requires": "licensed_material_link"
  }
}
```
图的栏目名为 Source/Weights Disclosure，但正文只提链接；不将链接自动等同对应源码或权重披露。

## 边界

- 图中左右箭头仅按印刷顺序保存，不能自动分配供应链角色。
- O/R 编号是图中分类编号，不是许可证正式条款编号。
- occurrences 是图报告频次，不是本项目实验结果。
- R4 与 O3 等争议摘要保留并标记；不得据此捏造精确法律文本。
- Fine-tune/Quantize 归为 Modify 不自动推出法定 DerivativeWork；示例中的 ModifiedArtifact 是建模选择。
- TrainModel 是新增实验活动；不扩张现有 chain 的 16 活动矩阵。
- LLaMA3.1 的 R4 和 GPL O3 保留 SOURCE_CLAIM_NOT_VERIFIED/语义差异；不会自动装载为确定性正式规则。
- 同许可延续与版权声明保留不是同一要求；允许收费也不等于商用场景已满足非商业许可条件。
