# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""EnCodec model implementation."""

import math
from pathlib import Path
import typing as tp

import numpy as np
import torch
from torch import nn

import quantization as qt
from modules import SEANetEncoder, SEANetDecoder
import random

class SAT(nn.Module):
    def __init__(self,
                 sample_rate: int = 24_000,
                 channels: int = 1,
                 causal: bool = True,
                 model_norm: str = 'weight_norm',
                 audio_normalize: bool = False,
                 ratios=[8, 5, 4, 2],
                 multi_scale=None,
                 phi_kernel=None,
                 dimension=128,
                 latent_dim=32,
                 n_residual_layers=1,
                 lstm=2):
        super().__init__()
        self.encoder = SEANetEncoder(channels=channels, dimension=dimension, norm=model_norm, causal=causal,ratios=ratios, n_residual_layers=n_residual_layers, lstm=lstm)
        self.decoder = SEANetDecoder(channels=channels, dimension=dimension, norm=model_norm, causal=causal,ratios=ratios, n_residual_layers=n_residual_layers, lstm=lstm)
        self.quantizer = qt.ResidualVectorQuantizer(
            dimension=dimension,
            n_q=len(multi_scale),
            bins=1024,
            latent_dim=latent_dim,
            multi_scale=multi_scale,
            phi_kernel=phi_kernel
        )


    def forward(self, x: torch.Tensor):
        e = self.encoder(x)
        quant, code, vq_loss = self.quantizer(e)
        output = self.decoder(quant)
        return output, code, vq_loss
        


        

# class EncodecModel(nn.Module):
#     """EnCodec model operating on the raw waveform.
#     Args:
#         target_bandwidths (list of float): Target bandwidths.
#         encoder (nn.Module): Encoder network.
#         decoder (nn.Module): Decoder network.
#         sample_rate (int): Audio sample rate.
#         channels (int): Number of audio channels.
#         normalize (bool): Whether to apply audio normalization.
#         segment (float or None): segment duration in sec. when doing overlap-add.
#         overlap (float): overlap between segment, given as a fraction of the segment duration.
#         name (str): name of the model, used as metadata when compressing audio.
#     """
#     def __init__(self,
#                  encoder: m.SEANetEncoder,
#                  decoder: m.SEANetDecoder,
#                  quantizer: qt.ResidualVectorQuantizer,
#                  target_bandwidths: tp.List[float],
#                  sample_rate: int,
#                  channels: int,
#                  normalize: bool = False,
#                  segment: tp.Optional[float] = None,
#                  overlap: float = 0.01,
#                  name: str = 'unset'):
#         super().__init__()
#         self.bandwidth: tp.Optional[float] = None
#         self.target_bandwidths = target_bandwidths
#         self.encoder = encoder
#         self.quantizer = quantizer
#         self.decoder = decoder
#         self.sample_rate = sample_rate
#         self.channels = channels
#         self.normalize = normalize
#         self.segment = segment
#         self.overlap = overlap
#         self.frame_rate = math.ceil(self.sample_rate / np.prod(self.encoder.ratios)) #75
#         self.name = name
#         self.bits_per_codebook = int(math.log2(self.quantizer.bins))
#         assert 2 ** self.bits_per_codebook == self.quantizer.bins, \
#             "quantizer bins must be a power of 2."

#     @property
#     def segment_length(self) -> tp.Optional[int]:
#         if self.segment is None:
#             return None
#         return int(self.segment * self.sample_rate)

#     @property
#     def segment_stride(self) -> tp.Optional[int]:
#         segment_length = self.segment_length
#         if segment_length is None:
#             return None
#         return max(1, int((1 - self.overlap) * segment_length))

#     def encode(self, x: torch.Tensor) -> tp.List[EncodedFrame]:
#         """Given a tensor `x`, returns a list of frames containing
#         the discrete encoded codes for `x`, along with rescaling factors
#         for each segment, when `self.normalize` is True.

#         Each frames is a tuple `(codebook, scale)`, with `codebook` of
#         shape `[B, K, T]`, with `K` the number of codebooks.
#         """
#         assert x.dim() == 3
#         _, channels, length = x.shape
#         assert channels > 0 and channels <= 2
#         segment_length = self.segment_length 
#         if segment_length is None: #segment_length = 1*sample_rate
#             segment_length = length
#             stride = length
#         else:
#             stride = self.segment_stride  # type: ignore
#             assert stride is not None

#         encoded_frames: tp.List[EncodedFrame] = []
#         for offset in range(0, length, stride): # shift windows to choose data
#             frame = x[:, :, offset: offset + segment_length]
#             encoded_frames.append(self._encode_frame(frame))
#         return encoded_frames

#     def _encode_frame(self, x: torch.Tensor) -> EncodedFrame:
#         length = x.shape[-1] # tensor_cut or original
#         duration = length / self.sample_rate
#         assert self.segment is None or duration <= 1e-5 + self.segment

#         if self.normalize:
#             mono = x.mean(dim=1, keepdim=True)
#             volume = mono.pow(2).mean(dim=2, keepdim=True).sqrt()
#             scale = 1e-8 + volume
#             x = x / scale
#             scale = scale.view(-1, 1)
#         else:
#             scale = None

#         emb = self.encoder(x) # [2,1,10000] -> [2,128,32]
#         #TODO: Encodec Trainer的training
#         if self.training:
#             return emb,scale
#         codes = self.quantizer.encode(emb, self.frame_rate, self.bandwidth)
#         # TODO need to change the shape
#         # codes = codes.transpose(0, 1)
#         # codes is [B, K, T], with T frames, K nb of codebooks.
#         return codes, scale

#     def audio_to_idxBl(self, x):
#         length = x.shape[-1] # tensor_cut or original
#         duration = length / self.sample_rate
#         assert self.segment is None or duration <= 1e-5 + self.segment

#         if self.normalize:
#             mono = x.mean(dim=1, keepdim=True)
#             volume = mono.pow(2).mean(dim=2, keepdim=True).sqrt()
#             scale = 1e-8 + volume
#             x = x / scale
#             scale = scale.view(-1, 1)
#         else:
#             scale = None

#         emb = self.encoder(x) # [2,1,10000] -> [2,128,32]
#         #TODO: Encodec Trainer的training
#         if self.training:
#             return emb,scale
#         codes = self.quantizer.encode(emb, self.frame_rate, self.bandwidth)
#         # codes is [B, K, T], with T frames, K nb of codebooks.
#         return codes, scale

#     def idxBl_to_h(self, labels_list):
#         return self.quantizer.idxBl_to_var_input(labels_list)
    
#     def fhat_to_audio(self, fhat):
#         return self.decoder(self.quantizer.post_conv(fhat))

#     def decode(self, encoded_frames: tp.List[EncodedFrame]) -> torch.Tensor:
#         """Decode the given frames into a waveform.
#         Note that the output might be a bit bigger than the input. In that case,
#         any extra steps at the end can be trimmed.
#         """
#         segment_length = self.segment_length
#         if segment_length is None:
#             assert len(encoded_frames) == 1
#             return self._decode_frame(encoded_frames[0])

#         frames = [self._decode_frame(frame) for frame in encoded_frames]
#         return _linear_overlap_add(frames, self.segment_stride or 1)

#     def _decode_frame(self, encoded_frame: EncodedFrame) -> torch.Tensor:
#         codes, scale = encoded_frame
#         if self.training:
#             emb = codes
#         else:
#             # codes = codes.transpose(0, 1)
#             emb = self.quantizer.decode(codes)
#         out = self.decoder(emb)
#         if scale is not None:
#             out = out * scale.view(-1, 1, 1)
#         return out

#     def recon_with_scale(self, x: torch.Tensor) -> tp.List[torch.Tensor]:
#         [(codes, _)] = self.encode(x)
#         embs = self.quantizer.decode_each_scale(codes)
#         outs = [self.decoder(emb) for emb in embs]
#         return outs
#     def get_codebook_usage(self):
#         self.quantizer.get_codebook_usage()

#     def forward(self, x: torch.Tensor) -> torch.Tensor:
#         frames = self.encode(x) # input_wav -> encoder , x.shape = [BatchSize,channel,tensor_cut or original length] 2,1,10000
#         if self.training:
#             # if encodec is training, input_wav -> encoder -> quantizer forward -> decode
#             loss_w = torch.tensor([0.0], device=x.device, requires_grad=True)
#             codes = []
#             # self.quantizer.train(self.training)
#             index = torch.tensor(random.randint(0,len(self.target_bandwidths)-1),device=x.device)
#             if torch.distributed.is_initialized():
#                 torch.distributed.broadcast(index, src=0)
#             bw = self.target_bandwidths[index.item()]# fixme: variable bandwidth training, if you broadcast bd, the broadcast will encounter error
#             for emb,scale in frames:
#                 qv = self.quantizer(emb,self.frame_rate,bw)
#                 loss_w = loss_w + qv.penalty # loss_w is the sum of all quantizer forward loss (RVQ commitment loss :l_w)
#                 codes.append((qv.quantized,scale))
#             return self.decode(codes)[:,:,:x.shape[-1]],loss_w,frames
#         else:
#             # if encodec is not training, input_wav -> encoder -> quantizer encode -> decode
#             return self.decode(frames)[:, :, :x.shape[-1]]

#     def set_target_bandwidth(self, bandwidth: float):
#         if bandwidth not in self.target_bandwidths:
#             raise ValueError(f"This model doesn't support the bandwidth {bandwidth}. "
#                              f"Select one of {self.target_bandwidths}.")
#         self.bandwidth = bandwidth

#     @staticmethod
#     def _get_model(sample_rate: int = 24_000,
#                    channels: int = 1,
#                    causal: bool = True,
#                    model_norm: str = 'weight_norm',
#                    audio_normalize: bool = False,
#                    ratios=[8, 5, 4, 2],
#                    multi_scale=None,
#                    phi_kernel=None,
#                    dimension=128,
#                    latent_dim=32,
#                    n_residual_layers=1,
#                    lstm=2):
#         encoder = m.SEANetEncoder(channels=channels, dimension=dimension, norm=model_norm, causal=causal,ratios=ratios, n_residual_layers=n_residual_layers, lstm=lstm)
#         decoder = m.SEANetDecoder(channels=channels, dimension=dimension, norm=model_norm, causal=causal,ratios=ratios, n_residual_layers=n_residual_layers, lstm=lstm)
#         n_q = len(self.multi_scale)
#         quantizer = qt.ResidualVectorQuantizer(
#             dimension=encoder.dimension,
#             n_q=n_q,
#             bins=1024,
#             latent_dim=latent_dim,
#             multi_scale=multi_scale,
#             phi_kernel=phi_kernel,
#             shared_codebook=shared_codebook,
#             share_phi=share_phi
#         )
#         model = EncodecModel(
#             encoder,
#             decoder,
#             quantizer,
#             sample_rate,
#             channels,
#             normalize=audio_normalize,
#         )
#         return model

#     def get_last_layer(self):
#         return self.decoder.layers[-1].weight

#     @staticmethod
#     def _get_pretrained(checkpoint_name: str, repository: tp.Optional[Path] = None):
#         if repository is not None:
#             if not repository.is_dir():
#                 raise ValueError(f"{repository} must exist and be a directory.")
#             file = repository / checkpoint_name
#             checksum = file.stem.split('-')[1]
#             _check_checksum(file, checksum)
#             return torch.load(file)
#         else:
#             url = _get_checkpoint_url(ROOT_URL, checkpoint_name)
#             return torch.hub.load_state_dict_from_url(url, map_location='cpu', check_hash=True)  # type:ignore

#     @staticmethod
#     def encodec_model_24khz(pretrained: bool = True, repository: tp.Optional[Path] = None):
#         """Return the pretrained causal 24khz model.
#         """
#         if repository:
#             assert pretrained
#         target_bandwidths = [1.5, 3., 6, 12., 24.]
#         checkpoint_name = 'encodec_24khz-d7cc33bc.th'
#         sample_rate = 24_000
#         channels = 1
#         model = EncodecModel._get_model(
#             target_bandwidths, sample_rate, channels,
#             causal=True, model_norm='weight_norm', audio_normalize=False,
#             name='encodec_24khz' if pretrained else 'unset')
#         if pretrained:
#             state_dict = EncodecModel._get_pretrained(checkpoint_name, repository)
#             model.load_state_dict(state_dict)
#         model.eval()
#         return model

#     @staticmethod
#     def encodec_model_48khz(pretrained: bool = True, repository: tp.Optional[Path] = None):
#         """Return the pretrained 48khz model.
#         """
#         if repository:
#             assert pretrained
#         target_bandwidths = [3., 6., 12., 24.]
#         checkpoint_name = 'encodec_48khz-7e698e3e.th'
#         sample_rate = 48_000
#         channels = 2
#         model = EncodecModel._get_model(
#             target_bandwidths, sample_rate, channels,
#             causal=False, model_norm='time_group_norm', audio_normalize=True,
#             segment=1., name='encodec_48khz' if pretrained else 'unset')
#         if pretrained:
#             state_dict = EncodecModel._get_pretrained(checkpoint_name, repository)
#             model.load_state_dict(state_dict)
#         model.eval()
#         return model

#     #TODO: 自己实现一个encodec的model
#     @staticmethod
#     def my_encodec_model(checkpoint: str,ratios=[8,5,4,2]):
#         """Return the pretrained 24khz model.
#         """
#         import os
#         assert os.path.exists(checkpoint), "checkpoint not exists"
#         print("loading model from: ",checkpoint)
#         target_bandwidths = [1.5, 3., 6, 12., 24.]
#         sample_rate = 24_000
#         channels = 1
#         model = EncodecModel._get_model(
#                 target_bandwidths, sample_rate, channels,
#                 causal=False, model_norm='time_group_norm', audio_normalize=True,
#                 segment=None, name='my_encodec',ratios=ratios)
#         pre_dic = torch.load(checkpoint)['model_state_dict']
#         model.load_state_dict({k.replace('quantizer.model','quantizer.vq'):v for k,v in pre_dic.items()})
#         model.eval()
#         return model
    
#     @staticmethod
#     def encodec_model_bw(checkpoint: str, bandwidth: float):
#         """Return target bw model, if you train a model in a single bandwidth
#         """
#         import os
#         assert os.path.exists(checkpoint), "checkpoint not exists"
#         print("loading model from: ",checkpoint)
#         target_bandwidths = bandwidth
#         sample_rate = 24_000
#         channels = 1
#         model = EncodecModel._get_model(
#                 target_bandwidths, sample_rate, channels,
#                 causal=False, model_norm='time_group_norm', audio_normalize=True,
#                 segment=1., name='my_encodec')
#         pre_dic = torch.load(checkpoint)['model_state_dict']
#         model.load_state_dict({k.replace('quantizer.model','quantizer.vq'):v for k,v in pre_dic.items()})
#         model.eval()
#         return model


def test():
    from itertools import product
    import torchaudio
    bandwidths = [3, 6, 12, 24]
    models = {
        'encodec_24khz': EncodecModel.encodec_model_24khz,
        'encodec_48khz': EncodecModel.encodec_model_48khz,
        "my_encodec": EncodecModel.my_encodec_model,
        "encodec_bw": EncodecModel.encodec_model_bw,
    }
    for model_name, bw in product(models.keys(), bandwidths):
        model = models[model_name]()
        model.set_target_bandwidth(bw)
        audio_suffix = model_name.split('_')[1][:3]
        wav, sr = torchaudio.load(f"test_{audio_suffix}.wav")
        wav = wav[:, :model.sample_rate * 2]
        wav_in = wav.unsqueeze(0)
        wav_dec = model(wav_in)[0]
        assert wav.shape == wav_dec.shape, (wav.shape, wav_dec.shape)


if __name__ == '__main__':
    test()