#!/usr/bin/env python3

import argparse
import configparser
import logging

import os
import sys
import platform
import pathlib
import json

import moodle
import gui


MUDDLE_VERSION = "0.1.0"

# A R G U M E N T S

parser = argparse.ArgumentParser(description="Moodle Scraper")
parser.add_argument("-g", "--gui", help="start with graphical interface", action="store_true")
parser.add_argument("-v", "--verbose", help="be more verbose", action="store_true")
parser.add_argument("-c", "--config", help="configuration file", type=str)
parser.add_argument("-l", "--logfile", help="where to save logs", type=str)
parser.add_argument("-V", "--version", help="version", action="store_true")
args = parser.parse_args()

# L O G G I N G

logformatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("muddle")
log.setLevel(logging.DEBUG)

if args.verbose:
    cli_handler = logging.StreamHandler()
    cli_handler.setLevel(logging.DEBUG)
    cli_handler.setFormatter(logformatter)
    log.addHandler(cli_handler)

# C O N F I G S  A N D  L O G S

# default location for configuration and log files

default_config_dir = pathlib.Path.cwd()
default_log_dir = pathlib.Path.cwd()

if platform.system() == "Linux":
    # compliant with XDG
    if os.environ.get("XDG_CONFIG_HOME"):
        default_config_dir = pathlib.PurePath(os.environ["XDG_CONFIG_HOME"]).joinpath("muddle/")

    elif pathlib.Path("~/.config").expanduser().exists():
        default_config_dir = pathlib.PurePath("~/.config/muddle/").expanduser()

    if os.environ.get("XDG_CACHE_HOME"):
        default_log_dir = pathlib.PurePath(os.environ["XDG_CACHE_HOME"]).joinpath("muddle/")

    elif pathlib.Path("~/.cache").expanduser().exists():
        default_log_dir = pathlib.PurePath("~/.cache/muddle/").expanduser()


# TODO: implement for other platforms

default_config_file = default_config_dir.joinpath("muddle.ini")
default_log_file = default_log_dir.joinpath("muddle.log")

log.debug("set default config path {}".format(default_config_file))
log.debug("set default log path {}".format(default_log_file))

# user parameters

log_file = pathlib.Path(default_log_file)
if args.logfile:
    if os.path.exists(args.logfile):
        log_file = pathlib.Path(args.logfile)
        log.debug(f"using log file {log_file}")
    else:
        log.error(f"path is not a file or does not exist {args.logfile}")
        log.debug("using default log path")

# set up logfile
log_file.parent.mkdir(parents=True, exist_ok=True)

file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(logformatter)
file_handler.setLevel(logging.INFO)

config_file = pathlib.Path(default_config_file)
if args.config:
    if os.path.isfile(args.config):
        config_file = pathlib.Path(args.config)
        log.debug(f"set config file {config_file}")
    else:
        log.error(f"path is not a file or does not exist {args.config}")
        log.debug("using default config path")

# parse config
if not config_file.is_file():
    log.error(f"cannot read {config_file}")
    sys.exit(1)

log.debug(f"reading config file {config_file}")
config = configparser.ConfigParser()
config.read(config_file)


# S T A R T

if args.version:
    print(f"""Version {MUDDLE_VERSION}
Muddle Copyright (C) 2020-2021 Nao Pross <np@0hm.ch>

This program comes with ABSOLUTELY NO WARRANTY; This is free software, and you
are welcome to redistribute it under certain conditions; see LICENSE.txt for
details. Project repository: https://github.com/NaoPross/Muddle
""")

if args.gui:
    gui.start(config["server"]["url"], config["server"]["token"])
