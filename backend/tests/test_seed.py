"""Empty DB -> dialogs are loaded from datasets/DEV.json; a non-empty DB is left alone."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import services
from app.db import Base


def test_seed_empty_db_then_noop(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        n = services.seed_conversations(db, "DEV")
        assert n == 65
        assert services.seed_conversations(db, "DEV") == 0  # already has data
        assert services.seed_conversations(db, "NOPE") == 0
