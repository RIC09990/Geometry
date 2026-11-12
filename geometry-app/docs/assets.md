# 视觉资产

用户提供的四张原始参考图保存在 `docs/references/`，用于对照页面风格与布局。

`public/archive-collage.png` 是使用内置 ImageGen 生成的网站背景，未使用 CLI/API 回退。根据用户后续决定，供案例列表、建题和工作台使用。它是装饰背景，界面文字、按钮和交互均由实际网页实现。

生成提示词：

> Use case: historical-scene. Asset type: full-bleed background texture for a Chinese geometry learning website; decorative artwork only, NOT a website screenshot and NO interface. Create a wide 16:9 tactile vintage scrapbook collage in the muted ivory, gray brown, taupe and desaturated olive palette of an old mathematician's notebook. Overlapping torn paper, subtle fine paper fibers, antique thin-line Euclidean geometry engravings, a small engraving of a drawing compass near the far right edge, cropped classical marble bust at the upper right edge. Keep the middle and left half visually quiet, light ivory parchment, suitable for readable foreground cards later. No words, no letters, no numbers, no titles, no user interface, no rectangular UI panels, no navigation, no watermark. Rich realistic paper textures and soft cast shadows, scholarly archival mood.

首页旧重复矢量背景 `euclid-plate.svg` 已替换并删除；现在使用下方注明来源的真实原书图版。首页旧三角形线稿及专用样式已被删除。

`vendor/jsxgraph.css` 复制自实际安装的 JSXGraph 1.14.3 包，保留上游版权说明。复制的原因是当前 npm 包的 exports 未导出 CSS 子路径。画板逻辑仍使用正式 npm 模块。

## 首页莫比乌斯环（2026-11-09 透明版）

- 文件：`public/mobius-strip.png`（1086 × 1448，1,036,838 字节）。RGBA，透明度范围0—255，外背景及环内孔透明。
- 作者：SIMON LEE。
- 来源：[Unsplash 原作 smh3Gm6tH6I](https://unsplash.com/photos/smh3Gm6tH6I)。图片来自该页面正式下载链接对应的 `photo-1644212830458-32ef05d37772`。
- 许可：[Unsplash License](https://unsplash.com/license)，允许下载及网站使用。
- 使用内置 ImageGen 编辑原作，转换为黑白银灰并提取透明背景，没有使用 CLI/API 回退。页面直接显示透明 PNG；已删除旧 JPEG 和临时候选图，移除灰度反相、混合模式和放大裁切样式。外框沿用旁边卡片的毛玻璃材质，保留标题及底部文案空间，不增加运行依赖。

最终编辑提示词：

> Use case: background-extraction. Edit target: the supplied Möbius strip photograph, for the Geometry homepage. Remove the entire background to actual transparent alpha, including the open central hole. Keep precisely the same single twisted Möbius ribbon shape, proportions, camera angle and orientation. Convert the ribbon itself to neutral black/white/silver gray with realistic smooth reflective highlights and rich material detail. The full ribbon must fit uncropped with a small transparent margin. No white, gray or black rectangle, no opaque studio background, no floor, no drop shadow outside the object, no text, no checkerboard painted into pixels. Preserve antialiased edges and output a genuinely transparent PNG cutout.


## 首页真实原书背景（2026-11-09）

- 资产：`public/euclid-book1-plate1.ca30d8a2806e.jpg`，927 × 1600，176,606 字节。原始图像字节保持不变，以SHA-256前12位命名供浏览器缓存一周；完整SHA-256为`ca30d8a2806e29aa0b149772cd10bd95f6485fe7eea69cc66113cd26adfebd57`。
- 原书：Jacques Ozanam（1640—1717），*Cursus mathematicus: or, a compleat course of the mathematicks*，1712年伦敦版，第1卷，*Book 1, Euclid’s Elements, Plate 1, Page 4*。图版含21幅不同的角、圆、三角形与多边形图，正是参考图所显示的原书图版。
- 扫描来源：Wellcome Library / Internet Archive，标识 `b30531548_0001`；[原馆藏扫描](https://archive.org/details/b30531548_0001)，[Wikimedia Commons 文件及授权页](https://commons.wikimedia.org/wiki/File:Cursus_mathematicus-_or,_a_compleat_course_of_the_mathematicks_..._The_whole_illustrated_with_near_200_copper_plates_(IA_b30531548_0001).pdf)。
- 授权：来源标注 Public Domain Mark 1.0，原作作者逝世已超过100年，出版早于1931年。
- 取自公开扫描PDF的第119页，使用已有Poppler按1600px导出单页JPEG；没有生成或重画图版。原书暂存PDF与试读页已清理，未向项目安装依赖。
- 仅首页背景改用该图版，整幅铺设、`no-repeat`，以CSS灰度匹配黑白参考；保留现有浅色覆层。莫比乌斯环、卡片、毛玻璃材质、文字、导航位置和其他页面不作修改。
