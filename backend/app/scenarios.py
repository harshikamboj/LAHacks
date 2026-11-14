"""Small, explicit synthetic work queue; isolated test workers retain a single case."""

SCENARIOS = [
    ("SI-2041", "TR-2041", "Retired receiving account", "account_correction"),
    ("SI-2042", "TR-2042", "Similar receiving-account exception", "similar_exception"),
    ("SI-2043", "TR-2043", "Check an already-accepted instruction", "already_accepted"),
    ("SI-2044", "TR-2044", "Reconcile conflicting trade records", "trade_mismatch"),
]


def scope_filter(settings):
    return {"$or": [{"caseId": settings.demo_case_id}, {"demoOwner": settings.demo_case_id}]}


def scenarios(settings):
    if settings.demo_case_id != "SI-2041":
        return [
            (settings.demo_case_id, settings.demo_trade_id, "Test exception", "account_correction")
        ]
    return SCENARIOS
