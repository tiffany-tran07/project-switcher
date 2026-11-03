"""Synthetic render-only fixtures: no user data, database writes, or AI calls."""

from datetime import UTC, datetime

from app.schemas import ResumeVersionOut


def acceptance_version(multipage: bool = False) -> ResumeVersionOut:
    claims = [
        "Reduced latency by ≥30% from 120 ms to ≤80 ms using C++, C#, .NET, and A/B tests.",
        "Tracked $120,000 and €10,000 budgets; preserved a −5% variance and a 10–20% range.",
        "Reviewed “quoted text”, an en–dash, an em—dash, and naïve façade labels.",
    ]
    if multipage:
        claims += [
            f"Fixture item {index:02d}: reviewed Python services, PostgreSQL queries, source logs, "
            "and deployment checks with the fictional team; retained documented scope and results."
            for index in range(1, 46)
        ]
    claims.append(
        "Built a fictional project using Python, PostgreSQL, and source-linked review notes."
    )
    bullets = []
    for index, claim in enumerate(claims):
        bullets.append(
            {
                "id": f"bullet-{index}",
                "evidence_id": f"source-{index}",
                "text": claim,
                "position": index,
                "evidence_snapshot": {
                    "claim": claim,
                    "source_note": "Synthetic test-only data; not a real career claim.",
                    "verified_at": "2026-01-01T00:00:00+00:00",
                    "metrics": [],
                    "skills": [],
                    "experience": {
                        "organization": "Fictional Systems",
                        "title": "Engineer",
                        "start_date": "2020-01-01",
                        "end_date": "2023-06-30",
                        "location": "Remote",
                    },
                    "project": {
                        "name": "Fictional Atlas",
                        "start_date": "2021-02-01",
                        "end_date": "2022-03-31",
                        "url": "https://project.example.test/review",
                    }
                    if index == len(claims) - 1
                    else None,
                },
            }
        )
    return ResumeVersionOut.model_validate(
        {
            "id": "synthetic-version",
            "resume_id": "synthetic-resume",
            "version_number": 1,
            "template": "single-column",
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "approved_at": datetime(2026, 1, 1, tzinfo=UTC),
            "bullets": bullets,
            "content": {
                "profile": {
                    "name": "Fictional Candidate",
                    "email": "fixture@example.test",
                    "phone": "555-0100",
                    "location": "Synthetic fixture — not a real resume",
                    "links": ["https://portfolio.example.test/C%2B%2B?tag=A+B#Overview"],
                },
                "sections": [
                    {
                        "heading": "Experience",
                        "evidence_ids": [bullet["evidence_id"] for bullet in bullets[:-1]],
                    },
                    {"heading": "Projects", "evidence_ids": [bullets[-1]["evidence_id"]]},
                ],
            },
        }
    )
