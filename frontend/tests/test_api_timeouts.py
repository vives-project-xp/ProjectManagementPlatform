import httpx
import pytest

from pmp_frontend import api


@pytest.fixture
def timeouts(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The timeout of every API client the frontend opens."""
    seen: list[float] = []
    real_client = api._client

    def spying_client(timeout: float = api.TIMEOUT) -> httpx.AsyncClient:
        seen.append(timeout)
        return real_client(timeout)

    monkeypatch.setattr(api, "_client", spying_client)
    return seen


@pytest.mark.parametrize(
    "bulk_action",
    [
        api.create_repos,
        api.check_all_members,
        api.create_trello_boards,
        api.check_all_trello_members,
    ],
)
async def test_actions_for_all_projects_wait_longer(timeouts, bulk_action):
    # Without a login the backend refuses; only the wait matters here.
    with pytest.raises(api.ApiError):
        await bulk_action("no-token")

    assert timeouts == [api.BULK_TIMEOUT]


async def test_other_calls_keep_the_short_wait(timeouts):
    with pytest.raises(api.ApiError):
        await api.github_status("no-token")

    assert timeouts == [api.TIMEOUT]
