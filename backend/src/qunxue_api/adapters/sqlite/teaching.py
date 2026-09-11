"""Two classroom records; mutations use SQLite compare-and-swap versions."""

from copy import deepcopy

from sqlalchemy import JSON, Integer, String, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base
from qunxue_api.modules.teaching_assistant import TeachingError


class TeachingActivityRow(Base):
    __tablename__ = "teaching_activities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[str] = mapped_column(String(36), index=True)
    owner_user_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class CourseTeachingSettingsRow(Base):
    __tablename__ = "course_teaching_settings"
    course_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class SqliteTeachingRepository:
    def __init__(self, session):
        self.session = session

    def get(self, activity_id):
        row = self.session.get(TeachingActivityRow, str(activity_id))
        return deepcopy(row.payload) if row else None

    def list(self, course_id):
        return [
            deepcopy(row.payload)
            for row in self.session.scalars(
                select(TeachingActivityRow).where(TeachingActivityRow.course_id == str(course_id))
            )
        ]

    def add(self, activity):
        self.session.execute(
            insert(TeachingActivityRow)
            .values(
                id=activity["id"],
                course_id=activity["course_id"],
                owner_user_id=activity["owner_user_id"],
                version=1,
                payload=activity,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        self.session.commit()
        self.session.expire_all()

    def save(self, activity, version):
        count = self.session.execute(
            update(TeachingActivityRow)
            .where(TeachingActivityRow.id == activity["id"], TeachingActivityRow.version == version)
            .values(version=activity["version"], payload=activity),
            execution_options={"synchronize_session": False},
        ).rowcount
        if count != 1:
            self.session.rollback()
            raise TeachingError("记录已更新，请刷新后重试。", 409)
        self.session.commit()
        self.session.expire_all()

    def settings(self, course_id):
        row = self.session.get(CourseTeachingSettingsRow, str(course_id))
        return (
            deepcopy(row.payload)
            if row
            else {
                "course_id": str(course_id),
                "objectives": "",
                "rubric": [],
                "version": 0,
                "receipts": {},
            }
        )

    def save_settings(self, value, version):
        if version == 0:
            count = self.session.execute(
                insert(CourseTeachingSettingsRow)
                .values(course_id=value["course_id"], version=value["version"], payload=value)
                .on_conflict_do_nothing(index_elements=["course_id"])
            ).rowcount
            if count != 1:
                self.session.rollback()
                raise TeachingError("课程设置已更新，请刷新。", 409)
        else:
            count = self.session.execute(
                update(CourseTeachingSettingsRow)
                .where(
                    CourseTeachingSettingsRow.course_id == value["course_id"],
                    CourseTeachingSettingsRow.version == version,
                )
                .values(version=value["version"], payload=value),
                execution_options={"synchronize_session": False},
            ).rowcount
            if count != 1:
                raise TeachingError("课程设置已更新，请刷新。", 409)
        self.session.commit()
