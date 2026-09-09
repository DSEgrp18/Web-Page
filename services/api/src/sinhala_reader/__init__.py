"""The reader API.

``create_app`` builds the application around an explicit set of dependencies,
which is what lets a test swap the store or the synthesiser without patching a
module.
"""

from .app import Deps, create_app
from .storage import Document, InMemoryStore, Job, JobState, Progress, Store

__all__ = [
    "Deps",
    "Document",
    "InMemoryStore",
    "Job",
    "JobState",
    "Progress",
    "Store",
    "create_app",
]
