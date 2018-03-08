# -*- coding: utf-8 -*-
"""CRI app collector

This module is designed to handle the graphical applications and icons on the machine
to report them back to the html/javascript front end so that it's all pretty and functional

Developed By: David Smerkous and Eli Smith
"""

from logger import Logger
from os.path import dirname, realpath, isdir, exists, join, basename
from os import makedirs, walk, remove
from base64 import b64encode
import fnmatch
import gtk
import re

# Configs
log = Logger("APP")
applications_dir = "/usr/share/applications"
icon_theme = "Numix"
app_list = []
theme = gtk.IconTheme()
theme.set_custom_theme(icon_theme)
icon_size = 256

class Application(object):
    def __init__(self, name):
        self._name = name
        self._full_name = None
        self._icon_name = "exec"
        self._icon_path = None
        self._exec = None
        self._comment = None
        self._version = None

    def _g_prop(self, c, to_get, default=None):
        if ("%s=" % to_get) not in c:
            return default
        filtered = filter(None, re.findall(r"%s=(.*?)\n" % to_get, c, re.DOTALL))
        if len(filtered) == 0:
            return None
        return filtered[0]
    
    def load(self, desktop_file):
        with open(desktop_file, 'r') as d:
            dc = d.read()
            self._full_name = self._g_prop(dc, "Name")
            self._icon_name = self._g_prop(dc, "Icon", "exec")
            self._exec = self._g_prop(dc, "Exec")
            if self._exec is None:
                log.warning("Application %s doesn't have an exec!" % self._name)
                self._exec = self._g_prop(dc, "TryExec")
                if self._exec is None:
                    log.error("Failed to load %s! There's no executable!")
                    return False
            self._comment = self._g_prop(dc, "Comment")
            self._version = self._g_prop(dc, "Version")
            return True

    def fix(self):
        if self._full_name is None:
            self._full_name = self._name

        # Remove the optional command arguments
        print(self._exec)
        self._exec = re.sub(r'%\w', '', self._exec)
        
        # Get the full icon path
        icon = theme.lookup_icon(self._icon_name, icon_size, 0)
        if icon is None:
            icon = theme.lookup_icon("exec", icon_size, 0)
        self._icon_path = icon.get_filename()
        log.info("Found icon at %s (executable: %s)" % (self._icon_path, self._exec))

    def get_dict(self, load_icon=True):
        try:
            icon_type = basename(self._icon_path).split(".")[1]
        except Exception as err:
            log.error("Failed to load icon type %s (err: %s)" % (load_icon, str(err)))
            icon_type = None

        icon_data = None
        if load_icon:
            with open(self._icon_path, 'r') as ld:
                icon_data = b64encode(ld.read())
        return {
            "name": self._name,
            "full_name": self._full_name,
            "icon_type": icon_type, 
            "icon": icon_data,
            "comment": self._comment,
            "version": self._version
        }

    def get_name(self):
        return self._full_name

    @staticmethod
    def get_app_list():
        global app_list
        return app_list

    @staticmethod
    def load_app_list():
        global app_list
        d_files = [join(dirpath, f) for dirpath, dirnames, files in walk(applications_dir) for f in fnmatch.filter(files, "*.desktop")]
        app_list = []
        for d in d_files:
            name = basename(d).split(".")[0]
            log.info("Loading application %s" % name)
            app = Application(name)
            if app.load(d):
                app.fix()
                app_list.append(app)
        app_list = sorted(app_list, key=lambda x: x.get_name())
        log.info("Loaded a total of %d applications" % len(app_list))

Application.get_app_list()
