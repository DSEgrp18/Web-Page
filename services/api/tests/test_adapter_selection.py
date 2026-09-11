"""Which voice the server serves, and how it says so.

None of these tests load a checkpoint. `XttsAdapter` defers importing torch and
reading the bundle until `load()`, which is what makes it possible to test the
*choice* on a machine with neither — and is also what these tests must not
accidentally undo. One of them exists specifically to catch that.

Every ``Deps`` here names its store. Left to ``build_store()`` it would come
from the environment, so running these with ``SINHALA_READER_DATABASE_URL`` set
— as CI does — would share one database with every other test and make
assertions about what a reader owns depend on what ran before them.
"""

from __future__ import annotations

import pytest
from conftest import READER, as_reader
from fastapi.testclient import TestClient
from sinhala_tts.adapter import DevelopmentAdapter, ReadinessState, XttsAdapter

from sinhala_reader import Deps, create_app
from sinhala_reader.adapters import (
    ADAPTER_ENV,
    DEVICE_ENV,
    adapter_mode,
    build_adapter,
    loaded_model_version,
    warm,
)
from sinhala_reader.storage import InMemoryStore


@pytest.fixture(autouse=True)
def no_inherited_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test states its own configuration; none inherits the shell's."""
    monkeypatch.delenv(ADAPTER_ENV, raising=False)
    monkeypatch.delenv(DEVICE_ENV, raising=False)


class TestChoosing:
    def test_the_default_is_the_labelled_placeholder(self) -> None:
        # Safe rather than timid: a tone carries is_real_model=False everywhere,
        # so it can never be mistaken for narration. Defaulting the other way
        # would make every test run try to load 5.6 GB.
        assert adapter_mode() == "development"
        assert isinstance(build_adapter(), DevelopmentAdapter)

    def test_the_real_voice_can_be_asked_for(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ADAPTER_ENV, "xtts")
        adapter = build_adapter()
        assert isinstance(adapter, XttsAdapter)
        assert adapter.is_real_model is True
        # Chosen, not loaded. Selection must not touch the bundle.
        assert adapter.readiness is ReadinessState.NOT_LOADED

    def test_the_name_is_not_case_or_space_sensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ADAPTER_ENV, "  XTTS ")
        assert isinstance(build_adapter(), XttsAdapter)

    def test_a_device_can_be_forced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # On a 4 GB card this skips an out-of-memory attempt that would fall
        # back to CPU anyway.
        monkeypatch.setenv(ADAPTER_ENV, "xtts")
        monkeypatch.setenv(DEVICE_ENV, "cpu")
        assert build_adapter()._requested_device == "cpu"

    def test_an_unknown_voice_stops_the_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # CLAUDE.md forbids silently falling back to another voice. A typo in a
        # deployment variable must not quietly serve tones to a reader who was
        # promised speech.
        monkeypatch.setenv(ADAPTER_ENV, "xttts")
        with pytest.raises(ValueError) as raised:
            build_adapter()
        message = str(raised.value)
        assert "xttts" in message
        assert "development" in message and "xtts" in message


class TestWarmUp:
    def test_a_placeholder_needs_no_warming(self) -> None:
        assert warm(DevelopmentAdapter()) is None

    def test_a_failing_load_does_not_take_the_process_down(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A background thread that raises kills the process silently.

        The adapter's own state is the reporting channel, so the failure has to
        stay inside it and reach `/readiness`, not escape onto a thread nobody
        is watching.
        """
        monkeypatch.setenv(ADAPTER_ENV, "xtts")
        # No SINHALA_TTS_MODEL_DIR is set, so loading fails immediately with a
        # message about the missing bundle — a real failure, not a mocked one.
        adapter = build_adapter()
        thread = warm(adapter)
        assert thread is not None
        # Generous, because on a machine that actually has torch installed the
        # failing path still imports it first, and that alone measured about 25
        # seconds here — close enough to a 30-second bound that the test failed
        # whenever anything else was running. CI has no torch and fails in
        # milliseconds. The bound is only here so a genuine hang is not reported
        # as a pass.
        thread.join(timeout=180)
        assert not thread.is_alive()
        assert adapter.readiness is ReadinessState.FAILED


class TestReadinessTellsTheTruth:
    def test_it_names_the_voice_and_says_a_tone_is_a_tone(self) -> None:
        client = TestClient(create_app(Deps(store=InMemoryStore(), run_in_background=False)))
        body = client.get("/readiness").json()
        assert body["voice"] == "development"
        assert body["real_model"] is False
        assert body["model_version"] is None
        assert any("placeholder tone" in note for note in body["limitations"])
        # And says how to get the real one, rather than leaving it to be found.
        assert any(ADAPTER_ENV in note for note in body["limitations"])

    def test_a_cold_start_is_reported_as_a_cold_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ADAPTER_ENV, "xtts")
        adapter = XttsAdapter()  # never loaded: warming is off for this app
        client = TestClient(
            create_app(
                Deps(
                    store=InMemoryStore(),
                    adapter=adapter,
                    run_in_background=False,
                    warm_on_start=False,
                )
            )
        )

        body = client.get("/readiness").json()
        assert body["real_model"] is True
        assert body["readiness"] == ReadinessState.NOT_LOADED
        assert body["serving"] is False
        # Not a fault: an operator who reads this waits instead of restarting
        # the process and paying for the load twice.
        assert any("still loading" in note for note in body["limitations"])
        # The tone limitation must NOT appear — this server serves speech.
        assert not any("placeholder tone" in note for note in body["limitations"])

    def test_a_dead_voice_does_not_read_as_a_healthy_server(self) -> None:
        """Found by running it, not by reading it.

        With the real voice selected and coqui-tts missing, `/readiness`
        reported `readiness: failed` and then three limitations about storage,
        auth and origins — none about the voice. A skim read that as healthy.
        The adapter's own failure reason has to reach the report.
        """

        class Broken(XttsAdapter):
            @property
            def readiness(self) -> ReadinessState:
                return ReadinessState.FAILED

            @property
            def failure_reason(self) -> str:
                return "No module named 'TTS'"

        client = TestClient(
            create_app(
                Deps(
                    store=InMemoryStore(),
                    adapter=Broken(),
                    run_in_background=False,
                    warm_on_start=False,
                )
            )
        )
        body = client.get("/readiness").json()

        assert body["serving"] is False
        assert any("failed to load" in note for note in body["limitations"])
        # And the actual reason, not just that something went wrong.
        assert any("No module named" in note for note in body["limitations"])
        assert body["voice_detail"] == "No module named 'TTS'"
        # Still not a cold start, and still not a placeholder.
        assert not any("still loading" in note for note in body["limitations"])
        assert not any("placeholder tone" in note for note in body["limitations"])

    def test_a_health_probe_never_loads_the_checkpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The bug this guards is subtle and expensive.

        `TtsAdapter.model_version` loads the bundle if it has not been loaded,
        which is right for synthesis — a cache key must describe the model that
        would actually produce the audio — and wrong for a health check. A probe
        that blocks for ninety seconds gets killed by whatever is probing it,
        and a cold start is then reported as an outage.
        """
        loads: list[str] = []

        class Tripwire(XttsAdapter):
            def load(self) -> None:
                loads.append("load")
                raise AssertionError("a readiness probe must never load the model")

        adapter = Tripwire()
        monkeypatch.setenv(ADAPTER_ENV, "xtts")
        # Warming is what legitimately loads the model. Turning it off leaves
        # the probes as the only thing that could, which is the point.
        client = TestClient(
            create_app(
                Deps(
                    store=InMemoryStore(),
                    adapter=adapter,
                    run_in_background=False,
                    warm_on_start=False,
                )
            )
        )

        assert client.get("/readiness").status_code == 200
        assert client.get("/health").status_code == 200
        assert loads == []

    def test_a_failed_load_does_not_send_a_probe_back_into_loading(self) -> None:
        """The deny-list bug, guarded.

        An earlier version excluded only NOT_LOADED and LOADING, so an adapter
        whose load had *failed* fell through to the blocking path and tried
        again — inside a health check.
        """
        loads: list[str] = []

        class Failed(XttsAdapter):
            @property
            def readiness(self) -> ReadinessState:
                return ReadinessState.FAILED

            def load(self) -> None:
                loads.append("load")

        assert loaded_model_version(Failed()) is None
        assert loads == []

    def test_the_version_appears_once_there_is_one(self) -> None:
        class Loaded(XttsAdapter):
            @property
            def readiness(self) -> ReadinessState:
                return ReadinessState.READY

            @property
            def model_version(self) -> str:
                return "ce18fe82442ccbd3"

        assert loaded_model_version(Loaded()) == "ce18fe82442ccbd3"

    def test_no_document_is_served_while_the_voice_is_cold(self) -> None:
        """Ownership does not become laxer because the model is not ready."""
        client = TestClient(
            create_app(
                Deps(
                    store=InMemoryStore(),
                    adapter=XttsAdapter(),
                    run_in_background=False,
                    warm_on_start=False,
                )
            )
        )
        response = client.get("/documents", headers=as_reader(client, READER))
        assert response.status_code == 200
        assert response.json() == []
