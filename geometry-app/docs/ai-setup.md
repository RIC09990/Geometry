# 通用 AI 配置与验收边界

更新：2026-11-10。

当前用户选择为 DeepSeek V4.1 Flash 最高思考档：官方模型标识 `deepseek-flash`，请求显式发送 `thinking: {type: "enabled"}` 与 `reasoning_effort: "max"`。文字和原始图片直接进入同一模型，不增加 OCR/Pro 转接调用。新配置默认 Max；旧页面未传档位时由官方 DeepSeek 适配器补为 Max，已有的 Low/High 明确选择仍会保留。密钥弹窗在 Chat Completions 与 Responses 协议下都显示“思考档位”，第三方 OpenAI 兼容服务默认不注入（可显式选择）；DeepSeek 系目标（官方域名或模型名含 deepseek）同时发送 `thinking`，其余只发送 `reasoning_effort`，避免不支持该字段的服务返回 400。Anthropic 与 Gemini 的思考参数体系不同，当前不注入，显式选择会返回 422。

该模型名称对应当前官方 V4.1-Flash-1017 更新，思考等级及其映射以 [DeepSeek 更新记录](https://api-docs.deepseek.com/updates/) 和 [思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/) 为依据。最高思考档可能增加等待时间；该配置不是“回答永不出错”的保证。

AI 页、识题页、工作台的多解分析与学生批改共用一个会话配置。点击“填写 API Key / 管理 API Key”，首先粘贴密钥：OpenAI 项目/服务账号密钥、Anthropic API 密钥和 Google 标准 API 密钥的已知格式在本机识别，自动带入对应官方地址。这是格式提示，不等于密钥有效；共享 `sk-` 等不能明确区分的格式只需选择一次服务商，不会逐个平台试钥匙。第三方转发服务始终允许手动覆盖。

点击“连接并使用”后，未填模型时仅向所选官方服务读取可用模型列表，优先选取通用对话模型并排除明显的图像生成、音频、嵌入等模型；不会自动发起聊天收费请求。高级“接口与模型”仍可手动填写。模型列表只证明该账号可见该模型，不保证图片、结构化输出及搜索都被模型支持。支持 Chat Completions、Responses、Anthropic Messages、Gemini 四种 HTTP 协议；自定义服务填写 HTTPS Base URL 与模型。DeepSeek 只是预设之一，不要求所有密钥都符合 sk- 开头。

密钥只保存在当前标签页的 sessionStorage（含服务商与模型选择），不写入本机文件或 localStorage；刷新与站内跳转不丢，关闭浏览器后需要重填。清除操作位于统一的密钥弹窗中，会取消等待并阻止新请求。已提交到服务商的请求不能撤销已有用量。

网页通过本站后端转发请求。个人模式只使用当前请求的密钥，不能回退到服务器密钥；服务器模式不能被访客提供的 Base URL 重定向。公网分享启动器清空两代服务端密钥环境变量，访客自行填写。

需要按对话路由的网关（如 OpenCode Go）会在请求上收到 `x-opencode-session`：网页为每个对话生成稳定标识，服务端只对 `opencode.ai` 写入该头；识题、多解、批改等一次性调用各自生成一个新标识。所有请求同时带 `User-Agent: Geometry/1.0`，不使用 HTTP 库默认的库名。

识题页与 AI 页共用同一份密钥、服务商与模型配置；识别题目同样使用流式，等待时显示读取进度与模型的思考过程，最终结果仍按完整 JSON 校验后填入。

AI 页默认使用流式回答：模型的思考过程来自上游 
easoning_content，实时显示为可折叠的「思考过程」；正文从 JSON content 字段增量解码，最终以服务端解析结果为准。检索第二趟、格式重试和作业复核替换正文前会重置已显示内容。指标按上游 usage 汇总（缓存命中、输入/输出 token、tok/s），未返回时显示「—」。设置中的「显示AI调试信息」打开后，每条回复下显示用时，输入框下显示缓存命中与 token 统计。流式只用于 Chat Completions 协议；Responses、Anthropic、Gemini 自动回退为普通请求。

## 服务端配置

```dotenv
AI_PROVIDER=deepseek
AI_PROTOCOL=chat
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-flash
AI_API_KEY=填写实际密钥
```

其他服务使用对应协议、地址和模型。旧 DEEPSEEK_API_KEY / DEEPSEEK_MODEL 仍作为已有配置的兼容读取，旧页面的密钥请求头也临时接受；界面和新请求均已改用通用名称。密钥不能使用 NEXT_PUBLIC_ 前缀。

## 图像、文件、搜索与批改

- 图片保留实际像素，按所选协议转换为 image_url、input_image、Anthropic image 或 Gemini inlineData；不会把文件名当作识别结果。所选模型本身需要具有视觉能力。
- PDF 由现有 PDF.js 在本机逐页转图，TXT/Markdown 按文本读取。选择、预览附件不会请求模型。
- 普通问题正常回答，只有题目时给出完整解答，提交自己的解答时检查数学含义并纠正实际错误。仅在用户要求评分或批注报告时输出评分数据和 PDF；不再默认给所有作答打分。
- 用户勾选联网搜索，或模型发现需要实时资料并返回 `searchQuery` 时，使用所选服务商的搜索能力：DeepSeek Search API、OpenAI Responses web_search、Claude 原生 web_search 或 Gemini Google Search。地点缺失时先询问。通用兼容服务没有统一搜索协议；搜索失败不编造实时结果或来源。
- 图片批注位置按原图坐标映射；不能可靠定位时不乱画位置。无法辨认的内容不编造分数。
- PDF 使用 ReportLab 5.1.0，在内存中生成，公式由已安装的 Matplotlib 数学排版器生成；没有引入另一套浏览器模型 SDK。测试读取使用 pypdf 7.0.0。PDF 渲染失败与模型回复分开反馈。

## 识题与证明

非退化关系别名正确归入独立字段。不能立即形式化的条件与任意最值/定值表达式完整保存为文字，仍能沟通、编辑、进入工作台、由 AI 联网解答。精确引擎不会跳过文字条件后宣称整个目标已核验。

步骤依赖来自实际列明的前提；已编码的步骤另交 Z3 核验。AI 自然语言候选与已通过的精确结论分开展示。Newclid / NetworkX / NiceGeo 的原接口保留。

## 对话上下文与复核

正常对话只调用模型一次。约 641 字符的系统说明代替原来的长篇提示与完整 schema，也不强制关闭模型的思考模式。最后一条消息是用户当前请求；检索资料、检索失败说明、格式重试与作业复核说明都并入当前请求或其后的消息，system 保持不变，让上游的前缀缓存可以命中。等价变形与不同解法应按数学含义判断，没有写入特定几何题的标准答案。

前后端一致把整个会话连同各轮附件都发给模型，不按长度丢轮次；长度只由压缩控制。上一轮请求超过 24000 输入 token 时，较早轮次（保留最近 4 轮）压缩成一条摘要并写入会话，之后请求只发「摘要 + 最近轮次」；压缩后旧图不再进入上下文。服务商不返回 usage 时按字符数估算 token（半 token/字，图片每张 1100）同样触发压缩；不足 4 轮时只保留当前请求、把之前的内容压成摘要。单请求总字符超过 10 万时服务端直接拒绝并提示新建对话。网页可见的完整聊天记录不受影响。检索正文最多五个来源，JSON 资料约 6000 字符。

官方 DeepSeek 思考请求保留所选档位，使用服务默认输出预算，避免把 Max 思考与正文一起截在 4K/8K。JSON 格式过滤返回空白时，仅重试一次不启用该过滤的请求；题目、格式说明和思考档位不变。AI 请求从排队到搜索、生成、必要复核共用 300 秒总预算；取消等待会中止后续请求。代理和本机网关的等待时间略长，保证错误说明能正常返回页面。

评分结果先做本地格式、算术和分数一致性检查；只有发现具体矛盾时才重试一次。重试基于原题和原作答，不把首轮改写后的答案当成学生答案。校验失败时不发布未经核验的评分或 PDF。这不是任意数学证明的形式验证，外部模型的自然语言回答仍可能出错。

## 已运行与未运行

本地测试覆盖四协议文字/真实图片字节、同一密钥转发、搜索来源解析、多轮消息字段兼容、识题别名与文字条件、PDF 得分/原图/批注/分式、服务端凭据隔离。这些协议测试使用隔离 HTTP 上游，不能称为各厂商真实付费调用均已通过。

官方接口依据：[DeepSeek 视觉](https://api-docs.deepseek.com/guides/vision/)、[DeepSeek 搜索](https://api-docs.deepseek.com/guides/search/)、[OpenAI Web search](https://developers.openai.com/api/docs/guides/tools-web-search)、[Claude API](https://platform.claude.com/docs/en/api/overview)、[Gemini generateContent](https://ai.google.dev/api/generate-content)。



AI 页的会话历史保存在本机 `geometry-app/.local/ai-conversations/`，每条对话一个 JSON 文件（含上传图片），单条上限 24 MiB；支持新建、切换、重命名、删除与搜索标题或正文。记录不写入浏览器存储，删除对话即删除对应文件。
