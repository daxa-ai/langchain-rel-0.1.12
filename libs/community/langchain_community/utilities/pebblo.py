from __future__ import annotations

import logging
import os
import pathlib
import platform
from enum import Enum
from typing import Optional, Tuple

from langchain_core.env import get_runtime_environment
from langchain_core.pydantic_v1 import BaseModel
from langchain_community.document_loaders.base import BaseLoader


logger = logging.getLogger(__name__)

PLUGIN_VERSION = "0.1.0"
IP_INFO_URL = "https://ipinfo.io/ip"
CLASSIFIER_URL = os.getenv("PEBBLO_CLASSIFIER_URL", "http://localhost:8000/v1")

file_loader = [
    "JSONLoader",
    "S3FileLoader",
    "UnstructuredMarkdownLoader",
    "UnstructuredPDFLoader",
    "UnstructuredFileLoader",
    "UnstructuredJsonLoader",
    "PyPDFLoader",
    "GCSFileLoader",
    "AmazonTextractPDFLoader",
    "CSVLoader",
    "UnstructuredExcelLoader",
    "UnstructuredEmailLoader",
    ]

dir_loader = [
    "DirectoryLoader",
    "S3DirLoader",
    "SlackDirectoryLoader",
    "PyPDFDirectoryLoader",
    "NotionDirectoryLoader",
    ]

in_memory = ["DataFrameLoader"]

remote_db = ["NotionDBLoader", "GoogleDriveLoader",]

LOADER_TYPE_MAPPING = {"file": file_loader, "dir": dir_loader, "in-memory": in_memory, "remote_db": remote_db}

SUPPORTED_LOADERS = (*file_loader, *dir_loader, *in_memory, *remote_db)

logger = logging.getLogger(__name__)


class Runtime(BaseModel):
    """This class represents a Runtime.

    Args:
        type (Optional[str]): Runtime type. Defaults to ""
        host (str): Hostname of runtime.
        path (str): Current working directory path.
        ip (Optional[str]): Ip of current runtime. Defaults to ""
        platform (str): Platform details of current runtime.
        os (str): OS name.
        os_version (str): OS version.
        language (str): Runtime kernel.
        language_version (str): version of current runtime kernel.
        runtime (Optional[str]) More runtime details. Defaults to ""
    """
    type: Optional[str] = ""
    host: str
    path: str
    ip: Optional[str] = ""
    platform: str
    os: str
    os_version: str
    language: str
    language_version: str
    runtime: Optional[str] = ""


class Framework(BaseModel):
    """This class represents a Framework instance.

    Args:
        name (str): Name of the Framework.
        version (str): Version of the Framework.
    """
    name: str
    version: str


class App(BaseModel):
    """This class represents an AI application.

    Args:
        name (str): Name of the app.
        owner (str): Owner of the app.
        description (Optional[str]): Description of the app.
        load_id (str): Unique load_id of the app instance.
        runtime (Runtime): Runtime details of app.
        framework (Framework): Framework details of the app
        plugin_version (str): Plugin version used for the app.
    """
    name: str
    owner: str
    description: Optional[str]
    load_id: str
    runtime: Runtime
    framework: Framework
    plugin_version: str


class Doc(BaseModel):
    """This class represents a pebblo document.

    Args:
        name (str): Name of app originating this document.
        owner (str): Owner of app.
        docs (list): List of documents with its metadata.
        plugin_version (str): Pebblo plugin Version
        load_id (str): Unique load_id of the app instance.
        loader_details (dict): Loader details with its metadata.
        loading_end (bool): Boolean, specifying end of loading of source.
        source_owner (str): Owner of the source of the loader.
    """

    name: str
    owner: str
    docs: list
    plugin_version: str
    load_id: str
    loader_details: dict
    loading_end: bool
    source_owner: str


def get_full_path(path: str) -> str:
    """Return absolute local path for a local file/directory,
    for network related path, return as is.

    Args:
        path (str): Relative path to be resolved.

    Returns:
        str: Resolved absolute path.
    """
    if (
        not path
        or ("://" in path)
        or ("/" == path[0])
        or (path in ["unknown", "-", "in-memory"])
    ):
        return path
    full_path = pathlib.Path(path).resolve()
    return str(full_path)


def get_loader_type(loader: str):
    """Return loader type among, file, dir or in-memory.

    Args:
        loader (str): Name of the loader, whose type is to be resolved.

    Returns:
        str: One of the loader type among, file/dir/in-memory.
    """
    for loader_type, loaders in LOADER_TYPE_MAPPING.items():
        if loader in loaders:
            return loader_type
    return "unknown"


def get_loader_full_path(loader: BaseLoader):
    """Return absolute source path of source of loader based on the
    keys present in Document object from loader.

    Args:
        loader (BaseLoader): Langchain document loader, derived from Baseloader.
    """
    from langchain_community.document_loaders import (
        DataFrameLoader,
        GCSFileLoader,
        S3FileLoader,
        NotionDBLoader,
    )

    location = "-"
    if not isinstance(loader, BaseLoader):
        logger.error(
            "loader is not derived from BaseLoader, source location will be unknown!"
        )
        return location
    loader_keys = loader.__dict__.keys()
    if "bucket" in loader_keys:
        if isinstance(loader, GCSFileLoader):
            location = f"gc://{loader.bucket}/{loader.blob}"
        elif isinstance(loader, S3FileLoader):
            location = f"s3://{loader.bucket}/{loader.key}"
    elif "source" in loader_keys:
        location = f"{loader.source}"
        if "channel" in loader_keys:
            location = f"{location}/{loader.channel}"
    elif "path" in loader_keys:
        location = loader.path
    elif "file_path" in loader_keys:
        location = loader.file_path
    elif "web_paths" in loader_keys:
        location = loader.web_paths[0]
    # For in-memory types:
    elif isinstance(loader, DataFrameLoader):
        location = "in-memory"
    elif isinstance(loader, NotionDBLoader):
        location = location = f"notiondb://{loader.database_id}"
    return get_full_path(str(location))


def get_runtime() -> Tuple[Framework, Runtime]:
    """Fetch the current Framework and Runtime details.

    Returns:
        Tuple[Framework, Runtime]: Framework and Runtime for the current app instance.
    """
    runtime_env = get_runtime_environment()
    framework = Framework(
        name="langchain", version=runtime_env.get("library_version", None)
    )
    uname = platform.uname()
    runtime = Runtime(
        host=uname.node,
        path=os.environ["PWD"],
        platform=runtime_env.get("platform", "unknown"),
        os=uname.system,
        os_version=uname.version,
        language=runtime_env.get("runtime", "unknown"),
        language_version=runtime_env.get("runtime_version", "unknown"),
    )

    if "Darwin" in runtime.os:
        runtime.type = "desktop"
        logger.debug("MacOS")
        local_runtime = get_local_runtime("local")
        runtime.ip = local_runtime.get("ip", "")
        runtime.runtime = local_runtime.get("runtime", "local")
        return framework, runtime

    curr_runtime = get_local_runtime("local")

    runtime.type = curr_runtime.get("type", "unknown")
    runtime.ip = curr_runtime.get("ip", "")
    runtime.runtime = curr_runtime.get("runtime", "unknown")

    logger.debug(f"runtime {runtime}")
    logger.debug(f"framework {framework}")
    return framework, runtime


def get_local_runtime(service):
    """Fetch local runtime details

    Args:
        service (str): `local`

    Returns:
        dict: Runtime details.
    """
    import socket  # lazy imports

    import requests

    host = socket.gethostname()
    try:
        public_ip = socket.gethostbyname(host)
    except Exception:
        public_ip = socket.gethostbyname("localhost")
    path = os.getcwd()
    name = host
    runtime = {
        "type": "local",
        "host": host,
        "path": path,
        "ip": public_ip,
        "name": name,
        "runtime": service,
    }
    return runtime
