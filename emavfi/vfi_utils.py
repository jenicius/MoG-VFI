import cv2
import math
import torch
import numpy as np
import argparse
import sys
import torch.nn.functional as F

sys.path.append('.')
import emavfi.config as cfg
from emavfi.Trainer import Model
from emavfi.benchmark.utils.padder import InputPadder
from emavfi.model.warplayer import warp

TTA = False
cfg.MODEL_CONFIG['LOGNAME'] = 'ours_t'
cfg.MODEL_CONFIG['MODEL_ARCH'] = cfg.init_model_config(
    F = 32,
    depth = [2, 2, 2, 4, 4]
)

def get_vfi_model():
    model = Model(-1)
    model.load_model()
    model.eval()
    model.device()
    model.net.train = lambda x: x
    for p in model.net.parameters():
        p.requires_grad = False
    return model


def cal_flow(videos, model):
    device = videos.device
    _, _, time_len, H, W = videos.shape
    mean = torch.tensor((0.5, 0.5, 0.5)).view(1, 3, 1, 1).to(device)
    std = torch.tensor((0.5, 0.5, 0.5)).view(1, 3, 1, 1).to(device)
    img0_, img1_ = videos[:, :, 0].flip(1), videos[:, :, -1].flip(1)
    img0_ = img0_ * std + mean
    img1_ = img1_ * std + mean
    img0 = img0_
    img1 = img1_
    b = img0.size(0)
    time_len = videos.shape[2]
    img0 = img0.repeat_interleave(repeats=time_len-2,dim=0)
    img1 = img1.repeat_interleave(repeats=time_len-2,dim=0)
    timestep = torch.linspace(0,1,time_len)[1:-1].to(device, non_blocking=True).repeat(b).reshape(b*(time_len-2),1,1,1)

    model = model.net.to(device)

    flow, mask = None, None
    af, mf = model.feature_bone(img0, img1)
    B = af[0].shape[0]//2

    for i in range(model.flow_num_stage):
        t = torch.ones_like(mf[-1-i][:B]).to(device) * timestep
        if flow != None:
            warped_img0 = warp(img0, flow[:, :2])
            warped_img1 = warp(img1, flow[:, 2:4])
            flow_, mask_ = model.block[i](
                torch.cat([t*mf[-1-i][:B],(1-t)*mf[-1-i][B:],af[-1-i][:B],af[-1-i][B:]],1),
                torch.cat((img0, img1, warped_img0, warped_img1, mask), 1),
                flow
                )
            flow = flow + flow_
            mask = mask + mask_
        else:
            flow, mask = model.block[i](
                torch.cat([t*mf[-1-i][:B],(1-t)*mf[-1-i][B:],af[-1-i][:B],af[-1-i][B:]],1),
                torch.cat((img0, img1), 1),
                None
                )
    mask = torch.sigmoid(mask)
    return [flow, mask]


def warp_fea(motion, features):
    flow, mask = motion
    b, _, time_len, h, w = features.shape     
    fea0, fea1 = features[:, :, 0], features[:, :, -1]
    fea0 = fea0.repeat_interleave(repeats=time_len-2,dim=0)
    fea1 = fea1.repeat_interleave(repeats=time_len-2,dim=0)
    _, _, H, W = flow.shape
    scale_f = h/H
    flow = scale_f * F.interpolate(flow, size=(h, w), mode="bilinear", align_corners=False, recompute_scale_factor=False)
    mask =  F.interpolate(mask, size=(h, w), mode="bilinear", align_corners=False, recompute_scale_factor=False)
    warped_fea0 = warp(fea0, flow[:, :2])
    warped_fea1 = warp(fea1, flow[:, 2:4])
    warped_feas = warped_fea0 * mask + warped_fea1 * (1 - mask)
    warped_feas = warped_feas.reshape(b, time_len-2, -1, h, w).transpose(1,2)
    return warped_feas