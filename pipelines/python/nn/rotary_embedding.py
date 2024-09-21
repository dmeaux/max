# ===----------------------------------------------------------------------=== #
# Copyright (c) 2024, Modular Inc. All rights reserved.
#
# Licensed under the Apache License v2.0 with LLVM Exceptions:
# https://llvm.org/LICENSE.txt
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ===----------------------------------------------------------------------=== #
"""The rope embedding used within the model."""

from dataclasses import dataclass
from functools import cached_property
from typing import Optional

import numpy as np
from max.dtype import DType
from max.graph import DimLike, TensorValue, ValueLike, ops


@dataclass
class RotaryEmbedding:
    """
    RotaryEmbedding layer to calculate and apply the frequency tensor for complex exponentials.
    """

    dim: DimLike
    n_heads: int
    theta: float
    """Hyperparameter used to control the frequency scaling of the sinusoidal components of the embeddings."""
    max_seq_len: int
    """The maximum sequence length for model's input."""
    rope_scaling: Optional[np.ndarray]
    """Scaling factor for the positional frequencies."""
    _freqs_cis: Optional[ValueLike] = None

    def freqs_cis_base(self) -> TensorValue:
        """
        Computes the frequency tensor for complex exponentials (cis)
        for a given seq_len. Tensor is scaled with theta parameter.
        Required to apply Rotary Position Embedding (RoPE) to tensor.
        See 'Roformer: Enhanced Transformer with Rotary Embedding'
        (arxiv.org/pdf/2104.09864).

        Returns:
            The frequency tensor for complex exponentials with shape
                (max_seq_len * 2, dim//(2 * n_heads), 2)
        """
        if self._freqs_cis is None:
            n = self.dim // self.n_heads
            # Note: using float64 to avoid an overflow on the exponential, then converting back to float32.
            iota = ops.range(
                ops.constant(0, DType.float64),
                ops.constant(n - 1, DType.float64),
                ops.constant(2, DType.float64),
                out_dim=n // 2,
            )
            if self.rope_scaling is not None:
                iota = iota * self.rope_scaling
            freqs = ops.cast(1.0 / (self.theta ** (iota / n)), DType.float32)
            t = ops.range(
                ops.constant(0, DType.float32),
                ops.constant(self.max_seq_len * 2.0, DType.float32),
                ops.constant(1, DType.float32),
                out_dim=self.max_seq_len * 2,
            )
            freqs = ops.outer(t, freqs)
            self._freqs_cis = ops.stack(
                [ops.cos(freqs), ops.sin(freqs)], axis=-1
            )
        return TensorValue(self._freqs_cis)

    @cached_property
    def freqs_cis(self) -> TensorValue:
        self._freqs_cis = self.freqs_cis_base()
        return self._freqs_cis

    def __call__(
        self, x: ValueLike, start_pos: int, seq_len: int
    ) -> TensorValue:
        """Applies rotary positional embeddings (RoPE) to `x`.

        Args:
            x: Activation tensor with shape (batch, seq_len, n_kv_heads, head_dim).
            start_pos: starting position of input tensor
            seq_len: length of input tensor

        Returns:
            Input activation tensor with rotary positional embeddings applied and
            the same shape as `x`.
        """
        v = TensorValue(x)

        complex = ops.as_interleaved_complex(v)

        start_pos_val = TensorValue.from_dim(start_pos)
        seq_len_val = TensorValue.from_dim(seq_len)
        freqs_cis_sliced = self.freqs_cis[
            (slice(start_pos_val, start_pos_val + seq_len_val), seq_len),
        ]

        freqs_cis_bcast = ops.unsqueeze(ops.unsqueeze(freqs_cis_sliced, 1), 0)

        x_re = complex[..., 0]
        x_im = complex[..., 1]

        freqs_re = freqs_cis_bcast[..., 0]
        freqs_im = freqs_cis_bcast[..., 1]

        rope_re = (x_re * freqs_re) - (x_im * freqs_im)
        rope_im = (x_re * freqs_im) + (x_im * freqs_re)

        rope_complex = ops.stack([rope_re, rope_im], axis=-1)

        # Cast back to the activations dtype, which may differ from
        # freqs_cis's dtype.
        return ops.cast(ops.reshape(rope_complex, v.shape), v.dtype)


@dataclass
class OptimizedRotaryEmbedding(RotaryEmbedding):
    """
    Optimized version of RotaryEmbedding using 2D frequency tensor representation.
    """

    @cached_property
    def freqs_cis(self):
        freqs = self.freqs_cis_base()
        d1, d2, d3 = freqs.shape
        new_f_shape = [d1.dim, d2.dim * d3.dim]
        self._freqs_cis = ops.reshape(freqs, new_f_shape)
        return self._freqs_cis
