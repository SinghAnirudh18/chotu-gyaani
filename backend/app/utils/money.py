"""Money is integer paise everywhere. Formatting happens only at the API edge."""


def format_inr(paise: int | None) -> str | None:
    if paise is None:
        return None
    sign = "-" if paise < 0 else ""
    paise = abs(int(paise))
    rupees, p = divmod(paise, 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{sign}₹{s}" + (f".{p:02d}" if p else "")
