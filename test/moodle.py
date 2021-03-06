import pytest

import pathlib
import configparser

from muddle import paths
from muddle import moodle

config_file = pathlib.Path(paths.default_config_file)
if not config_file.is_file():
    log.error(f"cannot read {config_file}")
    sys.exit(1)

config = configparser.ConfigParser()
config.read(config_file)


class TestMoodleInstance:
    server = moodle.MoodleInstance(config["server"]["url"], config["server"]["token"])

    def test_get_userid(self):
        assert self.server.get_userid() != None

    def test_get_enrolled_courses(self):
        assert type(next(self.server.get_enrolled_courses())) == moodle.Course


def test_moodle_api():
    server = moodle.MoodleInstance(config["server"]["url"], config["server"]["token"])

    for course in server.get_enrolled_courses():
        print(course.shortname)
        for section in course.get_sections(server.api):
            print(section.name)
            for module in section.get_modules():
                print(module.name)
