from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session


_LINKAGE_STATS_QUERY = sa.text(
    """
    SELECT
        COUNT(*) AS total_locations,
        SUM(CASE WHEN business_location_id IS NOT NULL THEN 1 ELSE 0 END) AS linked_locations
    FROM locations
    WHERE organization_id = :organization_id
    """
)


def get_location_linkage_stats(db: Session, org_id: str) -> dict[str, object]:
    row = db.execute(_LINKAGE_STATS_QUERY, {"organization_id": org_id}).mappings().one()
    total_locations = int(row["total_locations"] or 0)
    linked_locations = int(row["linked_locations"] or 0)
    unlinked_locations = total_locations - linked_locations
    linkage_percentage = 0.0 if total_locations == 0 else round((linked_locations / total_locations) * 100, 2)

    return {
        "total_locations": total_locations,
        "linked_locations": linked_locations,
        "unlinked_locations": unlinked_locations,
        "linkage_percentage": linkage_percentage,
    }
