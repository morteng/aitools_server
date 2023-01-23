echo Running server with --enable-insecure-extension-access parm so I can install extensions remotely on my lan, don't do this unless you know what you're doing
venv_dir="-" CUDA_VISIBLE_DEVICES=0 python launch.py --listen --port 7860 --api --xformers --enable-insecure-extension-access
