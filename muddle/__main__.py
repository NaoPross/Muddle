#!/usr/bin/env python3

import argparse
import configparser
import logging
import colorlog

import os
import sys
import platform
import pathlib
import json

from . import moodle
from . import gui
from . import paths


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
    cli_handler = colorlog.StreamHandler()
    cli_handler.setLevel(logging.DEBUG)
    cli_formatter = colorlog.ColoredFormatter(
        "%(name)-13s - %(log_color)s%(levelname)-8s%(reset)s: %(message)s",
        datefmt=None,
        reset=True,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    cli_handler.setFormatter(cli_formatter)
    log.addHandler(cli_handler)

# C O N F I G S  A N D  L O G S

log.debug("set default config path {}".format(paths.default_config_file))
log.debug("set default log path {}".format(paths.default_log_file))

# user parameters

log_file = pathlib.Path(paths.default_log_file)
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

config_file = pathlib.Path(paths.default_config_file)
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

# runtime data that should NOT be written
config.add_section("runtime_data")
config["runtime_data"]["config_path"] = str(config_file)


# S T A R T

if args.version:
    print(f"""Version {MUDDLE_VERSION}
Muddle Copyright (C) 2020-2023 Nao Pross <np@0hm.ch>

This program comes with ABSOLUTELY NO WARRANTY; This is free software, and you
are welcome to redistribute it under certain conditions; see LICENSE.txt for
details. Project repository: https://github.com/NaoPross/Muddle
""")

if args.gui or config.getboolean("muddle", "always_run_gui"):
    gui.start(config)
