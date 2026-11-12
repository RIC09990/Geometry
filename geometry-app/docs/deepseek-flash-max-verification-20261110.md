# DeepSeek V4.1 Flash · Max 验收

2026-11-10 按用户最终选择启用，供 2026-11-11 展示准备。

## 当前配置

```json
{
  "model": "deepseek-flash",
  "thinking": {"type": "enabled"},
  "reasoning_effort": "max"
}
```

使用官方 `https://api.deepseek.com`，当前会话及新配置均选择此组合。`deepseek-flash` 对应官方 V4.1-Flash-1017 更新。文字与原始图片直接传给该模型，不增加读图转写、Pro 接力或新的提示词。

旧页面未传思考档位时，由官方 DeepSeek 适配器补为 Max；明确选择 Low 或 High 时仍尊重该选择。其他服务商及自定义地址不注入 DeepSeek 参数。响应的 `reasoningEffort` 元数据反映实际发出的参数，不作为后续聊天内容。

依据：[DeepSeek 更新记录](https://api-docs.deepseek.com/updates/)、[思考模式与档位](https://api-docs.deepseek.com/guides/thinking_mode/)。

## 实际调用

本机通过 `/api/ai/chat` 验收了原图解题、等式变形核对和普通问答。返回元数据为 `deepseek-flash / max`。原始请求资料与回答保存在本机验收目录。

## 自动化与运行状态

- 后端完整回归：447 项通过。
- 前端完整回归：98 项通过；TypeScript 检查通过。
- 新增覆盖实际协议字段、原图字节保留、一轮原生读图、用户显式档位、自定义地址隔离及档位元数据剥离。
- 已构建并重启服务；构建源与输出指纹一致；运行接口返回 `deepseek-flash / max`。
- 当前密钥仍按既有设计只保留在会话内，刷新页面后需重填；模型和 Max 默认配置已更新。

最高思考档不代表所有模型回答都能保证正确。本记录列明已验证的样本与程序行为。

[查看 AI 配置方法](ai-setup.md)
