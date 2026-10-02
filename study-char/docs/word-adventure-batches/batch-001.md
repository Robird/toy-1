# 单词小冒险第 1 批制作记录

日期：2026-10-02

状态：完成

用户要求：完整收录仓库根目录 `小学英语大纲词汇.txt` 中的词汇。有合适 emoji 就显示，其余通过中文含义和听音学习；支持短语拼写。使用 `gpt-6-luna` 子 agent 整理内容，将 `distractorCount`、`showSpelling` 改成页面级参数。

源词表共 441 条，全部收录。保留原有但不在源词表中的 HAT、CUP，最终共 443 条。从最初的 6 条新增 437 条，无重复单词或重复 ID。旧词补图数量：0。

图示分布：188 条 emoji、1 条已有猫 SVG、254 条中文与听音。本批没有新增 SVG。

## 并行任务

| 负责人 | 非空词条序号范围 | 全量阶段新交条数 | 交稿位置 |
| --- | --- | --- | --- |
| batch001_animals | 1 到 147 | 133 | `work/word-adventure/batch-001/worker-a/full-vocabulary.json` |
| batch001_food | 148 到 294 | 146 | `work/word-adventure/batch-001/worker-b/full-vocabulary.json` |
| batch001_objects | 295 到 441 | 146 | `work/word-adventure/batch-001/worker-c/full-vocabulary.json` |

三个 worker 均使用用户建议的 `gpt-6-luna`。初稿的 12 条候选也在本批内，全量阶段又交 425 条，共新增 437 条。分段按非空条目序号，源文件的实际行号另存于正式清单。

主 agent 核对完整覆盖及唯一性，纠正 HIS 被误读为 THIS、司机配为飞行员等错误，清理用邻近物体代替目标词义的图示，并复核介词、代词和称谓。WANT、THE、FAN 的释义已修订；CLOSE 限定为“关闭”，避免同时教授不同发音的义项。

## 关卡清单

全部已接入。逐词 ID、中文义项、emoji、源文件行号、状态和负责人见 [完整清单](../../work/word-adventure/batch-001/inventory.json)。游戏内 `WORD_POOL` 是正式数据；本批文件是过程记录，后续修改游戏时同步更新清单。

可在 [词库预览](../../work/word-adventure/batch-001/preview.html) 搜索英文、中文或只查看有图示的词。

## 页面与配置改动

- `WORD_POOL` 仅保存内容，必需字段是 `id`、`word`、`meaning`、`illustration`；不再逐词保存难度。
- 页面脚本开头 `DEFAULT_GAME_OPTIONS` 集中设置默认干扰数 2 和默认显示拼写。
- URL 支持 `?distractorCount=4&showSpelling=false`。干扰数接受 0 到 26 的整数，并以实际剩余字母数为上限；非法参数回退默认值。
- `illustration: ''` 显示中文提示卡，emoji 关卡直接使用现有渲染能力；猫 SVG 保留。
- ICE CREAM、PHYSICAL EDUCATION 的空格自动分隔，只输入字母；字母格和进度不把空格计入。超过 8 个字母的词使用较小字母格，窄屏可换行。
- `display` 保留 I、China 等规范大小写；`speech` 为 MR、MRS、MS、PE、TV 提供合适的朗读文本。
- 交付仍是可直接通过本地文件打开的单 HTML，无外部图片依赖。尚未建立通用 SVG 注册表。

## 验收结果

使用独立 Chrome headless 浏览器，直接以本地文件打开游戏及预览。验收辅助脚本仅通过浏览器调试注入指定抽取位置，正式页面没有添加选题或测试入口。

- 441 个源词全部覆盖；总数 443，ID 与单词分别唯一，词条没有重复难度字段。
- 逐一运行全部 443 个关卡，确认图示或中文显示、字母格数量、干扰字母数、完整拼写、重复字母、积分保存和手动下一关。
- 使用 390 px 窄屏检查全部关卡无横向溢出；检查自动下一关仍在真实 3200 ms 延迟后发生。
- 检查 7 组全局参数：默认、零干扰、4 个干扰、上限 26、负数、超过上限、非数字及无效布尔值。隐藏拼写时说明文案不显示英文，拼写完成仍正常。
- 实际查看 emoji 联系表，以及苹果、AM、长词和两个短语的窄屏截图。Windows 将中国国旗 emoji 显示为 CN，CHINA 已改为中文提示。
- 最终修订后，对 23 个受影响条目补做检查，包括长词尺寸、CHINA 提示模式和 4 项释义修订；再次通过参数及自动下一关检查。

完整运行结果见 [verification.json](../../work/word-adventure/batch-001/verification.json)，最终修订后的检查见 [verification-followup.json](../../work/word-adventure/batch-001/verification-followup.json)。截图与验收辅助文件位于同一批次目录。

语音检查使用模拟 speech synthesis，核对整词、逐字母、短语及缩写的朗读文本顺序；没有实际试听系统英文声音。声音可用性与发音仍取决于用户设备的语音引擎。原有胜利音效未做实际试听。emoji 的外观也随系统变化。

## 下次继续

本词表已全部覆盖，没有剩余词待接入。下一次扩词从 `batch-002` 开始，先读取实际 `WORD_POOL`，再对新的词汇来源查重。不要重新加入本表条目，也不要把英美变体误删成重复。

本批的 `assemble.cjs` 是当时的整理辅助文件，不能作为未来批次的通用构建命令；后续以实际页面和新来源为准。`inspect.cjs` 使用本批固定数量与本地 Chrome 调试端口，仅适用于复查本批。

验收浏览器已关闭。自动审批因策略阻止拒绝删除本批临时 `browser-profile` 目录，该目录已由本批 `.gitignore` 忽略，不属于交付内容。
