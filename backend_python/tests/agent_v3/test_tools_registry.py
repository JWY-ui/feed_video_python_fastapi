"""注册表的不变量。

单个工具的行为各自有测试；这里守的是"整体"那几条 —— 尤其**哪些工具必须确认**。
写错一个 tier 就等于让模型绕过用户确认直接发私信，而每个工具的单独测试都发现不了。
"""
from __future__ import annotations

from app.agent_v3.tools import REGISTRY, Tier, specs_for_llm

# 对外可见、不可撤回 —— 必须经用户确认。这个集合只应该因为**有意的**决定而改变。
MUST_CONFIRM = {"send_message", "publish_comment"}


def test_the_confirm_set_is_exactly_what_we_decided():
    public = {name for name, spec in REGISTRY.items()
              if spec.tier is Tier.WRITE_PUBLIC}
    assert public == MUST_CONFIRM


def test_every_tool_is_fully_specified():
    for name, spec in REGISTRY.items():
        assert spec.description.strip(), f"{name} 缺描述 —— 模型看不到它就不知道该何时用"
        assert spec.args_model is not None, name
        assert callable(spec.handler), name


def test_specs_for_llm_is_openai_shaped():
    specs = specs_for_llm()
    assert len(specs) == len(REGISTRY)
    for entry in specs:
        assert entry["type"] == "function"
        assert entry["function"]["name"]
        assert entry["function"]["parameters"]["type"] == "object"


def test_expected_read_only_tools_are_registered():
    """计划里点名的只读工具都得在 —— 少一个模型就会以为自己没有这个能力。"""
    expected = {
        "search_videos", "list_latest_videos", "list_hot_videos",
        "list_following_videos", "list_by_tag", "get_video_detail",
        "search_user", "get_following", "get_followers",
        "list_comments", "list_my_liked_videos",
        "list_messages", "get_my_profile", "list_notifications",
        "like_video", "unlike_video", "follow_user", "unfollow_user",
    }
    assert expected <= set(REGISTRY)
