# Hand Gesture for Neovim

Use your webcam to unlock hand gesture recognition to control Neovim!

<img src="https://user-images.githubusercontent.com/12980409/209009889-94513f97-2cdd-4fd7-9d0f-5874b944b8e8.gif" width="100%"/>

Highly experimental. Is it practical? Maybe not, but some use cases are not bad. Should you try it? Why not, it's fun!

Highly customisable. Just change the lua scripts to your own custom commands!  
The demo uses [GitHub Copilot](https://github.com/github/copilot.vim) (AI code suggestion), [Nvim-Tree](https://github.com/nvim-tree/nvim-tree.lua) (file explorer), and [nvim-treesitter-textobjects](https://github.com/nvim-treesitter/nvim-treesitter-textobjects) (peep function definition).

## Prerequisites


You need an Nvidia GPU on a Linux computer. I tested with Ubuntu 22.04, GTX 1080 Ti and RTX 3060. The Nvidia driver has to support CUDA 11.3 (see `nvidia-smi` command).  
I'm sorry, no Windows or Mac support as of yet.

## Installation
This plugin depends on a number of softwares so there's no easy way to install using plugin managers.  
The easiest way to get started is using Docker.

You need to install [Nvidia-docker](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html). From their official guide,  

```bash
curl https://get.docker.com | sh \
  && sudo systemctl --now enable docker

distribution=$(. /etc/os-release;echo $ID$VERSION_ID) \
      && curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
      && curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

### Pull the repo and the docker container.  
Warning: this will download around 7GB. This program has many dependencies that makes it huge.

```bash
git clone https://github.com/kiyoon/nvim-hand-gesture
docker pull kiyoon/nvim-hand-gesture
```

### Before testing with Neovim, see if the program works.


```bash
# You may need to change the variables
WEBCAM=/dev/video0
REPO_PATH=~/nvim-hand-gesture
docker run --gpus all --rm -it \
    --device=$WEBCAM:/dev/video0 \
    -v "$REPO_PATH":/workspace kiyoon/nvim-hand-gesture
```

To enable the GUI demo,
```bash
xhost +local:docker
docker run --gpus all --rm -it \
    --device=$WEBCAM:/dev/video0 \
    -e DISPLAY=${DISPLAY} -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v "$REPO_PATH":/workspace kiyoon/nvim-hand-gesture --gui
```

### Once you saw it working, make vim bindings.

```vim
" With GUI demo
nmap <leader>G <Cmd>call system("docker run --gpus all --rm --device=/dev/video0:/dev/video0 -e DISPLAY=${DISPLAY} -v /tmp/.X11-unix:/tmp/.X11-unix -v ~/project/nvim-hand-gesture:/workspace -v /run/user:/run/user kiyoon/nvim-hand-gesture --gui --nvim_socket_path " . v:servername . " &")<CR>
" Without GUI
nmap <leader>g <Cmd>call system("docker run --gpus all --rm --device=/dev/video0:/dev/video0 -v ~/project/nvim-hand-gesture:/workspace -v /run/user:/run/user kiyoon/nvim-hand-gesture --nvim_socket_path " . v:servername . " &")<CR>
" Quit running process
nmap <leader><leader>g <Cmd>let g:quit_nvim_hand_gesture = 1<CR>
```

Note that you need to remove `-it` option, and may change the webcam device and nvim-hand-gesture repo path to the correct one.  
`-v /run/user` mount is because Neovim's `v:servername` is usually `/run/user/$USER/nvim.$pid.0`. It may depend on the system.  

## Customisation

Change lua files in [gesture_mappings](./gesture_mappings) to your likings. If the action is in [persistent_gestures.txt](./persistent_gestures.txt), the lua script will keep being executed until you stop that action. If not, it will only be executed once and be ignored for the rest of the duration.

### Setup tips

You may not want to make a gesture command intrusive to your original neovim workflow. To make it as practical as possible, try to avoid moving your cursor or amending text.

Instead, some example use cases include:  
- Opening / closing a side bar (e.g. nvim-tree) without focussing on it
- Opening a floating window (e.g. peek function definition).
- Adjusting size of splits

I'd be happy if anyone shares their own use cases and good sets of defaults!


## Acknowledgement

This is a porting of [TSM demo](https://github.com/mit-han-lab/temporal-shift-module/tree/master/online_demo) in order to use it to control Neovim.
