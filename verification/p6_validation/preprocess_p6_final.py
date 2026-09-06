"""Preprocess p6_final.md to add proper Markdown heading structure.

This script transforms nested list structures into proper Markdown headings
so Docling can extract heading_path for hotspot retrieval validation.

Process:
1. Identify time-stamp nodes (00:01, 00:31, etc.) as ## headings
2. Identify topic nodes (传统软件比喻, AI产品经理核心DNA) as ### headings
3. Preserve nested list content as regular text
4. Output structured Markdown for full pipeline validation
"""
from __future__ import annotations

import re
from pathlib import Path

SOURCE_FILE = Path("E:/obsidisen/默认/p6_final.md")
OUTPUT_FILE = Path("E:/obsidisen/默认/p6_final_structured.md")

# Heading inference rules
TIME_STAMP_PATTERN = re.compile(r"^\d{2}:\d{2}$")
TOPIC_KEYWORDS = [
    "传统软件比喻",
    "AI产品经理核心DNA",
    "智能来源比喻",
    "AI产品智能来源",
    "数据驱动概念",
    "传统产品经理关注点",
    "淘宝案例流程",
    "传统流程特点",
    "AI产品经理的角色转变",
    "工作重心",
    "厨师比喻",
    "AI产品落地首个环节",
    "护城河理论",
    "数据处理步骤",
    "数据清洗标注",
    "菜品清洗比喻",
    "李菲菲案例",
    "数据工作的重要性",
    "数据闭环飞轮",
    "抖音案例",
    "用户行为数据",
    "推荐机制",
    "AI产品经理的思考方向",
    "特斯拉案例",
    "摄像头配置",
    "数据收集机制",
    "AB test 预演",
    "闭环流程",
    "核心思维要求",
    "传统客服产品流程",
    "产品类型",
    "设计拆解步骤",
    "数据驱动整体逻辑",
    "AI产品跟传统产品最大的区别",
    "孩子学习写报告的案例",
    "大模型问答的演示案例",
    "传统产品经理转型或转型时的感受",
    "AI产品经理应该关注的点",
    "关注点一：管理用户预期",
    "关注点二：保证数据闭环",
    "关注点三：评估功能",
    "关注点四：持续进化",
    "AI产品经理的角色定义",
    "模型健康状态监测",
    "模型优化与进修",
    "AI 产品分类与矩阵",
    "动态演进路线",
    "AI 产品矩阵象限细分",
    "现状分布",
    "赋能与感知应用案例",
    "替代与认知智能",
    "认知与赋能",
    "AI PM 与传统 PM 进化",
    "团队与向上管理",
    "沟通对象边界拓展",
    "第二个团队",
    "人际关系的设计",
    "关系设计的影响",
    "案例分享",
    "用户画像",
    "推荐列表",
    "准确性说明",
    "迭代逻辑",
    "匹配要点",
    "总结",
]


def detect_heading_level(text: str, indent_level: int) -> int | None:
    """Detect heading level based on time-stamp pattern or topic keywords.

    Returns:
        2 for time-stamp nodes (##)
        3 for topic keywords (###)
        None for regular list items
    """
    stripped = text.strip()

    # Time-stamp nodes -> ## (second level)
    if TIME_STAMP_PATTERN.match(stripped):
        return 2

    # Topic keywords -> ### (third level)
    for keyword in TOPIC_KEYWORDS:
        if keyword in stripped:
            return 3

    return None


def parse_nested_list(lines: list[str]) -> list[tuple[int, str]]:
    """Parse nested list structure and return (indent_level, text) pairs.

    Indent level is determined by leading spaces before '-' marker.
    """
    parsed: list[tuple[int, str]] = []
    for line in lines:
        if not line.strip():
            continue

        # Count indent level (spaces before '-')
        match = re.match(r"^(\s*)-\s+(.+)$", line)
        if match:
            spaces = match.group(1)
            indent = len(spaces) // 2  # Each level = 2 spaces
            text = match.group(2).strip()
            parsed.append((indent, text))

    return parsed


def build_heading_text(text: str, parent_context: list[str]) -> str:
    """Build heading text with context from parent nodes."""
    # Clean up text
    cleaned = text.strip()

    # For time-stamp nodes, add parent context if available
    if TIME_STAMP_PATTERN.match(cleaned) and parent_context:
        # Find last non-time-stamp parent
        for parent in reversed(parent_context):
            if not TIME_STAMP_PATTERN.match(parent):
                return f"{cleaned} - {parent}"
        return cleaned

    return cleaned


def convert_to_markdown_headings(parsed: list[tuple[int, str]]) -> list[str]:
    """Convert parsed nested list to Markdown with proper headings."""
    output: list[str] = []

    # Always preserve the first level-1 heading
    output.append("# AI产品经理项目实战与深度思考架构分析\n")

    # Track parent nodes for context
    parent_stack: list[str] = []

    # Skip the first line (already added as # heading)
    for indent, text in parsed[1:]:
        heading_level = detect_heading_level(text, indent)

        # Update parent stack
        while len(parent_stack) > indent:
            parent_stack.pop()
        if indent <= len(parent_stack):
            if parent_stack and parent_stack[-1] != text:
                parent_stack.append(text)

        if heading_level == 2:
            # ## heading (time-stamp nodes)
            heading_text = build_heading_text(text, parent_stack[:-1])
            output.append(f"\n## {heading_text}\n")
        elif heading_level == 3:
            # ### heading (topic nodes)
            heading_text = text
            output.append(f"\n### {heading_text}\n")
        else:
            # Regular list item
            output.append(f"- {text}\n")

    return output


def main() -> None:
    """Main preprocessing pipeline."""
    print(f"Reading source: {SOURCE_FILE}")
    source_content = SOURCE_FILE.read_text(encoding="utf-8")
    lines = source_content.splitlines()

    print(f"Parsing nested structure...")
    parsed = parse_nested_list(lines)
    print(f"  Found {len(parsed)} nodes")

    print(f"Converting to Markdown headings...")
    markdown_lines = convert_to_markdown_headings(parsed)

    print(f"Writing output: {OUTPUT_FILE}")
    OUTPUT_FILE.write_text("\n".join(markdown_lines), encoding="utf-8")

    print(f"[OK] Preprocessing complete")
    print(f"   Source: {SOURCE_FILE.stat().st_size} bytes")
    print(f"   Output: {OUTPUT_FILE.stat().st_size} bytes")

    # Show sample output
    print(f"\n=== Sample output (first 20 lines) ===")
    for line in markdown_lines[:20]:
        print(line.rstrip())


if __name__ == "__main__":
    main()