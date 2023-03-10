import argparse
import io
import os
import time
from typing import Tuple

from PIL import Image, ImageOps
import numpy as np
import pynvim

import cv2
from mobilenet_v2_tsm import MobileNetV2
import onnx
import torch
import torch.onnx
import torchvision
import tvm
import tvm.contrib.graph_runtime as graph_runtime
import tvm.relay

def get_parser():
    parser = argparse.ArgumentParser(description="Control Neovim using hand gestures",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--nvim_socket_path", help="Use --listen on nvim to specify nvim's socket path, and pass the same to here.")
    parser.add_argument("--headless", action='store_true', help="Do not open window for visualisation.")
    return parser

SOFTMAX_THRES = 0
HISTORY_LOGIT = True
REFINE_OUTPUT = True

def torch2tvm_module(torch_module: torch.nn.Module, torch_inputs: Tuple[torch.Tensor, ...], target):
    torch_module.eval()
    input_names = []
    input_shapes = {}
    with torch.no_grad():
        for index, torch_input in enumerate(torch_inputs):
            name = "i" + str(index)
            input_names.append(name)
            input_shapes[name] = torch_input.shape
        buffer = io.BytesIO()
        torch.onnx.export(torch_module, torch_inputs, buffer, input_names=input_names, output_names=["o" + str(i) for i in range(len(torch_inputs))], opset_version=10)
        outs = torch_module(*torch_inputs)
        buffer.seek(0, 0)
        onnx_model = onnx.load_model(buffer)
        from onnxsim import simplify
        onnx_model, success = simplify(onnx_model)  # this simplifier removes conversion bugs.
        assert success
        relay_module, params = tvm.relay.frontend.from_onnx(onnx_model, shape=input_shapes)
    with tvm.relay.build_config(opt_level=3):
        graph, tvm_module, params = tvm.relay.build(relay_module, target, params=params)
    return graph, tvm_module, params


def torch2executor(torch_module: torch.nn.Module, torch_inputs: Tuple[torch.Tensor, ...], target):
    prefix = f"mobilenet_tsm_tvm_{target}"
    lib_fname = f'{prefix}.tar'
    graph_fname = f'{prefix}.json'
    params_fname = f'{prefix}.params'
    if os.path.exists(lib_fname) and os.path.exists(graph_fname) and os.path.exists(params_fname):
        with open(graph_fname, 'rt') as f:
            graph = f.read()
        tvm_module = tvm.module.load(lib_fname)
        params = tvm.relay.load_param_dict(bytearray(open(params_fname, 'rb').read()))
    else:
        graph, tvm_module, params = torch2tvm_module(torch_module, torch_inputs, target)
        tvm_module.export_library(lib_fname)
        with open(graph_fname, 'wt') as f:
            f.write(graph)
        with open(params_fname, 'wb') as f:
            f.write(tvm.relay.save_param_dict(params))

    ctx = tvm.gpu() if target.startswith('cuda') else tvm.cpu()
    graph_module = graph_runtime.create(graph, tvm_module, ctx)
    for pname, pvalue in params.items():
        graph_module.set_input(pname, pvalue)

    def executor(inputs: Tuple[tvm.nd.NDArray]):
        for index, value in enumerate(inputs):
            graph_module.set_input(index, value)
        graph_module.run()
        return tuple(graph_module.get_output(index) for index in range(len(inputs)))

    return executor, ctx


def get_executor(use_gpu=True):
    torch_module = MobileNetV2(n_class=27)
    if not os.path.exists("/mobilenetv2_jester_online.pth.tar"):  # checkpoint not downloaded
        print('Downloading PyTorch checkpoint...')
        import urllib.request
        url = 'https://hanlab.mit.edu/projects/tsm/models/mobilenetv2_jester_online.pth.tar'
        urllib.request.urlretrieve(url, '/mobilenetv2_jester_online.pth.tar')
    torch_module.load_state_dict(torch.load("/mobilenetv2_jester_online.pth.tar"))
    torch_inputs = (torch.rand(1, 3, 224, 224),
                    torch.zeros([1, 3, 56, 56]),
                    torch.zeros([1, 4, 28, 28]),
                    torch.zeros([1, 4, 28, 28]),
                    torch.zeros([1, 8, 14, 14]),
                    torch.zeros([1, 8, 14, 14]),
                    torch.zeros([1, 8, 14, 14]),
                    torch.zeros([1, 12, 14, 14]),
                    torch.zeros([1, 12, 14, 14]),
                    torch.zeros([1, 20, 7, 7]),
                    torch.zeros([1, 20, 7, 7]))
    if use_gpu:
        target = 'cuda'
    else:
        target = 'llvm -mcpu=cortex-a72 -target=armv7l-linux-gnueabihf'
    return torch2executor(torch_module, torch_inputs, target)


def transform(frame: np.ndarray):
    # 480, 640, 3, 0 ~ 255
    frame = cv2.resize(frame, (224, 224))  # (224, 224, 3) 0 ~ 255
    frame = frame / 255.0  # (224, 224, 3) 0 ~ 1.0
    frame = np.transpose(frame, axes=[2, 0, 1])  # (3, 224, 224) 0 ~ 1.0
    frame = np.expand_dims(frame, axis=0)  # (1, 3, 480, 640) 0 ~ 1.0
    return frame


class GroupScale(object):
    """ Rescales the input PIL.Image to the given 'size'.
    'size' will be the size of the smaller edge.
    For example, if height > width, then image will be
    rescaled to (size * height / width, size)
    size: size of the smaller edge
    interpolation: Default: PIL.Image.BILINEAR
    """

    def __init__(self, size, interpolation=Image.BILINEAR):
        self.worker = torchvision.transforms.Scale(size, interpolation)

    def __call__(self, img_group):
        return [self.worker(img) for img in img_group]


class GroupCenterCrop(object):
    def __init__(self, size):
        self.worker = torchvision.transforms.CenterCrop(size)

    def __call__(self, img_group):
        return [self.worker(img) for img in img_group]


class Stack(object):

    def __init__(self, roll=False):
        self.roll = roll

    def __call__(self, img_group):
        if img_group[0].mode == 'L':
            return np.concatenate([np.expand_dims(x, 2) for x in img_group], axis=2)
        elif img_group[0].mode == 'RGB':
            if self.roll:
                return np.concatenate([np.array(x)[:, :, ::-1] for x in img_group], axis=2)
            else:
                return np.concatenate(img_group, axis=2)


class ToTorchFormatTensor(object):
    """ Converts a PIL.Image (RGB) or numpy.ndarray (H x W x C) in the range [0, 255]
    to a torch.FloatTensor of shape (C x H x W) in the range [0.0, 1.0] """

    def __init__(self, div=True):
        self.div = div

    def __call__(self, pic):
        if isinstance(pic, np.ndarray):
            # handle numpy array
            img = torch.from_numpy(pic).permute(2, 0, 1).contiguous()
        else:
            # handle PIL Image
            img = torch.ByteTensor(torch.ByteStorage.from_buffer(pic.tobytes()))
            img = img.view(pic.size[1], pic.size[0], len(pic.mode))
            # put it from HWC to CHW format
            # yikes, this transpose takes 80% of the loading time/CPU
            img = img.transpose(0, 1).transpose(0, 2).contiguous()
        return img.float().div(255) if self.div else img.float()


class GroupNormalize(object):
    def __init__(self, mean, std):
        self.mean = mean
        self.std = std

    def __call__(self, tensor):
        rep_mean = self.mean * (tensor.size()[0] // len(self.mean))
        rep_std = self.std * (tensor.size()[0] // len(self.std))

        # TODO: make efficient
        for t, m, s in zip(tensor, rep_mean, rep_std):
            t.sub_(m).div_(s)

        return tensor


def get_transform():
    cropping = torchvision.transforms.Compose([
        GroupScale(256),
        GroupCenterCrop(224),
    ])
    transform = torchvision.transforms.Compose([
        cropping,
        Stack(roll=False),
        ToTorchFormatTensor(div=True),
        GroupNormalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    return transform

categories = [
    "Doing other things",  # 0
    "Drumming Fingers",  # 1
    "No gesture",  # 2
    "Pulling Hand In",  # 3
    "Pulling Two Fingers In",  # 4
    "Pushing Hand Away",  # 5
    "Pushing Two Fingers Away",  # 6
    "Rolling Hand Backward",  # 7
    "Rolling Hand Forward",  # 8
    "Shaking Hand",  # 9
    "Sliding Two Fingers Down",  # 10
    "Sliding Two Fingers Left",  # 11
    "Sliding Two Fingers Right",  # 12
    "Sliding Two Fingers Up",  # 13
    "Stop Sign",  # 14
    "Swiping Down",  # 15
    "Swiping Left",  # 16
    "Swiping Right",  # 17
    "Swiping Up",  # 18
    "Thumb Down",  # 19
    "Thumb Up",  # 20
    "Turning Hand Clockwise",  # 21
    "Turning Hand Counterclockwise",  # 22
    "Zooming In", #"Zooming In With Full Hand",  # 23
    "Zooming In With Two Fingers",  # 24
    "Zooming Out", #"Zooming Out With Full Hand",  # 25
    "Zooming Out With Two Fingers"  # 26
]


n_still_frame = 0

def process_output(idx_, history):
    # idx_: the output of current frame
    # history: a list containing the history of predictions
    if not REFINE_OUTPUT:
        return idx_, history

    max_hist_len = 20  # max history buffer

    # mask out illegal action
    if idx_ in [7, 8, 21, 22, 3, 15, 18, 14, 10, 13]:
        idx_ = history[-1]

    # use only single no action class
    if idx_ == 0:
        idx_ = 2

    # group similar actions
    if idx_ == 11:
        idx_ = 16
    elif idx_ == 12:
        idx_ = 17
    elif idx_ == 24:
        idx_ = 23
    elif idx_ == 26:
        idx_ = 25
    
    # history smoothing
    if idx_ != history[-1]:
        if not (history[-1] == history[-2]): #  and history[-2] == history[-3]):
            idx_ = history[-1]
    

    history.append(idx_)
    history = history[-max_hist_len:]

    return history[-1], history


WINDOW_NAME = 'Video Gesture Recognition'
def main():
    parser = get_parser()
    args = parser.parse_args()

    with open('persistent_gestures.txt', 'r') as f:
        persistent_gestures = f.read().splitlines()

    nvim = None
    if args.nvim_socket_path is not None:
        print("Neovim socket path: %s", args.nvim_socket_path)
        for _ in range(1000):
            try:
                nvim = pynvim.attach('socket', path=args.nvim_socket_path)
            except Exception as e:
                time.sleep(0.1)
            else:
                break
        else:
            print('Timeout while waiting for nvim to start')
            return

        print("nvim attached")
        nvim.vars['hand_gesture_persistent_frame'] = 0
        nvim.vars['quit_nvim_hand_gesture'] = 0

    print("Open camera...")
    cap = cv2.VideoCapture(0)
    
    print(cap)

    # set a lower resolution for speed up
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)


    if not args.headless:
        # env variables
        full_screen = False
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, 640, 480)
        cv2.moveWindow(WINDOW_NAME, 0, 0)
        cv2.setWindowTitle(WINDOW_NAME, WINDOW_NAME)


    t = None
    index = 0
    print("Build transformer...")
    transform = get_transform()
    print("Build Executor...")
    executor, ctx = get_executor()
    buffer = (
        tvm.nd.empty((1, 3, 56, 56), ctx=ctx),
        tvm.nd.empty((1, 4, 28, 28), ctx=ctx),
        tvm.nd.empty((1, 4, 28, 28), ctx=ctx),
        tvm.nd.empty((1, 8, 14, 14), ctx=ctx),
        tvm.nd.empty((1, 8, 14, 14), ctx=ctx),
        tvm.nd.empty((1, 8, 14, 14), ctx=ctx),
        tvm.nd.empty((1, 12, 14, 14), ctx=ctx),
        tvm.nd.empty((1, 12, 14, 14), ctx=ctx),
        tvm.nd.empty((1, 20, 7, 7), ctx=ctx),
        tvm.nd.empty((1, 20, 7, 7), ctx=ctx)
    )
    idx = 0
    history = [2]
    history_logit = []
    history_timing = []

    i_frame = -1

    print("Ready!")
    while True:
        i_frame += 1
        _, img = cap.read()  # (480, 640, 3) 0 ~ 255
        if i_frame % 2 == 0:  # skip every other frame to obtain a suitable frame rate
            t1 = time.time()
            img_tran = transform([Image.fromarray(img).convert('RGB')])
            input_var = torch.autograd.Variable(img_tran.view(1, 3, img_tran.size(1), img_tran.size(2)))
            img_nd = tvm.nd.array(input_var.detach().numpy(), ctx=ctx)
            inputs: Tuple[tvm.nd.NDArray] = (img_nd,) + buffer
            outputs = executor(inputs)
            feat, buffer = outputs[0], outputs[1:]
            assert isinstance(feat, tvm.nd.NDArray)
            
            if SOFTMAX_THRES > 0:
                feat_np = feat.asnumpy().reshape(-1)
                feat_np -= feat_np.max()
                softmax = np.exp(feat_np) / np.sum(np.exp(feat_np))

                print(max(softmax))
                if max(softmax) > SOFTMAX_THRES:
                    idx_ = np.argmax(feat.asnumpy(), axis=1)[0]
                else:
                    idx_ = idx
            else:
                idx_ = np.argmax(feat.asnumpy(), axis=1)[0]

            if HISTORY_LOGIT:
                history_logit.append(feat.asnumpy())
                history_logit = history_logit[-12:]
                avg_logit = sum(history_logit)
                idx_ = np.argmax(avg_logit, axis=1)[0]

            idx, history = process_output(idx_, history)

            t2 = time.time()
            print(f"{index} {categories[idx]}")

            if nvim is not None:
                category_lower = categories[idx].lower().replace(' ', '_')
                lua_file = f'gesture_mappings/{category_lower}.lua'
                if os.path.isfile(lua_file):
                    if category_lower in persistent_gestures:
                        # Execute multiple times until the gesture is no longer detected
                        nvim.vars['hand_gesture_persistent_frame'] += 1
                        with open(lua_file, 'r') as f:
                            lua_code = f.read()
                            nvim.exec_lua(lua_code)
                    else:
                        # Execute only once
                        if idx != history[-2]:
                            nvim.vars['hand_gesture_persistent_frame'] = 0

                            with open(lua_file, 'r') as f:
                                lua_code = f.read()
                                nvim.exec_lua(lua_code)

            current_time = t2 - t1

        if not args.headless:
            img = cv2.resize(img, (640, 480))
            img = img[:, ::-1]
            height, width, _ = img.shape
            label = np.zeros([height // 10, width, 3]).astype('uint8') + 255

            cv2.putText(label, 'Prediction: ' + categories[idx],
                        (0, int(height / 16)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 0, 0), 2)
            cv2.putText(label, '{:.1f} Vid/s'.format(1 / current_time),
                        (width - 170, int(height / 16)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 0, 0), 2)

            img = np.concatenate((img, label), axis=0)
            cv2.imshow(WINDOW_NAME, img)

            key = cv2.waitKey(1)
            if key & 0xFF == ord('q') or key == 27:  # exit
                break
            elif key == ord('F') or key == ord('f'):  # full screen
                print('Changing full screen option!')
                full_screen = not full_screen
                if full_screen:
                    print('Setting FS!!!')
                    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN,
                                          cv2.WINDOW_FULLSCREEN)
                else:
                    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN,
                                          cv2.WINDOW_NORMAL)
        else:
            key = cv2.waitKey(1)

        if nvim is not None and nvim.vars['quit_nvim_hand_gesture'] == 1:
            break

        if t is None:
            t = time.time()
        else:
            nt = time.time()
            index += 1
            t = nt

    cap.release()

    if not args.headless:
        cv2.destroyAllWindows()


main()
