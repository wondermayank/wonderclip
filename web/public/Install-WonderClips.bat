@echo off
title Installing Wonder Clips
echo.
echo  Installing Wonder Clips on this computer. This takes about 5-15 minutes
echo  and downloads about 4 GB. Please keep this window open.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/wondermayank/wonderclip/main/engine/install.ps1 | iex"
echo.
pause
