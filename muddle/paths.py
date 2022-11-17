import pathlib
import platform
import os

default_config_dir = pathlib.Path.cwd()
default_log_dir = pathlib.Path.cwd()

if platform.system() == "Linux":
    # compliant with XDG
    if os.environ.get("XDG_CONFIG_HOME"):
        default_config_dir = pathlib.PurePath(os.environ["XDG_CONFIG_HOME"]).joinpath("muddle/")

    elif pathlib.Path("~/.config").expanduser().exists():
        default_config_dir = pathlib.Path("~/.config/muddle/").expanduser()

    if os.environ.get("XDG_CACHE_HOME"):
        default_log_dir = pathlib.Path(os.environ["XDG_CACHE_HOME"]).joinpath("muddle/")

    elif pathlib.Path("~/.cache").expanduser().exists():
        default_log_dir = pathlib.Path("~/.cache/muddle/").expanduser()

elif platform.system() == "Windows":
    if os.environ.get("APPDATA"):
        default_config_dir = pathlib.Path(os.environ["APPDATA"]).joinpath("muddle/")

    if os.environ.get("LOCALAPPDATA"):
        default_log_dir = pathlib.Path(os.environ["LOCALAPPDATA"]).joinpath("muddle")

elif platform.system() == "Darwin":
    default_config_dir = pathlib.Path("~/Library/Preferences/ch.0hm.muddle/").expanduser()
    default_log_dir = pathlib.Path("~/Library/Caches/ch.0hm.muddle/").expanduser()


default_config_file = default_config_dir.joinpath("muddle.ini")
default_log_file = default_log_dir.joinpath("muddle.log")
