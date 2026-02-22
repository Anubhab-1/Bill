"""
app/billing/invoice.py
-----------------------
Concurrency-safe invoice number generation.

Format:  YYYY-NNNN
Example: 2026-0001, 2026-0002, … 2026-9999, 2026-10000

Algorithm
─────────
1. Ensure a row exists for the current year using UPSERT-style insert.
   - PostgreSQL: INSERT ... ON CONFLICT DO NOTHING

2. Lock the row with SELECT ... FOR UPDATE.

3. Increment last_seq by 1 and write it back.

4. Return the formatted invoice number.

The lock is released when the caller's transaction commits (or rolls back).
Because the entire billing complete() route runs in one transaction,
the sequence increment and the Sale INSERT are atomic.

Why not PostgreSQL SEQUENCE?
─────────────────────────────
PostgreSQL native sequences are non-transactional by design (they never
roll back, to avoid gaps). That's fine for most use cases, but it means
a rolled-back sale would still consume a sequence number, leaving gaps
in the invoice series — which can be a compliance issue for Indian GST
invoicing. The table approach only advances when the sale actually commits.
"""
from datetime import datetime
from sqlalchemy import text


def generate_invoice_number(db_session) -> str:
    """
    Generate the next invoice number for the current year.

    MUST be called inside an open SQLAlchemy transaction.
    The FOR UPDATE lock is held until the caller commits.

    Args:
        db_session: the active SQLAlchemy session (db.session)

    Returns:
        str — e.g. "2026-0042"
    """
    from app.billing.models import InvoiceSequence

    year = datetime.now().year
    # Ensure the sequence row exists before locking.
    db_session.execute(text("""
        INSERT INTO invoice_sequences (year, last_seq)
        VALUES (:year, 0)
        ON CONFLICT (year) DO NOTHING
    """), {'year': year})

    # ── Lock the sequence row for this year ───────────────────────
    # with_for_update() → SELECT … FOR UPDATE
    # Concurrent transactions block here until we commit.
    seq_row = (
        db_session.query(InvoiceSequence)
        .filter(InvoiceSequence.year == year)
        .with_for_update()          # ← the key: row-level exclusive lock
        .first()
    )

    if seq_row is None:
        raise RuntimeError(f'Failed to load invoice sequence row for year {year}.')

    # ── Increment and persist ─────────────────────────────────────
    seq_row.last_seq += 1
    db_session.flush()              # write new value; lock held until outer commit

    # Zero-pad to 4 digits; grows naturally beyond 4 for high-volume years
    return f"{year}-{seq_row.last_seq:04d}"
