VALUATION_INDICATORS = [
    {
        "key": "pe",
        "label": "P/E (trailing)",
        "target": 25,
        "red_flag": 40,
        "higher_is_better": False,
    },
    {
        "key": "pe_fwd",
        "label": "P/E (forward)",
        "target": 20,
        "red_flag": 35,
        "higher_is_better": False,
    },
    {
        "key": "peg",
        "label": "PEG",
        "target": 1.5,
        "red_flag": 2.5,
        "higher_is_better": False,
    },
    {
        "key": "ev_ebitda",
        "label": "EV/EBITDA",
        "target": 15,
        "red_flag": 30,
        "higher_is_better": False,
    },
    {
        "key": "ps",
        "label": "P/S",
        "target": 5,
        "red_flag": 15,
        "higher_is_better": False,
    },
    {
        "key": "pb",
        "label": "P/B",
        "target": 5,
        "red_flag": 20,
        "higher_is_better": False,
    },
]


def valuation_rows(values):
    rows = []
    notes = []

    pe_fwd = values.get("pe_fwd")
    pe_fwd_is_valid = pe_fwd is not None and pe_fwd > 0
    roe = values.get("roe")

    for indicator in VALUATION_INDICATORS:
        key = indicator["key"]
        value = values.get(key)
        usable = value is not None and value > 0

        if key == "pb" and roe is not None and roe > 40:
            usable = False
            notes.append("P/B exclus: ROE mare")

        if key == "pe" and pe_fwd_is_valid and value is not None and value > 2 * pe_fwd:
            usable = False
            notes.append("P/E trailing exclus: profit distorsionat")

        rows.append(
            {
                "key": key,
                "label": indicator["label"],
                "value": value,
                "target": indicator["target"],
                "red_flag": indicator["red_flag"],
                "usable": usable,
                "in_red": usable and value >= indicator["red_flag"],
            }
        )

    return rows, notes


def red_count(rows):
    usable_rows = [row for row in rows if row["usable"]]
    return sum(row["in_red"] for row in usable_rows), len(usable_rows)
