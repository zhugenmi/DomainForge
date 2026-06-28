from app.configs.settings import settings


def test_chat_attachment_settings():
    assert settings.CHAT_ATTACHMENT_TTL == 600
    assert settings.MAX_CHAT_ATTACHMENTS == 5
    assert settings.MAX_CHAT_ATTACHMENT_MB == 20
