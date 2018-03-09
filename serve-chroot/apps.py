# -*- coding: utf-8 -*-
"""CRI app collector

This module is designed to handle the graphical applications and icons on the machine
to report them back to the html/javascript front end so that it's all pretty and functional

Developed By: David Smerkous and Eli Smith
"""

from logger import Logger
from os.path import dirname, realpath, isdir, exists, join, basename, splitext
from os import makedirs, walk, remove
from apt import cache, package
from apt.progress.base import AcquireProgress, InstallProgress
import base64
import mimetypes
import socket
import fnmatch
import gtk
import re

# Configs
log = Logger("APP")
applications_dir = "/usr/share/applications"
config_dir = "/etc/cri/serve-chroot"
remote_test_server = "8.8.8.8"
remote_test_port = 53
icon_theme = "Numix"
theme = gtk.IconTheme()
theme.set_custom_theme(icon_theme)
icon_size = 256
default_icon = theme.lookup_icon("exec", icon_size, 0) 

# Global locked variables
app_list = []
cche = cache.Cache()

# Global functions 
def check_internet():
    try:
        log.info("Checking for an internet connection...")
        socket.setdefaulttimeout(1)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((remote_test_server, remote_test_port))
        log.info("Connected to the internet!")
        return True
    except:
        pass
    log.error("No internet connection!")
    return False

class CriFetchProgress(AcquireProgress):
    def set_socket(self, websocket):
        self._socket = websocket

    def fail(self, item):
        self._socket.send_dict({
            "exec": "error",
            "message": "Failed to install a resource! Make sure you're connected to the internet"
        })

    def pulse(self, owner):
        self._socket.send_dict({
            "exec": "aquire_status",
            "count": self.current_items,
            "total_count": self.total_items,
            "bytes": self.fetched_bytes,
            "total_bytes": self.total_bytes,
            "bytes_second": self.current_cps
        })
        return True

class CriInstallProgress(InstallProgress):
    def set_socket(self, websocket, flag="install"):
        self._socket = websocket
        self._flag = flag

    def error(self, pkg, errormsg):
        self._socket.send_dict({
            "exec": "error",
            "message": "Failed to %s %s (err: %s)" % (self._flag, pkg, errormsg)
        })

    def start_update(self):
        log.info("Starting to %s package" % self._flag)
        self._socket.send_dict({
            "exec": "%s_start" % self._flag
        })

    def finish_update(self):
        log.info("Finished %s the package" % self._flag)
        self._socket.send_dict({
            "exec": "%s_finish" % self._flag
        })

    def status_change(self, pkg, percent, status):
        self._socket.send_dict({
            "exec": "%s_status" % self._flag,
            "package": pkg,
            "percent": percent,
            "status": status
        })

# Define the progress objects
f_progress = CriFetchProgress()
i_progress = CriInstallProgress()

class Package(object):
    def __init__(self, name):
        self._name = name
        self._full_name = None
        self._comment = None
        self._icon_type = "png"
        self._icon_path = None
        self._version = None
        self._essential = False
        self._size = None
        self._installed = False
        self._upgradable = False

    def load(self, pack):
        c = pack.candidate
        self._full_name = pack.shortname
        self._comment = c.summary
        
        # Get the full icon path
        icon = theme.lookup_icon(self._name, icon_size, 0)
        if icon is None:
            self._icon_type = None
            icon = default_icon
        self._icon_path = icon.get_filename()

        self._version = c.version
        self._essential = pack.essential
        self._size = c.size
        self._installed = pack.is_installed
        self._upgradable = pack.is_upgradable

    def get_dict(self, load_icon=True):
        icon_data = None
        if load_icon and self._icon_path is not None:
            icon_data = "data:%s;base64," % mimetypes.guess_type(self._icon_path)[0]
            with open(self._icon_path, 'rb') as ld:
                icon_data += base64.encodestring(ld.read()).replace("\n", "")
        
        return {
            "name": self._name,
            "full_name": self._full_name,
            "comment": self._comment,
            "icon_type": self._icon_type,
            "icon": icon_data,
            "version": self._version,
            "essential": self._essential,
            "size": self._size,
            "installed": self._installed,
            "upgradable": self._upgradable
        }

    @staticmethod
    def reload_cache(websocket):
        log.info("Reloading cache")
        try:
            cche.open(None)
        except Exception as err:
            log.error("Failed to reload cache %s" % str(err))
            websocket.send_dict({
                "exec": "error",
                "message": "Failed to reload cache"
            })
        log.info("Done reloading cache")

    @staticmethod
    def search(name, websocket):
        try:
            if not check_internet():

            for p in cche.keys():
                if name in p:
                    if cche[p].candidate.downloadable:
                        p_add = Package(p)
                        p_add.load(cche[p])
                        websocket(p_add.get_dict())
            return None
        except Exception as err:
            log.error("Failed to search packages! (err: %s)" % str(err))
            return str(err)

    @staticmethod
    def install(name, websocket):
        try:
            if name not in cche:
                return "Package not found!"

            # Mark the package for install
            cche[name].mark_install(auto_fix=True, auto_inst=True, from_user=True)

            if not cche[name].marked_install or cche[name].is_installed:
                return "Package is already installed"


            websocket.send_dict({
                "exec": "aquire_start"
            })

            f_progress.set_socket(websocket)
            i_progress.set_socket(websocket, "install")
            cche.commit(f_progress, i_progress)
            return None
        except Exception as err:
            log.error("Failed to install package! (err: %s)" % str(err))
            return str(err)

    @staticmethod
    def delete(name, websocket, purge):
        try:
            if name not in cche:
                return "Package not found!"

            # Mark the package for install
            cche[name].mark_delete(auto_fix=True, purge=purge)

            if not cche[name].marked_delete or not cche[name].is_installed:
                return "Package is not installed"


            websocket.send_dict({
                "exec": "aquire_start"
            })

            f_progress.set_socket(websocket)
            i_progress.set_socket(websocket, "delete")
            cche.commit(f_progress, i_progress)
            return None
        except Exception as err:
            log.error("Failed to install package! (err: %s)" % str(err))
            return str(err)



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
            icon = default_icon
        self._icon_path = icon.get_filename()
        log.info("Found icon at %s (executable: %s)" % (self._icon_path, self._exec))

    def get_dict(self, load_icon=True):
        try:
            icon_type = splitext(basename(self._icon_path))[1][1:]
        except Exception as err:
            log.error("Failed to load icon type %s (err: %s)" % (load_icon, str(err)))
            icon_type = None

        icon_data = None
        if load_icon and self._icon_path is not None:
            icon_data = "data:%s;base64," % mimetypes.guess_type(self._icon_path)[0]
            with open(self._icon_path, 'rb') as ld:
                icon_data += base64.encodestring(ld.read()).replace("\n", "")
        return {
            "name": self._name,
            "full_name": self._full_name,
            "icon_type": icon_type, 
            "icon": icon_data,
            "exec": self._exec,
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
        
        # Update the hide list
        hide_list = []
        try:
            with open("%s/hide.list" % config_dir, 'r') as hl:
                hide_list = hl.read().split('\n')
        except Exception as err:
            log.error("Failed to load hide.list (err: %s)" % str(err))

        # Check the applications by name
        log.info("Skipping applications %s" % str(hide_list))
        d_files = [join(dirpath, f) for dirpath, dirnames, files in walk(applications_dir) for f in fnmatch.filter(files, "*.desktop")]
        app_list = []
        for d in d_files:
            name = splitext(basename(d))[0]
            if name in hide_list:
                continue
            log.info("Loading application %s" % name)
            app = Application(name)
            if app.load(d):
                app.fix()
                app_list.append(app)
        app_list = sorted(app_list, key=lambda x: x.get_name())
        log.info("Loaded a total of %d applications" % len(app_list))
