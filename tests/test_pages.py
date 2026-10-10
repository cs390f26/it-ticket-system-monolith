import pytest


@pytest.mark.parametrize(
    "path, text",
    [
        ("/", "IT Help Desk"),
        ("/submit", "Report a problem"),
        ("/queue", "All tickets"),
        ("/ticket?id=HD-1042", "Update Ticket"),
    ],
)
def test_page_renders(client, path, text):
    response = client.get(path)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert text in response.get_data(as_text=True)


def test_submit_page_offers_other_category(client):
    assert "<option>Other</option>" in client.get("/submit").get_data(as_text=True)


def test_ads_shown_by_default(client):
    assert 'id="ad-slot"' in client.get("/").get_data(as_text=True)


def test_ads_can_be_turned_off(ticket_app):
    from tickets.app import create_app

    page = create_app(ticket_app, show_ads=False).test_client().get("/")
    assert "ad-slot" not in page.get_data(as_text=True)


@pytest.mark.parametrize("filename", ["styles.css", "app.js", "ads.css", "ads/support-plus-1.jpg"])
def test_static_files_served(client, filename):
    response = client.get("/static/" + filename)
    assert response.status_code == 200
    response.close()
