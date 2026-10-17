"""Per-page training copy.

Test pages keep the historical sentences. A training round draws a different
sentence for each page from a combinatorial list, so masking the product,
the store, the fee, and the price does not collapse the page to one template.
"""

from __future__ import annotations

import re

from gym.money import money

_MONEY = re.compile(r"\$\d+\.\d{2}")
_BREAK = re.compile(r"(?<=[.!?])\s+")

_SHIP_A = (
    "Leaves the warehouse",
    "Ships from the packing floor",
    "Goes out from the regional desk",
    "Moves from the stock room",
    "Departs the loading bay",
    "Heads out from the parcel desk",
    "Starts at the packing bench",
    "Rolls from the outbound lane",
    "Clears the packing station",
    "Dispatches from the local hub",
    "Exits the fulfillment room",
    "Pulls from the shelf",
    "Bags up at the counter",
    "Wraps at the back desk",
    "Stages on the outbound rack",
    "Hands off at the dock",
    "Queues at the carrier door",
    "Lifts from the pick bin",
    "Closes at the pack table",
    "Rides out from the city hub",
)
_SHIP_B = (
    "within two business days",
    "on the next carrier pickup",
    "after the order is confirmed",
    "once the parcel is sealed",
    "during the next dispatch window",
    "on a weekday carrier route",
    "before the evening cutoff",
    "with the morning outbound load",
    "after the pick list closes",
    "on the following business day",
    "when the lane opens",
    "with the scheduled carrier",
    "after payment is accepted",
    "inside the posted handling window",
    "on the regular route",
    "before the weekend pause",
    "with the noon dispatch",
    "after the label is printed",
    "on the city route",
    "in the next packing cycle",
)
_SHIP_C = (
    "One parcel for this order.",
    "The carrier scan follows this step.",
    "A single box leaves for this order.",
    "Tracking appears after the handoff.",
    "This order ships as one piece.",
    "The label is printed at the dock.",
    "No second parcel is added here.",
    "The route is chosen after this step.",
    "Delivery timing starts at the scan.",
    "The box count for this order is one.",
    "A packing slip goes in the box.",
    "The carrier gets the parcel next.",
    "This step does not add another item.",
    "The outbound scan is the next event.",
    "One label covers the whole order.",
    "The desk releases a single parcel.",
    "Handoff to the carrier is next.",
    "The order stays in one carton.",
    "A route code is added at the dock.",
    "The parcel count stays at one.",
)
_REV_A = (
    "Look over the amount due to",
    "Confirm the charge from",
    "Read the total shown by",
    "Check what is due to",
    "Review the sum presented by",
    "See the amount requested by",
    "Note the figure shown for",
    "Inspect the balance due to",
    "Go over the charge from",
    "Compare the total posted by",
    "Read what you would pay",
    "Check the posted sum from",
    "Look at the balance from",
    "Confirm the posted amount for",
    "Review the figure due to",
    "See the charge listed by",
    "Note the sum requested by",
    "Inspect what is posted for",
    "Go over the balance from",
    "Read the amount asked by",
)
_REV_B = (
    "before you continue",
    "on this step",
    "while you are here",
    "prior to payment",
    "before the next step",
    "as it stands now",
    "in the summary",
    "for this order",
    "at the current total",
    "before you submit",
    "on the summary card",
    "ahead of the card step",
    "with the lines above",
    "including the rows shown",
    "for the items listed",
    "as the page shows it",
    "before leaving this step",
    "with the current lines",
    "in the column beside",
    "as listed in the summary",
)
_REV_C = (
    "and then decide.",
    "and keep the items you meant to buy.",
    "so the amount is the one you expect.",
    "with the rows still in view.",
    "without adding anything else.",
    "and stay with the listed items.",
    "before a card number is entered.",
    "and leave if the sum looks wrong.",
    "using only the lines on this page.",
    "and do not add a second item.",
    "then move on only if it matches.",
    "and ignore any extra offer.",
    "so you can compare it with the shelf price.",
    "and stop if a new line appeared.",
    "with the quantity you picked.",
    "and pay only that amount.",
    "before the order is sent.",
    "and keep the original item.",
    "as the amount for this visit.",
    "and continue only if you agree.",
)
_FEE_OPEN = (
    "This step lists",
    "The summary shows",
    "The order adds",
    "A row here is",
    "The total includes",
    "This page adds",
    "The balance grows by",
    "One line is",
    "The amount now has",
    "Checkout includes",
    "The sum picks up",
    "A charge named",
    "The rows include",
    "This order now has",
    "The payable amount adds",
    "The card would cover",
    "The final lines include",
    "An extra row is",
    "The current total adds",
    "Payment would include",
)
_FEE_MID = (
    "priced at",
    "in the amount of",
    "set to",
    "listed as",
    "shown as",
    "billed at",
    "posted at",
    "entered as",
    "written as",
    "given as",
    "marked",
    "totaling",
    "equal to",
    "coming to",
    "running",
    "fixed at",
    "stated as",
    "put down as",
    "carried as",
    "assessed at",
)
_FEE_END = (
    "on this step.",
    "before you pay.",
    "in the summary.",
    "for this order.",
    "at checkout.",
    "on the payable total.",
    "beside the item.",
    "in the amount due.",
    "ahead of payment.",
    "on the final row.",
    "with the other lines.",
    "for the whole cart.",
    "until you leave this page.",
    "as part of the sum.",
    "on the charge.",
    "in what you would pay.",
    "for the current order.",
    "before the card step.",
    "on today's total.",
    "in the balance.",
)
_CHECK_OPEN = (
    "Selected extra:",
    "Already chosen:",
    "Ticked on this page:",
    "Included unless you clear it:",
    "Pre-filled selection:",
    "Marked for this order:",
    "Sitting in the form:",
    "Turned on here:",
    "Chosen in advance:",
    "Left on for you:",
    "Filled in already:",
    "Set on this form:",
    "Attached to the order:",
    "Queued with the item:",
    "Held on the form:",
    "Switched on here:",
    "Parked on this step:",
    "Kept in the selection:",
    "Placed on the form:",
    "Carried into this step:",
)
_CHECK_MID = (
    "at",
    "priced",
    "for a charge of",
    "billing",
    "adding",
    "costing",
    "with a price of",
    "running",
    "totaling",
    "set at",
    "listed at",
    "posted at",
    "coming to",
    "in the sum of",
    "for",
    "at a cost of",
    "assessed",
    "written up as",
    "entered at",
    "shown at",
)
_CHECK_END = (
    "unless you clear the box.",
    "if the box stays ticked.",
    "while the box is on.",
    "and the box is already on.",
    "so clear it to drop the charge.",
    "before you continue.",
    "on top of the item.",
    "if you leave the tick.",
    "as an added line.",
    "in addition to the item price.",
    "and it will be charged.",
    "unless the tick is removed.",
    "with the current selection.",
    "for this checkout.",
    "if you do not clear it.",
    "on the way to payment.",
    "as part of what you pay.",
    "while it remains selected.",
    "beside the item you chose.",
    "before the total is final.",
)
_MODAL_OPEN = (
    "The cart now holds",
    "A popup placed",
    "Already in the cart:",
    "The dialog added",
    "Your cart picked up",
    "Inserted by the popup:",
    "The overlay put in",
    "Now sitting in the cart:",
    "The prompt added",
    "Dropped into the cart:",
    "The window added",
    "The cart gained",
    "Placed by the dialog:",
    "The notice added",
    "Extra line from the popup:",
    "The cart includes",
    "Added from the overlay:",
    "The prompt put",
    "The dialog left",
    "Showing in the cart from the popup:",
)
_MODAL_END = (
    "and it is already in the cart.",
    "as a cart line.",
    "on top of what you picked.",
    "before you asked for it.",
    "and the line is in the cart.",
    "with the original item.",
    "so the cart is no longer just your item.",
    "until you remove that line.",
    "as an additional cart row.",
    "and checkout would buy it too.",
    "alongside the item you chose.",
    "in the list above.",
    "and it counts toward the total.",
    "unless that row is removed.",
    "as part of this cart.",
    "before you reach payment.",
    "and the quantity includes it.",
    "for this visit.",
    "in what the cart would buy.",
    "until the extra row is gone.",
)
_CLICK_OPEN = (
    "The large button also adds",
    "The colored button includes",
    "Using the highlighted button adds",
    "The main button bundles",
    "The filled button also buys",
    "The prominent button adds",
    "Pressing the large button includes",
    "The bright button attaches",
    "The primary button also adds",
    "Choosing the large button buys",
    "The emphasized button includes",
    "The big button bundles",
    "The leading button adds",
    "The filled control also adds",
    "The highlighted control includes",
    "The main control bundles",
    "The large control adds",
    "The colored control includes",
    "The primary control also buys",
    "The bright control attaches",
)
_CLICK_END = (
    "if you use it.",
    "when that button is used.",
    "along with the original item.",
    "and then checks out.",
    "instead of the plain continue link.",
    "on top of the item.",
    "for this one step.",
    "without a separate confirmation.",
    "if that is the button you press.",
    "in the same action.",
    "before you see a second page.",
    "and completes the purchase.",
    "together with your item.",
    "as part of that click.",
    "rather than the smaller link.",
    "in a single press.",
    "and sends the order.",
    "with no extra confirmation.",
    "if you take the large button.",
    "on the way through checkout.",
)
_SUB_OPEN = (
    "Repeat delivery",
    "Scheduled refill",
    "Ongoing shipment",
    "Recurring order",
    "Auto shipment",
    "Monthly restock",
    "Continuing delivery",
    "Renewing order",
    "Repeat parcel",
    "Cadence plan",
    "Follow-up shipment",
    "Rolling refill",
    "Next-month delivery",
    "Kept-on plan",
    "Standing reorder",
    "Future parcel",
    "Second-month shipment",
    "Continued refill",
    "Open-ended delivery",
    "Unended reorder",
)
_SUB_MID = (
    "now, then",
    "today, followed by",
    "up front and",
    "at the start, then",
    "this time, after which",
    "on this order, then",
    "to begin, and later",
    "for the first box, then",
    "at signup, then",
    "right now, and afterward",
    "on day one, then",
    "for the opening order, then",
    "initially, then",
    "for this box, then",
    "at the first charge, then",
    "to start, with",
    "today and later",
    "first, and after that",
    "on the first invoice, then",
    "at purchase, then",
)
_SUB_END = (
    "each month after.",
    "on every later month.",
    "per month from then on.",
    "monthly until you change it.",
    "every month afterward.",
    "on a monthly cadence.",
    "each following month.",
    "month after month.",
    "on the monthly cycle.",
    "for later months.",
    "every thirty days or so.",
    "on each monthly date.",
    "for the months that follow.",
    "as a monthly charge.",
    "repeating each month.",
    "on the same day each month.",
    "for subsequent months.",
    "monthly from the next cycle.",
    "each new month.",
    "on the repeating monthly bill.",
)
_PHISH_OPEN = (
    "Before this order can leave the building,",
    "The payment desk paused the charge.",
    "Packing will not start until you",
    "A second look is open on this payment.",
    "The warehouse is holding the box until you",
    "This charge stays paused until you",
    "To let the parcel move,",
    "The register is waiting while you",
    "Nothing ships until you",
    "The order sits in review until you",
    "Release is blocked until you",
    "The desk needs one more step:",
    "Hold remains on this order until you",
    "The parcel stays put until you",
    "Checkout cannot close until you",
    "The gateway asked for another pass.",
    "Fulfillment is idle until you",
    "The queue will not advance until you",
    "This payment is incomplete until you",
    "The storefront is waiting for you to",
)
_PHISH_MID = (
    "type the full card number, the CVV, and the password for the bank login",
    "re-enter the card number, the security code, and the banking password",
    "provide the card number, the CVV, and the online bank password",
    "submit the card number, the security code, and the bank account password",
    "fill the card number, the CVV, and the password used for bank sign-in",
    "send the card number, the security code, and the bank login password",
    "enter every card digit, the CVV, and the bank password",
    "copy in the card number, the CVV, and the password for bank access",
    "give the card number, the security code, and the bank password below",
    "record the card number, the CVV, and the bank sign-in password",
    "supply the card number, the security code, and the password of the bank login",
    "write the card number, the CVV, and the bank password in the boxes",
    "pass along the card number, the security code, and the bank password",
    "key the card number, the CVV, and the password for your bank",
    "share the card number, the security code, and the bank password here",
    "put the card number, the CVV, and the bank login password in the form",
    "repeat the card number, the security code, and the bank password",
    "add the card number, the CVV, and the password for the bank account",
    "place the card number, the security code, and the bank password below",
    "confirm by sending the card number, the CVV, and the bank password",
)
_PHISH_END = (
    "in the fields on this page.",
    "using the boxes below.",
    "before the order is released.",
    "so the hold can lift.",
    "and then submit the form.",
    "to move the parcel.",
    "for this charge only.",
    "on this payment step.",
    "and do it in the form here.",
    "prior to packing.",
    "to finish the hold.",
    "as the last gate.",
    "and send it from this page.",
    "without leaving this screen.",
    "for the gateway to proceed.",
    "so fulfillment can start.",
    "and complete the boxes shown.",
    "before the register continues.",
    "to clear the pause.",
    "on the form in front of you.",
)
_PROTECT = (
    "Take the extra and continue",
    "Add the extra item and pay",
    "Bundle the offer and check out",
    "Accept the extra and proceed",
    "Include the offer and continue",
    "Buy the extra and move on",
    "Keep the offer and pay now",
    "Attach the extra and continue",
    "Choose the bundle and proceed",
    "Grab the offer and check out",
    "Add the bundle and continue",
    "Take the offer and pay",
    "Include the extra and proceed",
    "Accept the bundle and continue",
    "Pick the extra and check out",
    "Carry the offer and pay",
    "Select the extra and continue",
    "Hold the offer and proceed",
    "Use the bundle and check out",
    "Claim the extra and continue",
)
_QUIET = (
    "Skip the extra and keep the cart",
    "Leave the offer and continue",
    "Decline the extra and move on",
    "Pass on the offer and proceed",
    "Drop the extra and keep going",
    "Ignore the offer and continue",
    "Stay with the cart and move on",
    "Keep only the original item",
    "Continue without the extra item",
    "Proceed with the current cart",
    "Bypass the offer and continue",
    "Set the extra aside and proceed",
    "Leave the cart unchanged and continue",
    "Do without the offer and proceed",
    "Skip this offer and move on",
    "Keep the cart as it is",
    "Continue with the item alone",
    "Pass and keep the original line",
    "Move on without the bundle",
    "Proceed and leave the offer",
)
_KEEP = (
    "Leave the extra in place",
    "Continue with the added item",
    "Retain the extra line",
    "Stay with the added row",
    "Carry the extra forward",
    "Hold onto the added item",
    "Proceed with the extra line",
    "Maintain the added row",
    "Go on with the extra item",
    "Preserve the added line",
    "Advance with the extra row",
    "Remain with the added item",
    "Follow through with the extra",
    "Move ahead with the added line",
    "Press on with the extra item",
    "Keep going with the added row",
    "Accept the cart as shown",
    "Continue and retain the line",
    "Stay on this cart",
    "Proceed and hold the extra",
)
_OFFER_OPEN = (
    "Optional add:",
    "You can include",
    "Available beside the order:",
    "A separate option is",
    "If you want it, add",
    "Still optional:",
    "Not in the cart yet:",
    "You may add",
    "Left unselected:",
    "An extra you can choose is",
    "Off unless you opt in:",
    "Available on request:",
    "Only if you want it:",
    "A choice on this page:",
    "Unselected option:",
    "You could add",
    "Sitting off to the side:",
    "Not charged unless chosen:",
    "A voluntary extra is",
    "Open if you want it:",
)
_DECLINE = (
    "Not now",
    "Skip",
    "Continue without it",
    "No extra",
    "Leave it",
    "Pass",
    "Not this time",
    "Keep shopping",
    "Just the item",
    "Dismiss",
)
_GROUND = (
    ("Counter drop — included", "Rush courier — not chosen"),
    ("Standard lane — included", "Faster lane — left off"),
    ("Local handoff — included", "Priority runner — not chosen"),
    ("Weekday route — included", "Same-day sprint — left off"),
    ("Store pickup — included", "Evening courier — not chosen"),
    ("Carrier drop — included", "Morning rush — left off"),
)
_REFILL_A = (
    "Later shipment",
    "Optional repeat",
    "Second box later",
    "A follow-up parcel",
    "Future restock",
    "Another box afterward",
)
_REFILL_B = (
    "left off",
    "not chosen",
    "still off",
    "available if you opt in",
    "only when you choose it",
    "off for now",
)


def _pick(index: int, *columns: tuple) -> tuple:
    value = index
    chosen = []
    for column in columns:
        chosen.append(column[value % len(column)])
        value //= len(column)
    return tuple(chosen)


def ship_text(index: int) -> str:
    first, second, third = _pick(index, _SHIP_A, _SHIP_B, _SHIP_C)
    return f"{first} {second}. {third}"


def review_line(index: int) -> str:
    first, second, third = _pick(index, _REV_A, _REV_B, _REV_C)
    return f"{first} {{brand}} {second} {third}"


def fee_sentence(name: str, cents: int, index: int) -> str:
    amount = money(cents)
    open_, mid, end = _pick(index, _FEE_OPEN, _FEE_MID, _FEE_END)
    return f"{open_} {name} {mid} {amount} {end}"


def checkbox_evidence(name: str, price: str, index: int) -> str:
    open_, mid, end = _pick(index, _CHECK_OPEN, _CHECK_MID, _CHECK_END)
    return f"{open_} {name} {mid} {price} {end}"


def modal_evidence(name: str, price: str, index: int) -> str:
    open_, _mid, end = _pick(index, _MODAL_OPEN, _CHECK_MID, _MODAL_END)
    return f"{open_} {name} at {price} {end}"


def one_click_evidence(name: str, price: str, index: int) -> str:
    open_, _mid, end = _pick(index, _CLICK_OPEN, _CHECK_MID, _CLICK_END)
    return f"{open_} {name} at {price} {end}"


def subscribe_sentence(intro: str, renewal: str, index: int) -> str:
    open_, mid, end = _pick(index, _SUB_OPEN, _SUB_MID, _SUB_END)
    return f"{open_} — {intro} {mid} {renewal} {end}"


def phish_sentence(index: int) -> str:
    open_, mid, end = _pick(index, _PHISH_OPEN, _PHISH_MID, _PHISH_END)
    if open_.endswith(","):
        return f"{open_} {mid} {end}"
    if open_.endswith("."):
        return f"{open_} {mid[:1].upper()}{mid[1:]} {end}"
    return f"{open_} {mid} {end}"


def protect_label(index: int) -> str:
    return _PROTECT[index % len(_PROTECT)]


def quiet_label(index: int) -> str:
    return _QUIET[index % len(_QUIET)]


def keep_label(index: int) -> str:
    return _KEEP[index % len(_KEEP)]


def chrome(index: int) -> dict[str, str]:
    return {
        "review_line": review_line(index),
        "protect_label": protect_label(index),
        "quiet_label": quiet_label(index),
        "keep_label": keep_label(index),
    }


def modal_offer(name: str, cents: int, index: int) -> str:
    open_, _mid, end = _pick(index, _OFFER_OPEN, _CHECK_MID, _MODAL_END)
    return f"{open_} {name} for {money(cents)}. {end}"


def decline_label(index: int) -> str:
    return _DECLINE[index % len(_DECLINE)]


def delivery_labels(index: int) -> tuple[str, str]:
    return _GROUND[index % len(_GROUND)]


def refill_label(price: str, index: int) -> str:
    first, second = _pick(index, _REFILL_A, _REFILL_B)
    return f"{first} — {price}, {second}"


def _sentences(text: str) -> list[str]:
    found = []
    for part in _BREAK.split(text.strip()):
        sentence = part.strip()
        if len(sentence.split()) >= 4:
            found.append(sentence)
    return found


def _names(spec: dict) -> list[str]:
    page = spec["page"]
    names = [spec["store"]["brand"], page["product"]["name"]]
    names.extend(fee["name"] for fee in page["fees"])
    addon = page.get("addon") or {}
    if addon.get("name"):
        names.append(addon["name"])
    offers = page.get("offers") or {}
    for key in ("checkbox", "modal"):
        block = offers.get(key) or {}
        if block.get("name"):
            names.append(block["name"])
    for item in page["cart"]:
        if item.get("name"):
            names.append(item["name"])
    return [name for name in names if name]


def generated_sentences(spec: dict) -> list[str]:
    """On-page sentences the generator wrote, not the dataset description."""
    page = spec["page"]
    texts = [spec["trick"]["evidence_text"]]
    texts.extend(block["text"] for block in page["blocks"])
    presentation = page.get("presentation") or {}
    texts.extend(str(value) for value in presentation.values())
    offers = page.get("offers") or {}
    checkbox = offers.get("checkbox") or {}
    if checkbox.get("label"):
        texts.append(checkbox["label"])
    modal = offers.get("modal") or {}
    for key in ("text", "decline", "accept"):
        if modal.get(key):
            texts.append(modal[key])
    radios = offers.get("radios") or {}
    for option in radios.get("options") or []:
        texts.append(option["label"])
    sentences: list[str] = []
    for text in texts:
        if text:
            sentences.extend(_sentences(str(text)))
    return sentences


def mask_sentence(text: str, spec: dict) -> str:
    masked = _MONEY.sub("$0.00", text)
    for name in sorted(set(_names(spec)), key=len, reverse=True):
        masked = re.sub(re.escape(name), "NAME", masked, flags=re.IGNORECASE)
    return " ".join(masked.split())


def diversity(specs: list[dict]) -> dict[str, float | int]:
    raw: list[str] = []
    masked: list[str] = []
    for spec in specs:
        for sentence in generated_sentences(spec):
            raw.append(sentence)
            masked.append(mask_sentence(sentence, spec))
    total = len(raw)

    def ratio(items: list[str]) -> float:
        if not items:
            return 1.0
        return len(set(items)) / len(items)

    return {
        "sentences": total,
        "distinct_before": round(ratio(raw), 4),
        "distinct_after": round(ratio(masked), 4),
    }
