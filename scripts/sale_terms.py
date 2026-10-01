"""Conservative sale-term classification for Ibaity public listing descriptions.

Only descriptions that explicitly state cash or full settlement qualify for
price statistics. Financing language always takes precedence, including when
an advertised amount is a total price rather than merely the down payment.
The description itself is not stored in the published snapshot.
"""
from __future__ import annotations

import re
import unicodedata

FINANCING = re.compile(
    r"قرض|قروض|قسط|اقساط|أقساط|دفعة|دفعه|دفعات|مقدم|متبقي|متبقى|باقي|"
    r"واصل|مصرف|بنك|كفيل|تبديل|تنازل|تسديد|تمويل|شهري|"
    r"loan|installments?|mortgage|down[ -]?payment|deposit|remaining|"
    r"monthly[ -]?payment|bank[ -]?finance|guarantor|sponsor|"
    r"balance[ -]?(?:due|remaining)|credit[ -]?sale",
    re.IGNORECASE,
)
CASH = re.compile(
    r"نقد(?:ا|اً|ي|يه|ية)?|كاش|مسدد[ة]? بالكامل|خالي[ة]? من (?:الأقساط|الاقساط)|"
    r"cash|fully[ -]?paid|paid[ -]?in[ -]?full",
    re.IGNORECASE,
)


def classify_sale_terms(description: object) -> str:
    text = unicodedata.normalize("NFKC", str(description or "")).strip()
    if not text:
        return "missing"
    if FINANCING.search(text):
        return "finance"
    if CASH.search(text):
        return "cash"
    return "unspecified"
