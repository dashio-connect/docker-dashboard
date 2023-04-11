import argparse
import logging
import signal
import dashio
import docker
import time
import configparser
import shortuuid


class SignalHandler:
    shutdown_requested = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.request_shutdown)
        signal.signal(signal.SIGTERM, self.request_shutdown)

    def request_shutdown(self, *args):
        logging.debug('Request to shutdown received, stopping')
        self.shutdown_requested = True

    def can_run(self):
        return not self.shutdown_requested


class DockerDashboard:
    def signal_cntrl_c(self, os_signal, os_frame):
        self.shutdown = True

    def init_logging(self, logfilename, level):
        log_level = logging.WARN
        if level == 1:
            log_level = logging.INFO
        elif level == 2:
            log_level = logging.DEBUG
        if not logfilename:
            formatter = logging.Formatter("%(asctime)s, %(message)s")
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logger = logging.getLogger()
            logger.addHandler(handler)
            logger.setLevel(log_level)
        else:
            logging.basicConfig(
                filename=logfilename,
                level=log_level,
                format="%(asctime)s, %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        logging.info("==== Started ====")

    def parse_commandline_arguments(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "-v",
            "--verbose",
            const=1,
            default=1,
            type=int,
            nargs="?",
            help="""increase verbosity:
                            0 = only warnings, 1 = info, 2 = debug.
                            No number means info. Default is no verbosity.""",
        )
        parser.add_argument("-x", "--version", dest="version", default="1.0", help="Service vervion")
        parser.add_argument("-l", "--logfile", dest="logfilename", default="", help="logfile location", metavar="FILE")
        parser.add_argument("-i", "--inifile", dest="inifilename", default="docker-dashboard.ini", help="ini location", metavar="FILE")
        args = parser.parse_args()
        return args

    def __init__(self):

        # Catch CNTRL-C signel

        signal_handler = SignalHandler()

        args = self.parse_commandline_arguments()
        self.init_logging(args.logfilename, args.verbose)

        new_ini_file = False
        ini_file = args.inifilename
        config_file_parser = configparser.ConfigParser()
        config_file_parser.defaults()

        try:
            ini_f = open(ini_file)
            ini_f.close()
        except FileNotFoundError:
            dashio_dict = {
                'DeviceID': shortuuid.uuid(),
                'DeviceName': 'Docker Dashboard',
                'username': 'username',
                'password': 'password'
            }
            config_file_parser['DashIO'] = dashio_dict
            with open(ini_file, 'w') as configfile:
                config_file_parser.write(configfile)
            new_ini_file = True

        if not new_ini_file:
            config_file_parser.read(ini_file)

        logging.info("    Device ID: %s", config_file_parser.get('DashIO', 'DeviceID'))
        logging.info("  Device Name: %s", config_file_parser.get('DashIO', 'DeviceName'))

        self.docker_client = docker.from_env()
        self.container_list = self.docker_client.containers.list()
        logging.debug("Container List: %s", self.container_list)
        
        self.device = dashio.Device(
            "DockerDashboard",
            config_file_parser.get('DashIO', 'DeviceID'),
            config_file_parser.get('DashIO', 'DeviceName')
        )
        self.device.use_cfg64()

        self.dash_con = dashio.DashConnection(
            config_file_parser.get('DashIO', 'username'),
            config_file_parser.get('DashIO', 'password')
        )

        self.dash_con.add_device(self.device)
        self.device.config_revision = 1
        while signal_handler.can_run():
            time.sleep(1)

        self.dash_con.close()
        self.device.close()


if __name__ == "__main__":
    DockerDashboard()
