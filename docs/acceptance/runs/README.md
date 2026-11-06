# P6 运行记录目录

`make acceptance-real` 在此写入原始脱敏 JSON 记录。原始记录状态只能是 `failed` 或 `awaiting_human_review`；人工评审另存为 `*-reviewed.json`，不得覆盖原文件。

当前未提交真实模型运行记录，因为本次环境没有配置 DeepSeek API 密钥。不要把密钥、真实学生数据、Cookie、CSRF、隐藏 Prompt 或供应商原始响应写入本目录。
