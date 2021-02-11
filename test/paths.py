import pytest

from muddle import paths

def test_defaults():
	assert paths.default_log_dir != None
	assert paths.default_log_file != None
	assert paths.default_config_dir != None
	assert paths.default_config_file != None