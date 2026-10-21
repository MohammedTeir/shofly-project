import pytest
from shofly_worker import cli
from shofly_worker.config import WorkerSettings
from shofly_worker.providers import LocalDirProvider


def S(**kw):
    return WorkerSettings(api_base_url="http://x", worker_api_token="t", **kw)


def test_build_provider_validates_configuration(tmp_path):
    assert isinstance(cli.build_provider(S(provider="local", local_dir=str(tmp_path))), LocalDirProvider)
    with pytest.raises(SystemExit):
        cli.build_provider(S(provider="telegram"))            # missing token/channel
    with pytest.raises(SystemExit):
        cli.build_provider(S(provider="s3"))
    assert cli.build_provider(S(provider="telegram", telegram_bot_token="1:a", telegram_chat_id="-100")).name == "telegram"


def test_loop_processes_sleeps_between_cycles_but_not_after_last(monkeypatch):
    batches = iter([["COMPLETED", "COMPLETED"], [], ["FAILED"]])
    monkeypatch.setattr(cli, "run_until_empty", lambda *a, **k: next(batches))
    naps = []
    total = cli.loop(None, None, S(poll_seconds=7), None, max_cycles=3, sleep=naps.append)
    assert total == 3 and naps == [7, 7]
