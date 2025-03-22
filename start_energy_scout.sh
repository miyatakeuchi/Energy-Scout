#!/bin/bash
echo "=== Script started === $(date)" >> /home/ben/energy_log.txt
cd /home/ben/Energy-Scout
echo "=== cded started === $(date)" >> /home/ben/energy_log.txt
git pull
echo "=== pulling === $(date)" >> /home/ben/energy_log.txt
/usr/bin/python3 main.py
echo "=== python mfers === $(date)" >> /home/ben/energy_log.txt
