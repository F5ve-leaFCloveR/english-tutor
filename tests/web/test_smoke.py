def test_web_package_importable():
    import tutor.web
    assert tutor.web is not None


def test_fastapi_available():
    import fastapi
    assert hasattr(fastapi, "FastAPI")
