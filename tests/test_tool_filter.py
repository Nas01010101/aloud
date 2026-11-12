from types import SimpleNamespace

from aloud.agent import _tool_for_agent


def _t(name):
    return SimpleNamespace(name=name)


def test_reader_gets_no_acting_tools():
    ctx = SimpleNamespace(agent_name="reader")
    assert _tool_for_agent(_t("take_snapshot"), ctx)
    assert not _tool_for_agent(_t("click"), ctx)
    assert not _tool_for_agent(_t("navigate_page"), ctx)


def test_navigator_can_act():
    ctx = SimpleNamespace(agent_name="navigator")
    assert _tool_for_agent(_t("click"), ctx)
    assert not _tool_for_agent(_t("evaluate_script"), ctx)


def test_unknown_caller_gets_read_only():
    assert not _tool_for_agent(_t("click"), None)
    assert not _tool_for_agent(_t("fill"), SimpleNamespace(agent_name="orchestrator"))


def test_shared_toolset_filters_per_agent_not_per_turn():
    from aloud.agent import _browser
    assert _browser._use_invocation_cache is False
