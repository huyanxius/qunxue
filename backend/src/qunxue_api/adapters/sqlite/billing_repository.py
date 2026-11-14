from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import case, func, select, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.billing_model import (
    CreditAccountRow,
    CreditLedgerRow,
    CreditRedemptionCodeRow,
)
from qunxue_api.modules.billing import (
    WELCOME_GRANT,
    CreditCodeBatchConflict,
    CreditCodeSpec,
    CreditCodeUnavailable,
    CreditEntry,
    CreditRedemption,
    CreditsDepleted,
    CreditSummary,
)

_RESERVATION_LEASE = timedelta(minutes=10)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqliteCreditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_welcome_grant(
        self,
        *,
        user_id: UUID,
        points: int,
        now: datetime,
    ) -> CreditSummary:
        existing = self.get_summary(user_id=user_id, offset=0, limit=50)
        if existing is not None:
            return existing
        self._session.execute(
            sqlite_insert(CreditAccountRow)
            .values(
                user_id=str(user_id),
                balance=points,
                active_run_id=None,
                active_run_expires_at=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        self._session.execute(
            sqlite_insert(CreditLedgerRow)
            .values(
                entry_id=str(user_id),
                user_id=str(user_id),
                run_id=None,
                kind="signup_grant",
                points=points,
                balance_after=points,
                input_tokens=0,
                output_tokens=0,
                model=None,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=["entry_id"])
        )
        self._session.flush()
        summary = self.get_summary(user_id=user_id, offset=0, limit=50)
        if summary is None:
            raise RuntimeError("welcome credit grant was not persisted")
        return summary

    def get_summary(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int = 0,
    ) -> CreditSummary | None:
        account = self._session.get(CreditAccountRow, str(user_id))
        if account is None:
            return None
        total_entries = (
            self._session.scalar(
                select(func.count())
                .select_from(CreditLedgerRow)
                .where(
                    CreditLedgerRow.user_id == str(user_id),
                    CreditLedgerRow.kind == "usage",
                )
            )
            or 0
        )
        page_limit = max(1, min(limit, 100))
        rows = self._session.scalars(
            select(CreditLedgerRow)
            .where(
                CreditLedgerRow.user_id == str(user_id),
                CreditLedgerRow.kind == "usage",
            )
            .order_by(
                CreditLedgerRow.created_at.desc(),
                case((CreditLedgerRow.kind == "usage", 1), else_=0).desc(),
                CreditLedgerRow.entry_id.desc(),
            )
            .offset(max(0, offset))
            .limit(page_limit)
        ).all()
        frozen = self._frozen_points(user_id)
        grants = self._session.scalars(
            select(CreditLedgerRow).where(
                CreditLedgerRow.user_id == str(user_id), CreditLedgerRow.kind != "usage"
            )
        ).all()
        welcome_only = (
            len(grants) == 1 and grants[0].kind == "signup_grant"
            and 0 <= account.balance <= grants[0].points
        )
        # Historic redemption resets and subscriptions do not establish paid
        # bucket attribution. Only an unmixed welcome balance is provable here.
        buckets = ({
            "bucket_id": grants[0].entry_id, "kind": "welcome",
            "available_points": max(0, account.balance - frozen),
            "limit_points": grants[0].points, "expires_at": None,
        },) if welcome_only else ()
        return CreditSummary(
            balance=account.balance,
            frozen_points=frozen,
            available_balance=max(0, account.balance - frozen),
            total_granted_points=grants[0].points if welcome_only else None,
            active_usage_buckets=buckets,
            quota_status="known" if welcome_only else "unavailable",
            entries=tuple(self._entry(row) for row in rows),
            total_entries=total_entries,
            next_cursor=(str(offset + page_limit) if offset + page_limit < total_entries else None),
        )

    def create_redemption_codes(self, *, codes: tuple[CreditCodeSpec, ...]) -> None:
        if not codes:
            return
        first = codes[0]
        values = [
            {
                "code_id": str(code.code_id),
                "code_hash": code.code_hash,
                "batch_id": code.batch_id,
                "code_index": code.code_index,
                "created_by_user_id": str(code.created_by_user_id),
                "created_at": code.created_at,
                "expires_at": code.expires_at,
                "redeemed_by_user_id": None,
                "redeemed_at": None,
            }
            for code in codes
        ]
        self._session.execute(
            sqlite_insert(CreditRedemptionCodeRow).values(values).on_conflict_do_nothing()
        )
        self._session.flush()
        stored = self._session.scalars(
            select(CreditRedemptionCodeRow)
            .where(
                CreditRedemptionCodeRow.created_by_user_id == str(first.created_by_user_id),
                CreditRedemptionCodeRow.batch_id == first.batch_id,
            )
            .order_by(CreditRedemptionCodeRow.code_index)
        ).all()
        if len(stored) != len(codes) or any(
            row.code_index != code.code_index
            or row.code_hash != code.code_hash
            or _as_utc(row.expires_at) != _as_utc(code.expires_at)
            for row, code in zip(stored, codes, strict=True)
        ):
            raise CreditCodeBatchConflict

    def redeem_code(
        self,
        *,
        user_id: UUID,
        code_hash: str,
        now: datetime,
    ) -> CreditRedemption:
        # A no-op account UPDATE acquires SQLite's writer lock before reading
        # frozen funds or claiming the code. DurableBilling reserves with BEGIN
        # IMMEDIATE, so a new hold cannot interleave with this balance reset.
        # The caller's existing transaction owns the lock through commit/rollback.
        self._session.execute(
            update(CreditAccountRow)
            .where(CreditAccountRow.user_id == str(user_id))
            .values(balance=CreditAccountRow.balance)
            .execution_options(synchronize_session=False)
        )
        code = self._session.scalar(
            select(CreditRedemptionCodeRow).where(CreditRedemptionCodeRow.code_hash == code_hash)
        )
        if code is None or _as_utc(code.expires_at) < _as_utc(now):
            raise CreditCodeUnavailable
        if code.redeemed_by_user_id is not None:
            if code.redeemed_by_user_id != str(user_id):
                raise CreditCodeUnavailable
            replay = self._session.get(CreditLedgerRow, code.code_id)
            if replay is None:
                raise RuntimeError("redeemed credit code is missing its ledger entry")
            return CreditRedemption(
                redeemed_points=WELCOME_GRANT,
                balance=self._current_balance(user_id),
            )

        frozen = self._frozen_points(user_id)
        if frozen:
            from qunxue_api.modules.billing import CreditRunInProgress

            raise CreditRunInProgress
        claimed = self._session.execute(
            update(CreditRedemptionCodeRow)
            .where(
                CreditRedemptionCodeRow.code_id == code.code_id,
                CreditRedemptionCodeRow.redeemed_by_user_id.is_(None),
                CreditRedemptionCodeRow.expires_at >= now,
            )
            .values(redeemed_by_user_id=str(user_id), redeemed_at=now)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            self._session.expire(code)
            refreshed = self._session.get(CreditRedemptionCodeRow, code.code_id)
            if refreshed is not None and refreshed.redeemed_by_user_id == str(user_id):
                replay = self._session.get(CreditLedgerRow, code.code_id)
                if replay is not None:
                    return CreditRedemption(
                        redeemed_points=WELCOME_GRANT,
                        balance=self._current_balance(user_id),
                    )
            raise CreditCodeUnavailable

        balance = self._session.scalar(
            update(CreditAccountRow)
            .where(CreditAccountRow.user_id == str(user_id))
            .values(
                balance=WELCOME_GRANT,
                updated_at=now,
            )
            .returning(CreditAccountRow.balance)
        )
        if balance is None:
            raise RuntimeError("credit account is missing during redemption")
        self._session.add(
            CreditLedgerRow(
                entry_id=code.code_id,
                user_id=str(user_id),
                run_id=None,
                kind="redemption",
                points=WELCOME_GRANT,
                balance_after=balance,
                input_tokens=0,
                output_tokens=0,
                model=None,
                created_at=now,
            )
        )
        self._session.flush()
        return CreditRedemption(redeemed_points=WELCOME_GRANT, balance=balance)

    def reserve_usage(self, *, user_id: UUID, run_id: UUID, now: datetime) -> None:
        for _attempt in range(2):
            changed = self._session.execute(
                update(CreditAccountRow)
                .where(
                    CreditAccountRow.user_id == str(user_id),
                    CreditAccountRow.balance > 0,
                )
                .values(
                    active_run_id=str(run_id),
                    active_run_expires_at=now + _RESERVATION_LEASE,
                    updated_at=now,
                )
            )
            if changed.rowcount == 1:
                self._session.flush()
                return
            account = self._session.get(
                CreditAccountRow,
                str(user_id),
                populate_existing=True,
            )
            if account is None:
                self.ensure_welcome_grant(
                    user_id=user_id,
                    points=WELCOME_GRANT,
                    now=now,
                )
                continue
            if account.balance <= 0:
                raise CreditsDepleted
            if account.active_run_id == str(run_id):
                return
            # A new foreground turn owns the account lease. The displaced run
            # cannot charge because charge_usage still requires this exact ID.
            continue
        raise RuntimeError("credit reservation could not be created")

    def release_usage(self, *, user_id: UUID, run_id: UUID, now: datetime) -> None:
        self._session.execute(
            update(CreditAccountRow)
            .where(
                CreditAccountRow.user_id == str(user_id),
                CreditAccountRow.active_run_id == str(run_id),
            )
            .values(
                active_run_id=None,
                active_run_expires_at=None,
                updated_at=now,
            )
        )
        self._session.flush()

    def charge_usage(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        points: int,
        input_tokens: int,
        output_tokens: int,
        model: str,
        now: datetime,
    ) -> CreditEntry:
        for _attempt in range(2):
            replay = self._session.scalar(
                select(CreditLedgerRow).where(CreditLedgerRow.run_id == str(run_id))
            )
            if replay is not None:
                return self._entry(replay)
            account = self._session.get(CreditAccountRow, str(user_id), populate_existing=True)
            if account is None:
                raise RuntimeError("credit account is missing")
            if account.active_run_id != str(run_id):
                raise RuntimeError("credit usage was not reserved for this run")
            previous_balance = account.balance
            charged_points = min(points, previous_balance)
            balance_after = previous_balance - charged_points
            changed = self._session.execute(
                update(CreditAccountRow)
                .where(
                    CreditAccountRow.user_id == str(user_id),
                    CreditAccountRow.balance == previous_balance,
                    CreditAccountRow.active_run_id == str(run_id),
                )
                .values(
                    balance=balance_after,
                    active_run_id=None,
                    active_run_expires_at=None,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                self._session.expire(account)
                continue
            row = CreditLedgerRow(
                entry_id=str(uuid4()),
                user_id=str(user_id),
                run_id=str(run_id),
                kind="usage",
                points=-charged_points,
                balance_after=balance_after,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model[:128],
                created_at=now,
            )
            self._session.add(row)
            self._session.flush()
            return self._entry(row)
        raise RuntimeError("credit balance changed concurrently")

    def _frozen_points(self, user_id: UUID) -> int:
        return self._session.scalar(
            text(
                "SELECT coalesce(sum(hold_points),0) "
                "FROM billing_operations WHERE user_id=:user AND status='active'"
            ),
            {"user": str(user_id)},
        )

    def _current_balance(self, user_id: UUID) -> int:
        account = self._session.get(
            CreditAccountRow,
            str(user_id),
            populate_existing=True,
        )
        if account is None:
            raise RuntimeError("credit account is missing during redemption replay")
        return account.balance

    @staticmethod
    def _entry(row: CreditLedgerRow) -> CreditEntry:
        return CreditEntry(
            entry_id=UUID(row.entry_id),
            kind=row.kind,  # type: ignore[arg-type]
            points=row.points,
            balance_after=row.balance_after,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            model=row.model,
            created_at=_as_utc(row.created_at),
        )
