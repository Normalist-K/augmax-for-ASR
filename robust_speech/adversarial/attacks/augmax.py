import os, sys, argparse, inspect
from cv2 import transform
import numpy as np
import torch
import torch.nn as nn
from torch_audiomentations import Compose
from copy import deepcopy

import robust_speech as rs
from robust_speech.adversarial.attacks.attacker import Attacker
from robust_speech.adversarial.utils import (
    l2_clamp_or_normalize,
    linf_clamp,
    rand_assign,
)

from robust_speech.adversarial.attacks.augmentations import augmentations


# data:
def aug_one(x, mixture_depth, aug_severity):
    """Perform K random augmentation operations on the original speech signal xori
    Args:
        speech: orignal input speech
        preprocess: a function that can convert the speech signoal into tensor, for input into NN
        mixture_depth: x_augi is generated by randomly selecting K augmentation methods
        aug_severity: level of augmentation operation
    Returns:
        torch tensor of augmented speech (x_augi)
    """
    aug_list = augmentations

    device = x.device.type
    with torch.no_grad():
        x_aug = x.unsqueeze(1).clone().to('cpu') # mono channel
        depth = mixture_depth if mixture_depth > 0 else np.random.randint(1, 3)
        transforms = []
        for _ in range(depth):
            op = np.random.choice(aug_list)
            transforms.append(op(aug_severity))
        aug = Compose(
            transforms=transforms
        )
        # import pdb; pdb.set_trace()
        x_aug = aug(x_aug, sample_rate=16000)
        x_aug = x_aug.squeeze(1).to(device)
    return x_aug

# def aug_one(x, mixture_depth, aug_severity):
#     return x

def aug_all(x, mixture_width=3, mixture_depth=-1, aug_severity=3):
    #input speech signal x (x_ori)
    #output: xs: [xori, xaug1, xaug2, ...]
    # x.shape = 1, 381760
    xs = [x]
    for _ in range(mixture_width):
        xs.append(
            aug_one(x, mixture_depth, aug_severity)
        )
    return xs

def augmax_combine(xs, m, q, device='cuda'):
    '''
    combine different aug operations to get the final augmentation
    Args:
        xs: xs = [x_ori, x_aug1, x_aug2, x_aug3]
        m: Tensor. m.size=(N)
        q: Tensor. q.size()=(N,3). w = softmax(q)
    output:
        final xaug = (1-m)xori + m* \sum_i (wi*x_augi)
    '''

    x_ori = xs[0]
    w = torch.nn.functional.softmax(q, dim=1)  # w.size()=(N,3)

    N = x_ori.size()[0]

    x_mix = torch.zeros_like(x_ori).to(device)
    for i, x_aug in enumerate(xs[1:]):
        wi = w[:, i].view((N, 1)).expand_as(x_aug)
        x_mix += wi * x_aug 

    m = m.view((N, 1)).expand_as(x_ori)
    x_mix = (1 - m) * x_ori + m * x_mix
    return x_mix


class AugMaxAttack(Attacker):
    """
    Implementation of the PGD attack (https://arxiv.org/abs/1706.06083)
    The attack performs nb_iter steps of size eps_iter, while always staying
    within eps from the initial point.

    Arguments
    ---------
    asr_brain: rs.adversarial.brain.ASRBrain
       brain object.
    eps: float
       maximum distortion.
    nb_iter: int
       number of iterations.
    eps_iter: float
       attack step size.
    rand_init: (optional bool)
       random initialization.
    clip_min: (optional) float
       mininum value per input dimension.
    clip_max: (optional) float
       maximum value per input dimension.
    order: (optional) int
       the order of maximum distortion (inf or 2).
    targeted: bool
       if the attack is targeted.
    train_mode_for_backward: bool
       whether to force training mode in backward passes (necessary for RNN models)
    """

    def __init__(
        self,
        asr_brain,
        eps=0.1,
        nb_iter=10,
        targeted=False,
        train_mode_for_backward=True,
    ):
        #original pgd attack parameters
        self.eps = eps
        self.nb_iter = nb_iter
        self.targeted = targeted
        self.asr_brain = asr_brain
        #
        self.train_mode_for_backward = train_mode_for_backward
        #augmax settings
        self.mixture_width = 3
        self.mixture_depth = -1
        self.aug_severity = 3

        assert isinstance(self.eps, torch.Tensor) or isinstance(self.eps, float)

    def perturb(self, batch):
        """
        Compute an adversarial perturbation

        Arguments
        ---------
        batch : sb.PaddedBatch
           The input batch to perturb

        Returns
        -------
        the tensor of the perturbed batch
        """
        if self.train_mode_for_backward:
            self.asr_brain.module_train()
        else:
            self.asr_brain.module_eval()

        save_device = batch.sig[0].device
        batch = batch.to(self.asr_brain.device)
        save_input = batch.sig[0]
        wav_init = torch.clone(save_input)

        N = wav_init.size()[0] #return batch size
        # initialize m_adv:
        m_adv = torch.rand(N).to(save_device)  # random initialize in [0,1)
        m_adv = torch.clamp(m_adv, 0, 1)  # clamp to range [0,1)
        m_adv.requires_grad = True
        # initialize ws_adv:
        q_adv = torch.rand((N, self.mixture_width), requires_grad=True).to(save_device)  # random initialize
        # initialize x_adv
        xs = aug_all(wav_init, self.mixture_width, self.mixture_depth, self.aug_severity)
        x_adv = augmax_combine(xs, m_adv, q_adv, save_device)
        # attack step size
        alpha = self.eps #pgd step
        for t in range(self.nb_iter):
            batch.sig = x_adv, batch.sig[1]
            predictions = self.asr_brain.compute_forward(batch, rs.Stage.ATTACK)
            if self.targeted:
                loss_adv = -self.asr_brain.compute_objectives(predictions, batch, rs.Stage.ATTACK)
            else:  # untargeted attack
                loss_adv = self.asr_brain.compute_objectives(predictions, batch, rs.Stage.ATTACK)
            # grad:
            grad_m_adv, grad_q_adv = torch.autograd.grad(loss_adv, [m_adv, q_adv], only_inputs=True)
            # update m:
            m_adv.data.add_(alpha * torch.sign(grad_m_adv.data))  # gradient assend by Sign-SGD
            m_adv = torch.clamp(m_adv, 0, 1)  # clamp to RGB range [0,1]
            # update w1:
            q_adv.data.add_(alpha * torch.sign(grad_q_adv.data))  # gradient assend by Sign-SGD
            # update x_adv:
            x_adv = augmax_combine(xs, m_adv, q_adv, save_device)
        batch.sig = save_input, batch.sig[1]
        batch = batch.to(save_device)
        return x_adv.data.to(save_device)



class AugMixModule(nn.Module):
    def __init__(self, mixture_width, mixture_depth=-1, aug_severity=3, device='cuda'):
        super(AugMixModule, self).__init__()

        self.mixture_width = mixture_width
        self.mixture_depth = mixture_depth
        self.aug_severity = aug_severity
        self.w_dist = torch.distributions.dirichlet.Dirichlet(torch.tensor([1.] * mixture_width)) # Dirichlet parameter must be float in pytorch
        self.m_dist = torch.distributions.beta.Beta(1, 1)

        self.device = device

    def forward(self, wav):
        '''
        Args:
            xs: tuple of Tensors. xs = (x_ori, x_aug1, x_aug2, x_aug3). x_ori.size()=(N,D)
        '''
        wav_init = torch.clone(wav)
        
        xs = aug_all(wav_init, self.mixture_width, self.mixture_depth, self.aug_severity)
        
        x_ori = xs[0]
        N = x_ori.size()[0]
        w = self.w_dist.sample([N]).to(self.device)
        m = self.m_dist.sample([N]).to(self.device)

        x_mix = torch.zeros_like(x_ori).to(self.device)
        for i, x_aug in enumerate(xs[1:]):
            wi = w[:,i].view((N, 1)).expand_as(x_aug)
            x_mix += wi * x_aug 

        m = m.view((N, 1)).expand_as(x_ori)
        x_mix = (1-m) * x_ori + m * x_mix

        return x_mix 



