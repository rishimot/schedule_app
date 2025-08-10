#/bin/bash

VENV_PATH="/home/s145053/develop/schedule_app/.venv/bin"
$VENV_PATH/pip install gunicorn

cat << EOF > /etc/systemd/system/schedule.service
[Unit]
Description=Gunicorn instance to serve schedule_app
After=network.target

[Service]
User=s145053
Group=www-data
WorkingDirectory=/home/s145053/develop/schedule_app/
Environment="PATH=/home/s145053/develop/schedule_app/.venv/bin"
ExecStart=/home/s145053/develop/schedule_app/.venv/bin/gunicorn --workers 3 --bind 0.0.0.0:5004 -m 007 app:app

[Install]
WantedBy=multi-user.target
EOF
sudo ufw allow 5004
sudo systemctl daemon-reload
sudo systemctl enable schedule
sudo systemctl start schedule
