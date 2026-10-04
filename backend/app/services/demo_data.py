from backend.app.services.seed_demo import seed_demo_data


def init_db() -> None:
    raise RuntimeError('Database schema is managed by Alembic. Run `alembic upgrade head` explicitly.')


__all__ = ['seed_demo_data', 'init_db']