import pytest


@pytest.mark.parametrize(
    "path, text",
    [
        ("/", "IT Help Desk"),
        ("/submit", "Submit a ticket"),
        ("/queue", "Ticket queue"),
        ("/ticket?id=HD-1042", "Update ticket"),
    ],
)
def test_page_renders(client, path, text):
    response = client.get(path)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert text in response.get_data(as_text=True)


def test_submit_page_offers_other_category(client):
    assert "<option>Other</option>" in client.get("/submit").get_data(as_text=True)


@pytest.mark.parametrize("filename", ["styles.css", "app.js"])
def test_static_files_served(client, filename):
    response = client.get("/static/" + filename)
    assert response.status_code == 200
    response.close()
