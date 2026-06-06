"""
#话题 提取工具——从视频标题和描述中自动提取标签。

用法：
  >>> extract_tags("今天天气真好 #旅游 #美食 #旅游")
  ['旅游', '美食']   ← 去重，保持出现顺序

规则：
  - 以 # 开头
  - 后接字母、数字、下划线（Unicode 模式包含中文等所有 Unicode 字母）
  - 遇到空格、标点或结束符时截断
  - 同一个话题只保留第一次出现

正则解释：
  #  → 匹配 # 号本身
  (  → 开始捕获组
  \w → 匹配字母、数字、下划线（re.UNICODE 模式含中文、日文等）
  +  → 至少一个字符
  )  → 结束捕获组

为什么用 findall 而不是 finditer？
  findall 有捕获组时直接返回捕获内容，省去手动提取 match.group(1)。
"""
import re

# 编译一次正则，后续多次使用——比每次调用 re.findall(pattern, text) 高效
_TAG_RE = re.compile(r"#([\w]+)", re.UNICODE)


def extract_tags(text: str) -> list[str]:
    """
    从文本中提取 #话题 标签列表。

    参数：
      text: 任意文本（视频标题 + 描述拼接后的字符串）

    返回：
      去重且保持出现顺序的话题名列表（不含 # 号）

    算法：
      正则找所有匹配 → 遍历 → 检查是否已见过 → 未见过的加入结果
    """
    matches = _TAG_RE.findall(text)
    seen: set[str] = set()
    tags: list[str] = []
    for tag in matches:
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags
