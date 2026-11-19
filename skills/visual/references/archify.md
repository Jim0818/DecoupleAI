# Archify 接入

系统架构和正式结构关系图优先使用用户已有 `~/.claude/skills/archify`。这是调用现有宿主能力的指南，不复制或自动升级第三方 Skill，也不将外部目录加入项目默认资源范围。

## 读取与选型

1. 将 `~` 展开为执行宿主的真实 home，读取 `~/.claude/skills/archify/SKILL.md`。本机核实位置为 `/Users/jim/.claude/skills/archify`，移到其他宿主时按实际安装位置确定。
2. 本次已核实版本为 3.2；以后以实际安装版本的说明、schema 和 CLI 为准。先读对应图型的 authoring defaults、示例及必要 schema，不把示例结构当成当前系统事实。
3. 架构选 architecture；工作步骤选 workflow；调用链选 sequence；数据流选 dataflow；状态选 lifecycle。基于真实代码的图先查所选工程证据，只读本次允许范围。
4. 直接在任务 staging 内写完整 candidate 与目标图文件。用任务授权位置覆盖 Archify 默认 `.archify/` 目录，避免绕过 staging 或另起一套项目。

## 执行与图像交付

现有 3.2 的基本调用形式如下；在项目工作目录运行，替换为真实输入/输出路径：

```bash
node "$HOME/.claude/skills/archify/bin/archify.mjs" finalize architecture \
  <staging/candidate.json> <staging/architecture.html> --quality showcase --json
```

真实代码架构按 Skill 要求增加 `--repo-root` 指向已授权工程。候选 quality 与命令参数一致。失败时读取回执，按该版本的修复上限处理，不把非零退出当成功，不循环安装/更新工具。

文章需要静态图时，按本机 Skill 的 delivery-contract/export 说明生成 PNG 或消费端可显示的图；可交付 HTML 作为可探索补充。用实际存在的导出路径，不猜 CLI 有 `--png` 等参数。纯 HTML 或 candidate 文件不能算文章已有图片。

`finalize` 的自动校验与浏览器检查不等于人工或模型看图。查看真实导出图，检查中文、箭头、层级、裁切与移动端可读性；未查看时报告自动检查状态，不能声称视觉验收通过。

## 不可用与回退

找不到 Skill、Node/浏览器依赖缺失、实际执行失败或不能导出时，报告具体原因。若已有 Mermaid/Excalidraw/SVG 工具能忠实表达，使用它生成并检查成图；必要时在正文保留具体待补图提示。不能悄悄把架构图改成无依据的生成图片。

来源：[Archify 作者仓库](https://github.com/tt-a1i/archify)。本次接入依据本机安装说明；上游更新提示不构成自动升级授权。
