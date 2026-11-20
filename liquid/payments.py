"""Reduce a card to a brand, last four, and gateway reference.

The full number and security code are checked, then discarded. Nothing in this
module returns them, and callers must not write them to the database or mail.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

from liquid.textutil import FormError, one_line

_DIGITS = re.compile(r"\D+")
_TOKEN = re.compile(r"^tok_[A-Za-z0-9]{16,}$")


@dataclass(frozen=True)
class PaymentReceipt:
    brand: str
    last4: str
    exp: str
    reference: str


def _digits(number: str) -> str:
    return _DIGITS.sub("", number)


def luhn_ok(number: str) -> bool:
    if not number.isdigit() or not 13 <= len(number) <= 19:
        return False
    total = 0
    parity = len(number) % 2
    for index, character in enumerate(number):
        digit = int(character)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _brand_matches(brand: str, number: str) -> bool:
    if brand == "Visa":
        return number.startswith("4")
    if brand == "Mastercard":
        two = int(number[:2])
        four = int(number[:4])
        return 51 <= two <= 55 or 2221 <= four <= 2720
    if brand == "American Express":
        return number.startswith(("34", "37")) and len(number) == 15
    if brand == "Discover":
        return number.startswith(("6011", "65")) or number[:3] in {str(n) for n in range(644, 650)}
    return False


def _expiry(value: str) -> str:
    match = re.fullmatch(r"(0[1-9]|1[0-2])\s*/\s*(\d{2}|\d{4})", value.strip())
    if not match:
        raise FormError("Enter the expiry as MM/YY.")
    month = int(match.group(1))
    year = int(match.group(2))
    if year < 100:
        year += 2000
    from datetime import date

    today = date.today()
    if (year, month) < (today.year, today.month) or year > today.year + 15:
        raise FormError("That card is outside the accepted expiry window.")
    return f"{month:02d}/{year}"


def accept_payment(brand: str, number: str, expiry: str, security_code: str) -> PaymentReceipt:
    """Validate a payment and return only what is safe to store."""

    brand = one_line(brand, 30)
    expiry_label = _expiry(expiry)
    code = _digits(security_code)
    raw = one_line(number, 40).replace(" ", "").replace("-", "")
    if _TOKEN.fullmatch(raw):
        if not re.fullmatch(r"\d{3,4}", code):
            raise FormError("The security code is invalid.")
        return PaymentReceipt(brand=brand or "Card", last4="····", exp=expiry_label, reference=raw)

    pan = _digits(raw)
    if not luhn_ok(pan):
        raise FormError("The card number could not be verified.")
    if not _brand_matches(brand, pan):
        raise FormError("The card number does not match the selected brand.")
    if brand == "American Express":
        if not re.fullmatch(r"\d{4}", code):
            raise FormError("The security code is invalid.")
    elif not re.fullmatch(r"\d{3}", code):
        raise FormError("The security code is invalid.")
    reference = "pay_" + secrets.token_hex(12)
    return PaymentReceipt(brand=brand, last4=pan[-4:], exp=expiry_label, reference=reference)
