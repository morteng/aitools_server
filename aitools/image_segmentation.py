import os
import time
import numpy as np
from skimage import io
import time
from glob import glob
from tqdm import tqdm

import torch
import gc
import torch.nn as nn
from torch.autograd import Variable
import torch.optim as optim
import torch.nn.functional as F
from torchvision.transforms.functional import normalize
from PIL import Image
import wget

# import importlib
from os.path import dirname
import sys
sys.path.append(f'{dirname(__file__)}/DIS/IS-Net/models')
from isnet import ISNetGTEncoder, ISNetDIS

model_path = f"{dirname(__file__)}/DIS/saved_models/IS-Net/isnet-general-use.pth"

if not os.path.exists(model_path):
    print("Missing file isnet-general-use.pth, downloading.  (refer to https://github.com/xuebinqin/DIS or the aitools/DIS subdir for license information) ")
    wget.download('https://rtsoft.com/files/ai/isnet-general-use.pth', dirname(__file__)+'/DIS/saved_models/IS-Net')
    if not os.path.exists(model_path):
        print(f"Error downloading.  Get it and move it into {model_path} somehow!")

input_size=[1024,1024]
net=ISNetDIS()
if torch.cuda.is_available():
        net.load_state_dict(torch.load(model_path))
        net=net.cuda()
else:
        net.load_state_dict(torch.load(model_path,map_location="cpu"))
net.eval()
print("Highly Accurate Dichotomous Image Segmentation model loaded")


def DoImageSegmentationAndReturnMask(inputPic: Image):

        im = np.asarray(inputPic)
        if len(im.shape) < 3:
            im = im[:, :, np.newaxis]
        im_shp = im.shape[0:2]
        im_tensor = torch.tensor(im, dtype=torch.float32).permute(2, 0, 1)
        im_tensor = F.upsample(torch.unsqueeze(
            im_tensor, 0), input_size, mode="bilinear").type(torch.uint8)
        image = torch.divide(im_tensor, 255.0)
        image = normalize(image, [0.5, 0.5, 0.5], [1.0, 1.0, 1.0])

        if torch.cuda.is_available():
            image = image.cuda()
        result = net(image)
        result = torch.squeeze(F.upsample(
            result[0][0], im_shp, mode='bilinear'), 0)
        ma = torch.max(result)
        mi = torch.min(result)
        result = (result-mi)/(ma-mi)

        tempResult = (result*255).permute(1,2,0).cpu().data.numpy().astype(np.uint8)
        tempResult = np.squeeze(tempResult,  axis=2)  # axis=2 is channel dimension 
        return Image.fromarray(tempResult)


def Test():

    #easy way to test it, as long as pic.png exists
    pic = Image.open("pic.png", mode='r')
    pic = pic.convert('RGB')
    returnPic = DoImageSegmentationAndReturnMask(pic)
    returnPic.save("test_output_image.png")


#Test() #uncomment so you can just run this file directly to test, will create test_output_image.png

