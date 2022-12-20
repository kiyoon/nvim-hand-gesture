```bash
# First, test the gesture demo
docker run --gpus all --rm -it --device=/dev/video1:/dev/video0 -e DISPLAY=${DISPLAY} -v /tmp/.X11-unix:/tmp/.X11-unix -v ~/project/nvim-hand-gesture:/workspace kiyoon/nvim-hand-gesture

# With neovim integration
docker run --gpus all --rm -it --device=/dev/video1:/dev/video0 -e DISPLAY=${DISPLAY} -v /tmp/.X11-unix:/tmp/.X11-unix -v ~/project/nvim-hand-gesture:/workspace -v /run/user:/run/user kiyoon/nvim-hand-gesture --socket_path /run/user/1000/nvim.1708692.0
```
