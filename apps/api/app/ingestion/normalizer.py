COUNTRY_CURRENCY = {
    "KE": "KES",
    "UG": "UGX",
    "TZ": "TZS",
    "RW": "RWF",
    "NG": "NGN",
    "GH": "GHS",
    "ZA": "ZAR",
    "ZM": "ZMW",
    "ET": "ETB",
}


def normalize_fleet_records(records: list[dict]) -> list[dict]:
    normalized = []
    for record in records:
        item = dict(record)
        item["country_code"] = item["country_code"].strip().upper()
        item["currency"] = item["currency"].strip().upper()

        expected_currency = COUNTRY_CURRENCY.get(item["country_code"])
        item["currency_warning"] = (
            None
            if expected_currency is None or expected_currency == item["currency"]
            else f"Currency {item['currency']} differs from the configured country default {expected_currency}"
        )
        normalized.append(item)

    return normalized
