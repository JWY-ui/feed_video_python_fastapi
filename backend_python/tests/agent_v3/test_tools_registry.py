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


def test_every_public_write_tool_writes_its_own_confirmation_card():
    """对外可见的写操作都要自带确认卡文案。

    确认卡是用户决定「发不发」的唯一依据，文案必须说清要发什么。兜底那版会把整个
    参数 JSON 塞进去 —— 既不友好，新增工具时也最容易漏配。这条和
    test_the_confirm_set_is_exactly_what_we_decided 是一对：新加一个 write_public
    工具，tier 和文案两处都得有人显式决定。
    """
    for name in MUST_CONFIRM:
        assert REGISTRY[name].preview is not None, f"{name} 没配确认卡文案"


def test_the_confirmation_card_shows_what_would_actually_be_sent():
    """文案里得看得见收件人和正文 —— 「将执行 send_message」等于没问。"""
    card = REGISTRY["send_message"].describe({"to_id": 42, "content": "今晚看球？"})

    assert "42" in card
    assert "今晚看球？" in card


def test_tools_without_their_own_card_fall_back_to_a_generic_one():
    """没配文案的工具（全是只读的，走不到确认）要有兜底，且兜底看得出是哪个工具。"""
    spec = REGISTRY["search_videos"]

    assert spec.preview is None
    assert "search_videos" in spec.describe({"query": "做菜"})


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
