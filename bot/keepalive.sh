#!/bin/bash
# keepalive.sh — поднимает бота, если он умер.
# На PythonAnywhere поставьте этот скрипт в Scheduled Tasks (каждый час):
# даже после еженедельной перезагрузки сервера бот вернётся в строй сам.
#
# ЗАМЕНИТЕ YOURNAME на ваш логин PythonAnywhere.

DIR="/home/YOURNAME/1abeilnossttt/bot"

cd "$DIR" || exit 1

if ! pgrep -f "python.*main\.py" > /dev/null; then
    nohup python main.py >> bot.log 2>&1 &
    echo "бот перезапущен" >> bot.log
else
    echo "бот уже работает"
fi
