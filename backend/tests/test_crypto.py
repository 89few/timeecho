from app.core.crypto import decrypt_text, encrypt_text, mask_phone, phone_hash


def test_phone_hash_and_aes_roundtrip():
    h1 = phone_hash("13812345678")
    h2 = phone_hash("13812345678")
    assert h1 == h2
    assert "13812345678" not in h1
    token = encrypt_text("13812345678")
    assert token != "13812345678"
    assert decrypt_text(token) == "13812345678"
    assert mask_phone("13812345678") == "138****5678"
