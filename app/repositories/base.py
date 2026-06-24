from typing import Generic, TypeVar

from sqlalchemy.orm import Session

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    def __init__(self, db: Session, model: type[ModelType]) -> None:
        self.db = db
        self.model = model

    def list_all(self, limit: int = 100) -> list[ModelType]:
        return list(self.db.query(self.model).limit(limit).all())
