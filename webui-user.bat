@echo off

set PYTHON=
set GIT=
set VENV_DIR=
set COMMANDLINE_ARGS=--listen --port 7860 --xformers --opt-split-attention --medvram

call webui.bat
