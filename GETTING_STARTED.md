# TextPicOS v1.0 使用说明

## 给主管目标

在项目会话中直接说明账号、目标、已有材料和必须保留的内容。已有原稿应作为明确输入；缺少真正影响结果的决定时，主管会集中提问。

例如：为数据 STUDIO 写一篇工具试用教程，使用我提供的原稿与实测材料，保留代码和截图；完成后交付可读正文，并判断需要补哪些图。

主管按缺口组织研究、写作、审阅与视觉工作。视觉评估每个内容任务都会进行，具体生成、来源图复用或待补图标记遵守当前视觉方法。

## 选择下一篇

可以直接说“从智性未来的现行题库选下一篇 Agent 上手教程”，或“根据本周指定工具
的官方更新与使用问题，给数据 STUDIO 找值得研究的题”。已有明确题目就直接给题，
不必先巡检热点。主管会结合当前范围、已选登记、证据和材料缺口给出理由，并保存
需要继续使用的候选。具体操作和反馈方式见 [选题使用说明](docs/runbooks/topic-selection.md)。

## 继续修改

直接给出局部反馈，例如“只把开头改口语一些，保留后面的代码、图和链接”。主管在同一运行和成品上续改，旧任务不能覆盖新批次。

## 发布

写完会交付成品。发布需要明确指令，并以当前完成版本及真实引用图片为依据。维护本系统时不会自动执行文章发布或写入外部资料库。

## 工程入口

进入项目根，使用现有含 PyYAML、jsonschema、pytest 的 Python 环境。当前本机为 /opt/miniconda3/envs/autogen/bin/python；需要时通过 TEXTPICOS_PYTHON 指定解释器。

```bash
python scripts/textpicos.py start demo-edit "修改所选原稿的首段" --account studio --input workspace/inputs/source.md --deliverable workspace/outputs/result.md
python scripts/textpicos.py status demo-edit
bash scripts/audit.sh --scope system
```

示例输入必须先实际存在；持续派工、提交、恢复及发布命令见 [运行操作](docs/runbooks/supervisor-operations.md)。脚本提供状态与交接能力，真实员工由宿主执行。

## 当前约定

账号和选题依据读取 config/accounts 及当前选题策略，不使用固定历史候选表。岗位与方法依据 config/system/capabilities.json，历史记录不能作为正在执行的岗位。

当前只支持新接口。系统维护不访问 articles，也不移动明确保护的归档目录。需要查看目录归属时阅读 [目录说明](docs/file-organization.md)。

