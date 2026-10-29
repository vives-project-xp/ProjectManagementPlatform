from nicegui import ui
from nicegui.testing import User

from pmp_frontend import api
from pmp_frontend.chat_page import file_size
from tests.conftest import JPG, eventually, ready_to_work
from tests.test_chat import api_token, drone_with_the_student, found


def test_file_sizes_read_like_people_say_them():
    assert file_size(820) == "820 B"
    assert file_size(14 * 1024) == "14 KB"
    assert file_size(int(3.2 * 1024 * 1024)) == "3.2 MB"


async def test_a_student_sends_a_photo_and_sees_its_thumbnail(user: User):
    await drone_with_the_student(await api_token("superuser"))
    await ready_to_work(user, "student")

    await user.open("/chat")
    await user.should_see(marker="chat-attach", retries=30)
    user.find(marker="chat-attach").click()
    await user.should_see(marker="chat-upload")
    upload = user.find(marker="chat-upload").elements.pop()
    assert isinstance(upload, ui.upload)
    await upload.handle_uploads(
        [
            ui.upload.SmallFileUpload(
                name="flight.jpg", content_type="image/jpeg", _data=JPG
            )
        ]
    )
    await user.should_see("flight.jpg", retries=30)
    user.find(marker="chat-send").click()

    await eventually(lambda: bool(found(user, "chat-photo-1")), retries=100)
    thumbnail = found(user, "chat-photo-1")[0]
    assert isinstance(thumbnail, ui.image)
    assert thumbnail.source == "/chat-files/1"
    response = await user.http_client.get(thumbnail.source)
    assert response.status_code == 200
    assert response.content == JPG
    await eventually(lambda: not found(user, "chat-attachments"))

    # A click opens the photo full size.
    user.find(marker="chat-photo-1").click()
    await user.should_see(marker="full-photo", retries=30)


async def test_other_files_are_downloads_with_their_size(user: User):
    superuser = await api_token("superuser")
    drone = await drone_with_the_student(superuser)
    teacher = await api_token("teacher")
    await api.send_chat_message(
        teacher, drone, "", [("plan.pdf", b"%PDF" + b"x" * 2048, "application/pdf")]
    )
    await ready_to_work(user, "student")

    await user.open("/chat")
    await user.should_see(marker="chat-file-1", retries=30)
    await user.should_see("plan.pdf")
    await user.should_see("(2 KB)")
    link = next(
        element
        for element in found(user, "chat-file-1")[0].descendants()
        if isinstance(element, ui.link)
    )
    response = await user.http_client.get(link.props["href"])
    assert response.headers["content-disposition"].startswith("attachment")
