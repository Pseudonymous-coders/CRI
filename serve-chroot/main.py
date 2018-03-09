# -*- coding: utf-8 -*-
"""CRI main file

This module is the core of the CRI interface as it handles all of the virtual displays, vnc,
app downloading, updating, removing, and more. This module specifically contains the program (vnc),
and websocket server handlers.

Developed By: David Smerkous and Eli Smith
"""

from logger import Logger
from apps import Application, Package
from distutils.spawn import find_executable
from tornado import ioloop, httpserver, web, websocket
from random import randint
from time import sleep
from os import chmod
from json import loads, dumps
from uuid import uuid4
import subprocess as sp
import threading as thread

# Configs
server_port = 3300 # The starting port
display_port = 3310 # The starting display ports
max_displays = 100 # The maximum amount of allowed displays
display_offset = 10 # The display displacement amount (to not conflict with other programs)
end_displays = display_port + max_displays
proxy_ports = display_port + max_displays
end_proxy_ports = proxy_ports + max_displays
base_vnc = "vncserver"
grep_vnc = "vnc"
start_up = "/tmp"

# Logs
log = Logger("CRI")

# Globally locked variables
programs = {}
connections = set()
master = None
instances = 0

# Program instance handler
class Program(object):
    def __init__(self, name):
        global available_displays
        self._name = name
        created = False

        # Check for an available display port
        for d in range(display_port, end_displays):
            try:
                is_in = False
                for p in programs.values():
                    if p.get_port() == d:
                        is_in = True
                        break
                if not is_in:
                    created = True
                    self._port = d
                    break
            except:
                pass
        
        if created:
            # Check fo an available proxy port
            for d in range(proxy_ports, end_proxy_ports):
                try:
                    is_in = False
                    for p in programs.values():
                        if p.get_proxy_port() == d:
                            is_in = True
                            break
                    if not is_in:
                        created = True
                        self._proxy_port = d
                        break
                except:
                    pass

        # Log the unusable display error
        if not created:
            log.warning("Possibly ran out of usable displays")
            log.error("Unknown usage at this point")
            self._port = end_displays
            self._proxy_port = end_proxy_ports
        self._display_num = (self._port - display_port) + display_offset
        
        # Declare the blank subprocess
        self._proc = None
        self._proxy_proc = None

    def get_name(self):
        return self._name

    def get_port(self):
        return self._port
    
    def get_proxy_port(self):
        return self._proxy_port

    def run(self):
        if self._proc is not None or self._proxy_proc:
            log.error("The program %s is already running!" % self._name)
            return
        Program.create_startup(self._name)
        self._proc = sp.Popen([base_vnc, (":%d" % self._display_num),
            "-name", ("'%s'" % self._name), "-AcceptCutText=1", 
            "-SendCutText=1", "-localhost=1", "-SecurityTypes=None", 
            "-rfbport", ("%d" % self._port), "-ZlibLevel=0",
            "-xstartup", ("'%s'" % Program.start_up_name(self._name))]) 
            #stdout=sp.PIPE, stderr=sp.PIPE)
        log.info("Waiting for the program to start")
        started = False
        for i in range(0, 100):
            if self._proc.poll() is not None:
                if self._proc.returncode == 0:
                    log.info("Program started!")
                    started = True 
                else:
                    log.info("The program failed to start!")
                break
            sleep(0.1)
        if not started:
            log.error("Failed to start the program!")
        else:
            self._proxy_proc = sp.Popen(["websockify", "%d" % self._proxy_port, "localhost:%d" % self._port])
            started = False
            for i in range(0, 100):
                proc = sp.Popen(["pgrep", "websockify"], stdout=sp.PIPE)
                data = proc.communicate()[0]
                rc = proc.returncode
                if rc == 0:
                    log.info("Proxy started!")
                    started = True
                    break
                sleep(0.1)
            if not started:
                log.error("The proxy failed to start!")
            log.info("Starting %s on port %d and proxied with websocket to port %d" % (self._name, self._port, self._proxy_port))

    def kill(self):
        if self._proc is None and self._proxy_proc is None:
            log.error("The program %s is not running!" % self._name)
        try:
            log.info("Attempting to kill %s" % self._name)
            proc = sp.Popen([base_vnc, "-kill", (":%d" % self._display_num)], stdout=sp.PIPE)
            proc.wait()
            log.info("Killed display :%d" % self._display_num)
            try:
                self._proc.kill()
            except Exception as err:
                log.warning("Couldn't clean up process via pid... %s" % str(err)) 
            self._proxy_proc.kill()
        except Exception as err:
            log.error("Failed to kill %s (err: %s)" % (self._name, str(err)))

    @staticmethod
    def start_up_name(name):
        return "%s/%s.cri_startup" % (start_up, name)

    @staticmethod
    def create_startup(name):
        try:
            log.info("Creating xstartup file... %s" % name)
            f_write = open(Program.start_up_name(name), "w")
            f_write.writelines([
                "#!/bin/sh\n",
                "xrdb $HOME/.Xresources\n",
                "xsetroot -solid grey\n",
                "xsetroot -cursor_name left_ptr\n",
                "i3 -c /etc/i3.conf &\n",
                ("%s\n" % name)
                ])
            f_write.close()
            chmod(Program.start_up_name(name), 777)
            log.info("Finished creating startup file!")
        except:
            log.error("Failed to create the xstartup file!")

    @staticmethod
    def kill_all():
        t_inst = Program.get_instances()
        if t_inst > 0:
            for d in range(0, t_inst):
                d_num = display_offset + d
                proc = sp.Popen([base_vnc, "-kill", (":%d" % d_num)], stdout=sp.PIPE)
                proc.wait()
                log.info("Killing display :%d" % d_num)
                if proc.returncode == 1:
                    log.error("Failed to kill the display!")
        proc = sp.Popen(["pkill", "-15", grep_vnc], stdout=sp.PIPE)
        proc_proxy = sp.Popen(["pkill", "-15", "websockify"], stdout=sp.PIPE)
        proc.poll()
        proc_proxy.poll()

    @staticmethod
    def get_instances():
        global instances
        proc = sp.Popen(["pgrep", grep_vnc], stdout=sp.PIPE)
        data = proc.communicate()[0]
        rc = proc.returncode
        if rc == 1:
            log.info("No instances are running!")
            instances = 0
        else:
            log.info("Instance return %s" % data)
            instances = len(data.split("\n")) - 1
        log.info("Running instances %d" % instances)
        return instances


# Websocket handler
class CRI(websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True
 
    def send_dict(self, dictionary):
        self.write_message(dumps(dictionary))

    def open(self):
        global connections, master
        log.info("Connected with %s" % self.request.remote_ip)
        connections.add(self) # Add myself to the connection list

        # Respond with a positive status
        self.send_dict({"exec": "status", "status": True})

        # Check to see if this connection can be a master
        if master is None:
            self.send_dict({"exec": "master"})

    def run_program(self, load):
        global programs, master
        if master is None:
            log.error("Trying to run program with no master connection!")
            self.send_dict({"exec": "error", "message": "No master connection (No connection that can make windows)!"})
            return

        # Check to make sure the executable exists
        check_p = load["name"]
        if " " in check_p:
            check_p = check_p.split(" ")[0] # Get the first argument
        
        if find_executable(check_p) is None:
            log.error("Couldn't find executable %s" % check_p)
            self.send_dict({"exec": "error", "message": "The executable %s doesn't exist or isn't in the PATH env variable" % check_p})
            return

        n_id = str(uuid4())
        programs[n_id] = Program(load["name"])
        self.send_dict({
            "exec": "run",
            "name": load["name"],
            "uuid": n_id,
            "port": programs[n_id].get_proxy_port()
        })
        programs[n_id].run()
        self.send_dict({
            "exec": "load",
            "name": load["name"],
            "uuid": n_id
        })

    def set_master(self, load):
        global master
        if load["status"]:
            log.info("Setting master to %s" % self.request.remote_ip)
            master = self
        else:
            log.info("Master status declined by %s" % self.request.remote_ip)
            self.check_master()
        self.send_dict({
            "exec": "set_master",
            "status": load["status"]
        })
        log.info("The master has been set!")

    def get_master(self, load):
        global master
        log.info("Getting master information for %s" % self.request.remote_ip)
        self.send_dict({
            "exec": "get_master",
            "status": (False if master is None else True)
        })

    def __list_programs(self, apps):
        for app in apps:
            self.send_dict({
                "exec": "list",
                "app": app.get_dict()
            })
        self.send_dict({
            "exec": "list_done"
        })

    def list_programs(self, load):
        app_list = Application.get_app_list()
        thread.Thread(target=self.__list_programs, args=(app_list,)).start()

    def __search_packages(self, name):
        status = Package.search(name, lambda d: self.send_dict({
            "exec": "search",
            "package": d
        }))

        if status is None:
            self.send_dict({
                "exec": "search_done"
            })
        else:
            self.send_dict({
                "exec": "error",
                "message": status
            })

    def search_packages(self, load):
        log.info("Searching for package %s" % load["search"])
        thread.Thread(target=self.__search_packages, args=(load["search"],)).start()

    def __install_package(self, name):
        status = Package.install(name, self)
        if status is not None:
            self.send_dict({
                "exec": "error",
                "message": status
            })
        log.info("Loading the new app list")
        Application.load_app_list()
        Package.reload_cache(self)

    def install_package(self, load):
        log.info("Installing packages %s" % load["install"])
        thread.Thread(target=self.__install_package, args=(load["install"],)).start()

    def __delete_package(self, name, purge):
        status = Package.delete(name, self, purge)
        if status is not None:
            self.send_dict({
                "exec": "error",
                "message": status
            })
        log.info("Loading the new app list")
        Application.load_app_list()
        Package.reload_cache(self)

    def delete_package(self, load):
        log.info("Deleting packages %s" % load["delete"])
        thread.Thread(target=self.__delete_package, args=(load["delete"], load["purge"])).start()

    def kill_program(self, load):
        global programs
        status = True
        try:
            if load["uuid"] not in programs:
                self.send_dict({"exec": "error", "message": "Program doesn't exist"})
                return
            log.info("Killing program %s" % programs[load["uuid"]].get_name())

            # Kill the program
            programs[load["uuid"]].kill()

            # Delete the program element
            del programs[load["uuid"]]

            log.info("Killed the program!")
        except Exception as err:
            log.error("Failed to kill the program (err: %s)" % str(err))

        self.send_dict({"exec": "kill", "status": status})

    def check_master(self):
        global programs, master
        if master is None:
            log.info("There are no more connections left! Killing all programs...")
            for p in programs.values():
                try:
                    p.kill()
                except Exception as err:
                    log.error("Failed to kill program (err: %s)" % str(err))
            programs = {}
            log.info("Done")

    def on_message(self, message):
        #try:
        data = loads(message)
        execs = {
            "set_master": self.set_master,
            "get_master": self.get_master,
            "run": self.run_program,
            "kill": self.kill_program,
            "list": self.list_programs,
            "search": self.search_packages,
            "install": self.install_package,
            "delete": self.delete_package
        }
        execs[data["exec"]](data)
        #except Exception as err:
        #self.send_dict({"exec": "error", "message": str(err)})
 
    def on_close(self):
        global programs, connections, master
        log.info("Disconnecting...")

        if master == self:
            log.warning("Removing the master connection!")
            master = None

        # Remove this connection from the list before requesting another master connection
        connections.remove(self)

        if master is None and len(connections) == 0:
            self.check_master()
        elif master is None:
            # Request another master connection
            log.info("Asking other connections if they want to be master")
            for c in connections:
                c.send_dict({"exec": "master"}) # Request if the other connections can be the master connection
        log.info("Disconnected with %s" % self.request.remote_ip)

def main():
    log.info("Starting CRI...")
    log.info("Developed by David Smerkous and Eli Smith")

    log.info("Killing all current instances...")
    Program.kill_all()
    log.info("Done")

    log.info("Loading all available apps...")
    Application.load_app_list()

    log.info("Starting websocket server")
    service = web.Application([(r'/', CRI),])
    listenr = httpserver.HTTPServer(service)
    listenr.listen(server_port)
    ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        log.error("Exiting... %s" % str(err))
        Program.kill_all()
