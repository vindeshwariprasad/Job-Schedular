"""Wraps a sync SQLAlchemy session so it can be used where async routes expect AsyncSession."""


class SyncToAsyncSessionWrapper:
    """Makes a sync session compatible with async route handlers in tests.

    API routes do ``await db.execute(...)``, ``await db.commit()``, etc.
    This wrapper provides async versions of those methods that delegate
    to the underlying sync session, so both the TestClient (async routes)
    and direct test assertions can share the same session & data.
    """

    def __init__(self, sync_session):
        self._session = sync_session

    async def execute(self, statement, *args, **kwargs):
        return self._session.execute(statement, *args, **kwargs)

    async def commit(self):
        self._session.commit()

    async def refresh(self, instance, *args, **kwargs):
        self._session.refresh(instance, *args, **kwargs)

    def add(self, instance):
        self._session.add(instance)

    def add_all(self, instances):
        self._session.add_all(instances)

    async def delete(self, instance):
        self._session.delete(instance)

    async def flush(self):
        self._session.flush()

    async def close(self):
        pass  # Lifecycle managed by the test fixture
