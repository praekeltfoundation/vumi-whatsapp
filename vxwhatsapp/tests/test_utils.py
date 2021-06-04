from vxwhatsapp.utils import valid_url


def test_valid_url():
    """
    Ensure that it returns True for valid URLs, and False for invalid ones
    """
    assert valid_url(None) is False
    assert valid_url("\t") is False
    # https://github.com/django/django/blob/main/tests/validators/invalid_urls.txt
    for url in open("vxwhatsapp/tests/invalid_urls.txt"):
        assert valid_url(url.strip()) is False
    # https://github.com/django/django/blob/main/tests/validators/valid_urls.txt
    for url in open("vxwhatsapp/tests/valid_urls.txt"):
        assert valid_url(url.strip()) is True
