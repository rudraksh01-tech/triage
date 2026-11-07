CATEGORIES = {
    "billing": "charges, refunds, payments, invoices, pricing, promo codes",
    "delivery": "orders, shipping, parcels, food delivery, late/missing/wrong items",
    "account": "login, password, locked or hacked account, subscription changes, cancellation",
    "technical": "app or website bugs, device faults, outages, network/signal, connectivity",
    "travel": "flights, trains, bookings, delays, cancellations, baggage, seats",
    "service": "complaint about staff, store, wait times or general experience, not a specific fault",
    "question": "how-to or information request with no problem reported",
    "other": "praise, jokes, spam, chatter, 'sent you a DM' and anything not actionable",
}

PRIORITIES = {
    "high": "money lost or stuck, locked out, safety risk, stranded traveller, service fully down",
    "medium": "a real problem that needs a reply but nothing is on fire",
    "low": "questions, feedback, praise, chatter",
}

LABELS = list(CATEGORIES)
PRIORITY_LEVELS = list(PRIORITIES)
