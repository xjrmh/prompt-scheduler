from __future__ import annotations

import re
import uuid


def make_job_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        slug = "job"
    return f"{slug[:32]}-{uuid.uuid4().hex[:8]}"
