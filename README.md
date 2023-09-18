# docker-dashboard

![Tests](https://github.com/jboulton/docker-dashboard/actions/workflows/tests.yml/badge.svg)
A python script for monitoring Docker containers to a DashIO Dashboard

## Requirements

- A linux server running docker continers.
- The DashIO app and an [account]("https://dashio.io/account-create/) with DashIO.
- The DashIO library installed on your Raspberry Pi. You can install it using pip:

  ```shell
  pip install dashio
  ```

- The DashIO app available here:

Apple              | Android
:-----------------:|:------------------:
[<img src=https://raw.githubusercontent.com/dashio-connect/python-dashio/master/Documents/download-on-the-app-store.svg width=200>](<https://apps.apple.com/us/app/dash-iot/id1574116689>) | [<img src=https://raw.githubusercontent.com/dashio-connect/python-dashio/master/Documents/Google_Play_Store_badge_EN.svg width=223>](<https://play.google.com/store/apps/details?id=com.dashio.dashiodashboard>)

## Install

```sh
git clone https://github.com/jboulton/docker-dashboard.git
cd docker-dashboard
sudo ./install.sh
```

Edit `docker-dashboard/docker-dashboard.ini` and replace the username and password with your username and password for your DashIO server account.

```sh
sudo systemctl restart docker-dashboard.service
```
