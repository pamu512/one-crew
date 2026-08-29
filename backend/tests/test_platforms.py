from fastapi.testclient import TestClient

import pytest

from onecrew.api import app
from onecrew.cut import event_cap, frame_count
from onecrew.models import PLATFORMS, Packet, Receipt
from onecrew.picks import PlatformRequiredError, require_platform
from onecrew.receipt import ReceiptInvalidError, write_receipt
from onecrew.seed import seed_findings, seed_links


def test_platforms_include_instagram_and_meta() -> None:
    assert "instagram" not in PLATFORMS
    assert PLATFORMS == (
        "tiktok",
        "youtube",
        "youtube_shorts",
        "instagram_reels",
        "instagram_stories",
        "instagram_feed",
        "facebook_reels",
        "facebook_feed",
        "threads",
        "podcast",
    )
    with pytest.raises(PlatformRequiredError):
        require_platform("instagram")
    with pytest.raises(PlatformRequiredError):
        require_platform("whatever-i-type")
    assert require_platform("instagram_stories") == "instagram_stories"
    assert require_platform("facebook_reels") == "facebook_reels"
    assert require_platform("threads") == "threads"
    with TestClient(app) as client:
        body = client.get("/api/platforms")
        assert body.status_code == 200
        payload = body.json()
        assert payload["default"] is None
        assert [row["id"] for row in payload["platforms"]] == list(PLATFORMS)


def test_stories_board_is_not_a_documentary_board() -> None:
    assert event_cap("full_length_documentary", "instagram_stories") < event_cap(
        "full_length_documentary", "youtube"
    )
    assert frame_count("full_length_documentary", "instagram_stories") < frame_count(
        "full_length_documentary", "youtube"
    )
    packet = Packet(
        id="oc-stories",
        hook="hook",
        script="script",
        platform="instagram_stories",
        depth="decade",
        cut="full_length_documentary",
    )
    with pytest.raises(ReceiptInvalidError, match="Stories board is not a documentary"):
        write_receipt(
            packet,
            Receipt(
                packet_id=packet.id,
                findings=seed_findings(),
                causal_links=seed_links(),
                disposition="READY",
            ),
        )


def test_reels_board_is_not_youtube_long_form() -> None:
    assert frame_count("full_length_documentary", "instagram_reels") < frame_count(
        "full_length_documentary", "youtube"
    )
    assert event_cap("full_length_documentary", "instagram_reels") < event_cap(
        "full_length_documentary", "youtube"
    )
