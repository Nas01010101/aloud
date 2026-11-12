from pathlib import Path

import pytest

from aloud import quick

FIX = Path(__file__).parent / "fixtures"
BANK = quick.parse((FIX / "demo_snapshot.txt").read_text())
SHOP = quick.parse((FIX / "shop_snapshot.txt").read_text())


@pytest.mark.parametrize("text, cmd", [
    ("what are the headings", "headings"),
    ("list the links", "links"),
    ("which buttons are there", "buttons"),
    ("read the form", "form"),
    ("where am I", "where"),
    ("quels sont les titres", "headings"),
    ("lis le formulaire", "form"),
    ("show landmarks", "landmarks"),
])
def test_command_matches_screen_reader_phrases(text, cmd):
    assert quick.command(text) == cmd


@pytest.mark.parametrize("text", [
    "fill the form with my address",
    "click the pay button",
    "pay my rent to jane@rent.example, at most 1200 dollars",
    "what is this page about",
])
def test_tasks_and_open_questions_go_to_the_agent(text):
    assert quick.command(text) is None


def test_headings_in_reading_order_with_levels():
    assert quick.answer("headings", SHOP) == (
        "2 headings. level 1, Checkout. level 2, Aurora wireless headphones.")


def test_form_reads_labels_roles_values_and_read_only():
    out = quick.answer("form", SHOP)
    assert out.startswith("3 fields.")
    assert "Quantity, spinbutton, contains 1" in out
    assert "Order total (CAD), textbox, read only, contains 79.00" in out


def test_buttons_and_where():
    assert quick.answer("buttons", BANK) == "2 buttons. Send with form. Send through the API (fetch)."
    assert quick.answer("where", BANK) == (
        "You are on QuickPay. Main heading: QuickPay transfer. Address: localhost:8765/index.html.")


def test_hidden_page_text_is_not_read_by_structural_commands():
    # The planted instruction is a plain text node; headings, buttons and form never include it.
    for cmd in ("headings", "buttons", "form", "links", "where"):
        assert "ignore previous instructions" not in quick.answer(cmd, BANK)


def test_selected_page_id_from_list_pages():
    listing = "## Pages\n1: QuickPay (http://127.0.0.1:8770/bank.html)\n2: Checkout (http://x/shop.html) [selected]"
    assert quick.selected_page(listing) == 2
    assert quick.selected_page("## Pages\n3: Only (http://x/)") == 3
    assert quick.selected_page("## Pages\n") is None


def test_empty_page():
    assert quick.answer("links", []) == "0 links."
    assert quick.answer("form", []) == "No form fields on this page."
