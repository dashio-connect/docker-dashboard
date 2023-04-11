
PWD=`pwd`
PYTHON=`which python3`
SERVICE_FILE=docker-dashboard.service
DEBUG=2
cat <<EOT > $SERVICE_FILE
[Unit]
Description=A python script for monitoring Docker containers to a DashIO Dashboard
After=syslog.target network.target

[Service]
WorkingDirectory=$PWD
ExecStart=$PYTHON $PWD/main.py -i $PWD/docker-dashboard.ini -l $PWD/docker-dashboard.log -v$DEBUG

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOT

if [ -f /etc/systemd/system/$SERVICE_FILE ]; then
    sudo systemctl stop $SERVICE_FILE
    sudo systemctl disable $SERVICE_FILE
else
    sudo \cp -f ./$SERVICE_FILE /etc/systemd/system/$SERVICE_FILE
fi

sudo systemctl enable $SERVICE_FILE
sudo systemctl start $SERVICE_FILE
