#!/usr/bin/env python3
"""Inject auto-generated skills index into README.md."""
import re, sys

readme_path = sys.argv[1]

# Build index by scanning my-skills/
import os, glob
repo_root = os.path.dirname(readme_path)
skills_dir = os.path.join(repo_root, 'my-skills')
entries = []

if os.path.isdir(skills_dir):
    for skill_name in sorted(os.listdir(skills_dir)):
        skill_dir = os.path.join(skills_dir, skill_name)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, 'SKILL.md')
        if not os.path.isfile(skill_md):
            continue

        with open(skill_md) as f:
            content = f.read()

        # Extract name from frontmatter
        name_match = re.search(r'^name:\s*(.+)$', content, re.MULTILINE)
        name = name_match.group(1).strip() if name_match else skill_name

        # Extract description (multi-line YAML >)
        desc_match = re.search(r'^description:\s*>\s*\n((?:\s{2,}.+\n?)+)', content, re.MULTILINE)
        if desc_match:
            desc_lines = [l.strip() for l in desc_match.group(1).strip().split('\n')]
            desc = ' '.join(desc_lines)[:250]
        else:
            desc_match = re.search(r'^description:\s*(.+)$', content, re.MULTILINE)
            desc = desc_match.group(1).strip()[:250] if desc_match else ''

        # First heading after frontmatter as pitch
        body = re.split(r'^---\s*$', content, maxsplit=2, flags=re.MULTILINE)
        pitch = ''
        if len(body) >= 3:
            pitch_match = re.search(r'^#+\s*(.+)$', body[2], re.MULTILINE)
            if pitch_match:
                pitch = pitch_match.group(1).strip()

        entries.append(f"""### [{name}](my-skills/{skill_name}/)

> {pitch}

{desc}

```bash
# 安装
cp -r my-skills/{skill_name} ~/.claude/skills/
```

""")

index = '\n'.join(entries) if entries else '_（暂无，欢迎贡献）_'

# Inject into README
with open(readme_path) as f:
    readme = f.read()

marker_start = '<!-- SKILLS_INDEX_START -->'
marker_end = '<!-- SKILLS_INDEX_END -->'

if marker_start in readme and marker_end in readme:
    new_readme = re.sub(
        f'{re.escape(marker_start)}.*?{re.escape(marker_end)}',
        f'{marker_start}\n{index}\n{marker_end}',
        readme, flags=re.DOTALL
    )
    with open(readme_path, 'w') as f:
        f.write(new_readme)
    print(f'✓ Injected {len(entries)} skill(s) into README')
else:
    print('ERROR: README 缺少 SKILLS_INDEX 标记', file=sys.stderr)
    sys.exit(1)
