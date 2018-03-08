from logger import Logger
from apps import Application
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
                for p in programs.items():
                    if p.get_port() == gen:
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
                    for p in programs.items():
                        if p.get_proxy_port() == gen:
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
        for i in range(0, 50):
            sleep(0.25)
            if self._proc.poll() is not None:
                if self._proc.returncode == 0:
                    log.info("Program started!")
                    started = True 
                else:
                    log.info("The program failed to start!")
                break
        if not started:
            log.error("Failed to start the program!")
        else:
            self._proxy_proc = sp.Popen(["websockify", "%d" % self._proxy_port, "localhost:%d" % self._port])
            started = False
            for i in range(0, 50):
                sleep(0.25)
                if self._proxy_proc.poll() is not None:
                    if self._proxy_proc.returncode == 0:
                        log.info("Proxy started!")
                        started = False
                    else:
                        log.info("The proxy failed to start!")
                    break
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
        log.info("New connection made")
        self.send_dict({"exec": "status", "status": True})

    def new_program(self, load):
        global programs
        n_id = str(uuid4())
        programs[n_id] = Program(load["name"])
        self.send_dict({
            "exec": "new",
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

    def __list_programs(self, apps):
        for app in apps:
            self.send_dict({
                "exec": "list",
                "apps": app.get_dict()
            })

    def list_programs(self, load):
        app_list = Application.get_app_list()
        thread.Thread(target=self.__list_programs, args=(app_list,)).start()

    def on_message(self, message):
        #try:
        data = loads(message)
        execs = {
            "new": self.new_program,
            "list": self.list_programs
        }
        execs[data["exec"]](data)
        #except Exception as err:
        #self.send_dict({"exec": "error", "message": str(err)})
 
    def on_close(self):
        log.info("Closed a connection")

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
