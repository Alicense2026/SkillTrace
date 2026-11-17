"""Activity taxonomy: groups are for presentation; canonical activities are used by rules."""
TAXONOMY = {
    "ARTIFACT_TRANSFORMATION": ["Use", "Copy", "Modify", "CreateDerivative"],
    "DISTRIBUTION_PROVISION": ["Distribute", "Publish", "ProvideSource", "Sublicense"],
    "COMMERCIAL_OPERATION": ["CommercialUse", "Charge", "SellCopies", "OfferPaidAccess"],
    "COMPOSITION_INTEGRATION": ["Bundle", "Link", "Combine"],
    "NETWORK_SERVICE": ["ProvideNetworkService", "RemoteInteraction"]
}
EXTENSION_ACTIVITIES = {"TrainModel": "AI_MODEL_OPERATION"}

ALIASES = {
    "publish": "Distribute", "publication": "Distribute", "redistribute": "Distribute",
    "package": "Bundle", "package_together": "Bundle", "integrate": "Combine",
    "integration": "Combine", "commercial_use": "CommercialUse",
    "paid_access": "OfferPaidAccess", "subscription": "OfferPaidAccess",
    "charging": "Charge", "fee": "Charge", "modify": "Modify", "edit": "Modify",
    "patch": "Modify", "source_code_offer": "ProvideSource", "relicense": "Sublicense"
}
def normalize_activity(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Activity cannot be empty")
    raw = value.strip().replace("-", "_").replace(" ", "_")
    key = raw.lower()
    for name in EXTENSION_ACTIVITIES:
        if name.lower() == key:
            return name
    if key in ALIASES:
        return ALIASES[key]
    for values in TAXONOMY.values():
        for v in values:
            if v.lower() == key:
                return v
    raise ValueError(f"Unknown Activity: {value}")
def category_for(activity):
    a = normalize_activity(activity)
    if a in EXTENSION_ACTIVITIES:
        return EXTENSION_ACTIVITIES[a]
    return next(k for k, values in TAXONOMY.items() if a in values)
