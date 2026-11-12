"""Offline mandate parse used when Gemini is unreachable. It feeds the Guardian, so a wrong limit weakens it."""

from aloud import mandate


def test_port_in_url_is_not_the_amount_limit():
    m = mandate.fallback("Pay my rent to jane@rent.example, at most 1200 dollars, on http://localhost:8765")
    assert m["maxAmount"] == 1200
    assert m["allowedRecipients"] == ["jane@rent.example"]
    assert m["allowedSites"] == ["localhost"]


def test_page_file_is_not_a_site():
    m = mandate.fallback("Buy the Aurora headphones on http://localhost:8765/shop.html, at most 90 dollars")
    assert m["maxAmount"] == 90
    assert m["allowedSites"] == ["localhost"]


def test_bare_domain_and_decimal_comma_amount():
    m = mandate.fallback("pay 1.200,50 EUR to jane@rent.example on quickpay.example")
    assert m["maxAmount"] == 1200.5
    assert m["allowedSites"] == ["quickpay.example"]


def test_host_and_port_without_scheme():
    m = mandate.fallback("Pay jane@rent.example at most 1200 dollars on localhost:8765")
    assert m["maxAmount"] == 1200
    assert m["allowedSites"] == ["localhost"]
