def test_package_importable():
    import tutor
    assert tutor.__version__ == "0.1.0"
