"""A finished analysis must never be lost to a transient database problem.

save_analysis() returns False rather than raising, on purpose: a storage fault
must not fail an analysis that already succeeded. But _persist_analysis ignored
that return value, so the ONLY signal that a write had failed was discarded — a
20-minute run that completed while the database was briefly unreachable was gone
permanently, with nothing but a log line.

These tests pin the recovery: a failed write is queued and retried until it
lands.
"""
import pytest

import app as app_module


@pytest.fixture(autouse=True)
def clean_queue():
    app_module._pending_persist.clear()
    yield
    app_module._pending_persist.clear()


SNAPSHOT = {'pdf_filename': 'spec.pdf', 'mode': 'bid_spec',
            'result': {'sections': []}, 'statistics': {'questions_answered': 7}}


class TestAFailedWriteIsNeverLost:
    def test_a_failed_save_is_queued(self, monkeypatch):
        monkeypatch.setattr(app_module.persistence_store, 'save_analysis',
                            lambda *a, **k: False)
        saved = app_module._persist_analysis('sess_x', SNAPSHOT, 'alice', 'completed')
        assert saved is False
        assert 'sess_x' in app_module._pending_persist, \
            'a finished analysis was dropped instead of queued'

    def test_a_raising_save_is_also_queued(self, monkeypatch):
        """Failure-safe means both shapes of failure — returned False and a
        thrown exception — end up in the same place."""
        def boom(*a, **k):
            raise RuntimeError('connection reset')
        monkeypatch.setattr(app_module.persistence_store, 'save_analysis', boom)
        assert app_module._persist_analysis('sess_y', SNAPSHOT, 'bob', 'completed') is False
        assert 'sess_y' in app_module._pending_persist

    def test_a_successful_save_queues_nothing(self, monkeypatch):
        monkeypatch.setattr(app_module.persistence_store, 'save_analysis',
                            lambda *a, **k: True)
        assert app_module._persist_analysis('sess_ok', SNAPSHOT, 'alice', 'completed') is True
        assert app_module._pending_persist == {}

    def test_the_retry_stores_it_once_the_database_returns(self, monkeypatch):
        """The whole point: the analysis lands without the user redoing it."""
        monkeypatch.setattr(app_module.persistence_store, 'save_analysis',
                            lambda *a, **k: False)
        app_module._persist_analysis('sess_z', SNAPSHOT, 'alice', 'completed')
        assert 'sess_z' in app_module._pending_persist

        captured = {}

        def working_save(session_id, **kwargs):
            captured['session_id'] = session_id
            captured.update(kwargs)
            return True

        monkeypatch.setattr(app_module.persistence_store, 'save_analysis', working_save)
        monkeypatch.setattr(app_module.threading, 'Timer',
                            lambda *a, **k: type('T', (), {'daemon': False,
                                                           'start': lambda self: None})())
        app_module._flush_pending_persists()

        assert app_module._pending_persist == {}, 'the retry did not clear the queue'
        assert captured['session_id'] == 'sess_z'
        # The retry must carry the SAME payload, not a stub.
        assert captured['snapshot']['statistics']['questions_answered'] == 7
        assert captured['owner'] == 'alice'
        assert captured['pdf_filename'] == 'spec.pdf'

    def test_a_still_failing_retry_keeps_the_analysis_queued(self, monkeypatch):
        monkeypatch.setattr(app_module.persistence_store, 'save_analysis',
                            lambda *a, **k: False)
        monkeypatch.setattr(app_module.threading, 'Timer',
                            lambda *a, **k: type('T', (), {'daemon': False,
                                                           'start': lambda self: None})())
        app_module._persist_analysis('sess_keep', SNAPSHOT, 'alice', 'completed')
        app_module._flush_pending_persists()
        assert 'sess_keep' in app_module._pending_persist, \
            'a still-unreachable database must not discard the analysis'

    def test_the_first_write_and_the_retry_share_one_code_path(self):
        """Two save calls that can drift is how a retry silently starts writing
        something different from the original."""
        import inspect
        for fn in (app_module._persist_analysis, app_module._flush_pending_persists):
            assert '_write_snapshot(' in inspect.getsource(fn), \
                f'{fn.__name__} must go through the shared writer'
