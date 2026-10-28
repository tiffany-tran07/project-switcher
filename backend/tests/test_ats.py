from app.ats import aliases_for, contains, requirement_result
from app.models import JobRequirement, Skill, SkillAlias


def test_normalization_keeps_technology_boundaries_and_ignores_negations() -> None:
    assert contains("Built Python services.", "python service")
    assert contains("Managed responsibilities", "responsibility")
    assert contains("Built C++ services", "C++")
    assert not contains("Built C++ services", "C#")
    assert not contains("Built JavaScript services", "Java")
    assert not contains("No Kubernetes experience", "Kubernetes")
    assert not contains("Worked without Docker", "Docker")
    assert not contains("Built a data pipeline", "")


def test_ambiguous_aliases_are_not_equivalent() -> None:
    a = Skill(name="First skill", aliases=[SkillAlias(alias="shared")])
    b = Skill(name="Second skill", aliases=[SkillAlias(alias="shared")])
    assert aliases_for("shared", [a, b]) == ["shared"]
    assert aliases_for("First skill", [a, b]) == ["First skill", "shared"]


def test_unsupported_terms_in_document_are_not_claimed_as_verified() -> None:
    req = JobRequirement(id="req", text="Kubernetes")
    row = requirement_result(req, "Kubernetes is required", [("e", "Used Python", [])], [])
    assert row.status == "no_verified_evidence"
    assert row.evidence_ids == []
    row = requirement_result(
        req, "Kubernetes is required", [("e", "No Kubernetes experience", [])], []
    )
    assert row.status == "no_verified_evidence"
