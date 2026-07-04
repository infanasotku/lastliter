import os


def pytest_configure():
    os.environ["ENV"] = "ci"
