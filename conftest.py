import os
import pytest


@pytest.fixture(autouse=True)
def set_project_root(monkeypatch):
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    monkeypatch.chdir(project_root)