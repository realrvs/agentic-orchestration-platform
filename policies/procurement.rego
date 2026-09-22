package procurement

import rego.v1

default decision := "deny"

decision := "allow" if {
    allow_conditions_met
}

decision := "deny" if {
    count(deny_reasons) > 0
}

decision := "escalate" if {
    count(deny_reasons) == 0
    not allow_conditions_met
}

deny_reasons contains msg if {
    input.amount > data.limits.max_amount
    msg := sprintf("amount %.0f exceeds max_amount %d", [input.amount, data.limits.max_amount])
}

deny_reasons contains "compliance_ok is false" if {
    input.compliance_ok == false
}

escalate_reasons contains "nomenclature_ok is false" if {
    input.nomenclature_ok == false
}

escalate_reasons contains msg if {
    input.confidence < data.limits.min_confidence
    msg := sprintf("confidence %.2f < %.2f", [input.confidence, data.limits.min_confidence])
}

escalate_reasons contains msg if {
    not input.region in data.regions.allow
    msg := sprintf("region %q not in allow-list", [input.region])
}

allow_conditions_met if {
    input.amount <= data.limits.max_amount
    input.compliance_ok == true
    input.nomenclature_ok == true
    input.confidence >= data.limits.min_confidence
    input.region in data.regions.allow
}

result := {
    "decision": decision,
    "deny_reasons": deny_reasons,
    "escalate_reasons": escalate_reasons,
    "policy_version": data.meta.version,
}
