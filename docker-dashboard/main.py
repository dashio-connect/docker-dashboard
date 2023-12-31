import argparse
import logging
import signal
import dashio
import docker
import time
import configparser
import shortuuid
import re
import zmq
import threading
import datetime


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

def to_nicer_str(text: str) -> str:
    camel_string = " ".join(x.capitalize() for x in re.split("_|-", text.lower()))
    return camel_string


class LogMonitorThread(threading.Thread):

    def close(self):
        """Close the thread"""
        self.running = False

    def __init__(self, conatiner, zmq_url: str, context: zmq.Context) -> None:
        threading.Thread.__init__(self, daemon=True)
        self.context = context

        self.running = True
        self.container = conatiner

        self.task_sender = self.context.socket(zmq.PUSH)
        self.task_sender.connect(zmq_url)

        self.start()

    def run(self):
        while self.running:
            try:
                if self.container.status == "running":
                    for log in self.container.logs(stream=True, follow=True, timestamps=True, since=datetime.datetime.utcnow()):
                        logging.debug("LOG: %s", log)
                        log_str = log.decode('utf-8').strip()
                        self.task_sender.send_multipart([b'LOG', log_str.encode()])
                time.sleep(1.0)
            except Exception as e:
                logging.debug(f"An error occurred: {str(e)}")
        self.task_sender.close()


class TimerThread(threading.Thread):

    def close(self):
        """Close the thread"""
        self.running = False

    def __init__(self, duration: float, zmq_url: str, context: zmq.Context) -> None:
        threading.Thread.__init__(self, daemon=True)
        self.context = context
        self.duration = duration
        self.running = True
        self.task_sender = self.context.socket(zmq.PUSH)
        self.task_sender.connect(zmq_url)

        self.start()

    def run(self):
        while self.running:
            time.sleep(self.duration)
            self.task_sender.send_multipart([b'TIMER', str(self.duration).encode()])

        self.task_sender.close()

class DockerDashboard:

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

    def update_container_controls(self, index: int):
        self.container_list_index = index
        current_container = self.container_list[index]
        self.cont_name_txbx.text = to_nicer_str(current_container.name)
        if current_container.status == "running":
            self.start_stop_button.send_button(dashio.ButtonState.OFF, dashio.Icon.STOP, "Stop")
        else:
            self.start_stop_button.send_button(dashio.ButtonState.ON, dashio.Icon.PLAY, "Start")

    def container_selection(self, rx_msg):
        logging.debug("Selector RX: %s", rx_msg)
        try:
            c_index = int(rx_msg[3])
        except (ValueError, IndexError):
            return
        self.c_select.position = c_index
        self.update_container_controls(c_index)
        self.cont_logs.close()
        self.cont_logs = LogMonitorThread(self.container_list[self.container_list_index], self.zmq_url, self.context)

    def start_stop_rx(self, rx_msg):
        logging.debug("Start Stop Btn RX: %s", rx_msg)
        container = self.container_list[self.container_list_index]
        if container.status == "running":
            container.stop()
            self.start_stop_button.send_button(dashio.ButtonState.ON, dashio.Icon.PLAY, "Start")
        else:
            container.start()
            self.start_stop_button.send_button(dashio.ButtonState.OFF, dashio.Icon.STOP, "Stop")

    def restart_rx(self, rx_msg):
        logging.debug("Restart Btn RX: %s", rx_msg)
        container = self.container_list[self.container_list_index]
        container.restart()

    def rescan_rx(self, rx_msg):
        logging.debug("Rescan Btn RX: %s", rx_msg)
        self.get_container_list()

    def update_selector_list(self):
        # self.c_select.selection_list.clear()
        send_select = False
        for container in self.container_list:
            cont_name = to_nicer_str(container.name)
            running_cont_name = "✅: " + cont_name
            exited_cont_name = "❌: " + cont_name
            if container.status == "running":
                cont_name = running_cont_name
            else:
                cont_name = exited_cont_name
            if running_cont_name not in self.c_select.selection_list and exited_cont_name not in self.c_select.selection_list:
                self.c_select.add_selection(cont_name)
                send_select = True
        if send_select:
            self.c_select.send_selection(self.container_list_index)

    def get_container_list(self):
        self.container_list = self.docker_client.containers.list(all=True)
        self.update_selector_list()
        if self.container_list[self.container_list_index].name not in self.c_select.selection_list:
            self.update_container_controls(0)

    def __init__(self):

        # Catch CNTRL-C signel
        signal_handler = SignalHandler()
        #  Socket to receive messages on
        self.zmq_url = "inproc://log_push_pull"
        self.context = zmq.Context.instance()
        task_receiver = self.context.socket(zmq.PULL)
        task_receiver.bind(self.zmq_url)
        self.timer = TimerThread(10.0, self.zmq_url, self.context)
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

        device_id = config_file_parser.get('DashIO', 'DeviceID')
        device_name = config_file_parser.get('DashIO', 'DeviceName')
        logging.info("    Device ID: %s", device_id)
        logging.info("  Device Name: %s", device_name)

        self.docker_client = docker.from_env()
        self.container_list_index = 0
        d_view = dashio.DeviceView("dv1", device_name)

        self.device = dashio.Device(
            "DockerDashboard",
            device_id,
            device_name,
            context=self.context
        )
        self.device.use_cfg64()
        self.device.add_control(d_view)
        self.device.config_revision = 2

        self.c_select = dashio.Selector(
            "cs1",
            "Container",
            control_position=dashio.ControlPosition(0.0, 0.84375, 0.7727272727272, 0.15625),
            title_position=dashio.TitlePosition.NONE
        )
        d_view.add_control(self.c_select)
        self.device.add_control(self.c_select)

        self.dash_con = dashio.DashConnection(
            config_file_parser.get('DashIO', 'username'),
            config_file_parser.get('DashIO', 'password')
        )

        self.c_select.add_receive_message_callback(self.container_selection)
        self.dash_con.add_device(self.device)

        self.log_txbx = dashio.TextBox(
            "logTextBox",
            "Container Log",
            text_format=dashio.TextFormat.LOG,
            title_position=dashio.TitlePosition.TOP,
            text_align=dashio.TextAlignment.LEFT,
            keyboard_type=dashio.Keyboard.NONE,
            control_position=dashio.ControlPosition(0.0, 0.0, 1.0, 0.84375)
        )
        self.log_txbx.color = dashio.Color.ALICE_BLUE
        d_view.add_control(self.log_txbx)
        self.device.add_control(self.log_txbx)

        self.controls_menu = dashio.Menu(
            "controls_mnu1",
            "Container Controls",
            text="",
            title_position=dashio.TitlePosition.NONE,
            control_position=dashio.ControlPosition(0.7727272727272, 0.84375, 0.227272727272727, 0.15625)
        )
        d_view.add_control(self.controls_menu)
        self.device.add_control(self.controls_menu)

        self.start_stop_button = dashio.Button(
            "5_startStopBtn",
            "startstop",
            text="",
            title_position=dashio.TitlePosition.NONE,
            icon_name=dashio.Icon.PLAY,
            on_color=dashio.Color.SEA_GREEN,
            off_color=dashio.Color.RED
        )
        self.controls_menu.add_control(self.start_stop_button)
        self.device.add_control(self.start_stop_button)
        self.start_stop_button.add_receive_message_callback(self.start_stop_rx)

        self.restart_button = dashio.Button(
            "4_restartBtn",
            "Restart",
            icon_name=dashio.Icon.REFRESH,
            on_color=dashio.Color.FIREBRICK,
            off_color=dashio.Color.FIREBRICK
        )
        self.controls_menu.add_control(self.restart_button)
        self.device.add_control(self.restart_button)
        self.restart_button.add_receive_message_callback(self.restart_rx)

        self.cont_name_txbx = dashio.TextBox(
            "3_contNameTxtBx",
            "",
            text_align=dashio.TextAlignment.CENTER,
            keyboard_type=dashio.Keyboard.NONE
        )
        self.controls_menu.add_control(self.cont_name_txbx)
        self.device.add_control(self.cont_name_txbx)

        self.rescan_containers_button = dashio.Button(
            "2_rescanBtn",
            "Rescan Containers",
            icon_name=dashio.Icon.COG,
            on_color=dashio.Color.DARK_GOLDEN_ROD,
            off_color=dashio.Color.DARK_GOLDEN_ROD
        )
        self.controls_menu.add_control(self.rescan_containers_button)
        self.device.add_control(self.rescan_containers_button)
        self.rescan_containers_button.add_receive_message_callback(self.rescan_rx)

        self.get_container_list()
        self.device.config_revision = 1

        self.cont_logs = LogMonitorThread(self.container_list[self.container_list_index], self.zmq_url, self.context)

        poller = zmq.Poller()
        poller.register(task_receiver, zmq.POLLIN)

        while signal_handler.can_run():
            try:
                socks = dict(poller.poll(20))
            except zmq.error.ContextTerminated:
                break
            if task_receiver in socks:
                msg_from, msg = task_receiver.recv_multipart()
                if msg_from == b'LOG':
                    # this should be a different control
                    lines = msg.decode().split('\n')
                    for line in lines:
                        self.log_txbx.text = line
                if msg_from == b'TIMER':
                    self.update_selector_list()

        self.dash_con.close()
        self.device.close()


if __name__ == "__main__":
    DockerDashboard()
