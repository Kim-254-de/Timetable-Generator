"""a unit is one whole class or split into groups, never both: drop leftover whole-class groups

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19 21:00:00.000000

Before this, naming a group (GR A, GR B, ...) left the unit's whole-class
group in place, so the unit was timetabled three times and the Allocator
listed it as a class of its own. The whole-class group of every unit that
also has named groups is removed, with its classes in saved timetables.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Children first: SQLite does not enforce ON DELETE CASCADE.
    op.execute(
        "DELETE FROM draft_sessions WHERE group_id IN ("
        "SELECT w.id FROM groups AS w WHERE w.label = '' "
        "AND EXISTS (SELECT 1 FROM groups AS n WHERE n.offering_id = w.offering_id AND n.label <> ''))"
    )
    op.execute(
        "DELETE FROM group_class_rows WHERE group_id IN ("
        "SELECT w.id FROM groups AS w WHERE w.label = '' "
        "AND EXISTS (SELECT 1 FROM groups AS n WHERE n.offering_id = w.offering_id AND n.label <> ''))"
    )
    op.execute(
        "DELETE FROM groups WHERE id IN ("
        "SELECT w.id FROM groups AS w WHERE w.label = '' "
        "AND EXISTS (SELECT 1 FROM groups AS n WHERE n.offering_id = w.offering_id AND n.label <> ''))"
    )


def downgrade() -> None:
    # The removed groups were duplicates of their unit's named groups; nothing to restore.
    pass
