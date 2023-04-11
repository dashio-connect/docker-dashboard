# docker-dashboard

![Tests](https://github.com/jboulton/docker-dashboard/actions/workflows/tests.yml/badge.svg)
A python script for monitoring Docker containers to a DashIO Dashboard

## Requirements

A linux server running docker conatiners. The DashIO app and an account with DashIO.

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
