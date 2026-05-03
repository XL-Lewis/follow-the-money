def test_package_imports_and_has_version():
    import ftm

    assert isinstance(ftm.__version__, str)
    assert ftm.__version__
