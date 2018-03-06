# -*- coding: utf-8 -*-
"""CRI logger

This module is designed to just handle logging. There's nothing more to it
Just printing and logging to files

Developed By: David Smerkous and Eli Smith
"""

from logging import getLogger, DEBUG, Formatter, FileHandler, StreamHandler
from os.path import dirname, realpath, isdir, exists, join, basename
from os import makedirs, walk, remove
from time import strftime, strptime, mktime
from datetime import datetime
from sys import stdout
import fnmatch

# Define logging characteristics
LOGGER_NAME = "CRI"
LOGGER_LEVEL = DEBUG
LOGGER_STORE_DAYS = 5 # Maximum amount of days to store a log file before deleting it

LOGGER_FORMAT = Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
LOGGER_FILE_PATH = "%s/logs" % dirname(realpath(__file__))
LOGGER_FILE_DATE_FORMAT = "%d-%m-%y--%H-%M-%S"
LOGGER_FILE_DATE = strftime(LOGGER_FILE_DATE_FORMAT)
LOGGER_FILE_FORMAT = "%s/%s.log" % (LOGGER_FILE_PATH, LOGGER_FILE_DATE)

if not isdir(LOGGER_FILE_PATH):
    print("Creating new log location %s..." % LOGGER_FILE_PATH),
    makedirs(LOGGER_FILE_PATH)
    print("Done")

LOG_FILES = [join(dirpath, f) for dirpath, dirnames, files in walk(LOGGER_FILE_PATH) for f in fnmatch.filter(files, '*.log')]

print("Looking for old log files...")

TODAY_NOW = datetime.now()
DELETED_FILES = 0
for l_file in LOG_FILES:
    try:
        c_date = datetime.fromtimestamp(mktime(strptime(basename(l_file).split(".")[0], LOGGER_FILE_DATE_FORMAT)))
        days_old = (TODAY_NOW - c_date).days
        if days_old > LOGGER_STORE_DAYS:
            remove(l_file)
            print("Deleted old file %s" % l_file)
            DELETED_FILES += 1
    except Exception as err:
        print("Failed to delete log file %s (err: %s)" % (l_file, str(err)))

print("Deleted a total of %d old log files" % DELETED_FILES)

if not exists(LOGGER_FILE_FORMAT):
    print("Creating new log file %s..." % LOGGER_FILE_FORMAT),
    open(LOGGER_FILE_FORMAT, 'w').close()
    print("Done")

LOGGER_FILE_HANDLER = FileHandler(LOGGER_FILE_FORMAT)
LOGGER_FILE_HANDLER.setFormatter(LOGGER_FORMAT)
LOGGER_CONSOLE_HANDLER = StreamHandler(stdout)
LOGGER_CONSOLE_HANDLER.setFormatter(LOGGER_FORMAT)
LOGGER = getLogger(LOGGER_NAME)
LOGGER.addHandler(LOGGER_FILE_HANDLER)
LOGGER.addHandler(LOGGER_CONSOLE_HANDLER)


class Logger(object):
    def __init__(self, name_space, logger_level=LOGGER_LEVEL):
        LOGGER.setLevel(logger_level)
        LOGGER.debug("Starting logger!")
        self._name_space = name_space

    def __base_log(self, to_log):
        return "|%s|: %s" % (self._name_space, str(to_log))

    def info(self, to_log):
        LOGGER.info(self.__base_log(to_log))

    def debug(self, to_log):
        LOGGER.debug(self.__base_log(to_log))

    def warning(self, to_log):
        LOGGER.warning(self.__base_log(to_log))

    def error(self, to_log):
        LOGGER.error(self.__base_log(to_log))
